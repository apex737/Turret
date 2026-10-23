/*
 * doa.c : 12.5 kHz 3채널 PCM에서 음원 방위를 구한다 (Step7 D1 = GCC-PHAT + 배경 교차 스펙트럼 빼기, 규약은 doa.h)
 *
 *  원리: 같은 소리가 마이크마다 조금씩 다른 시각에 도착한다. 쌍마다 그 시간차(TDOA)를 구하고,
 *        시간차 3개에 가장 잘 맞는 평면파 방향을 최소제곱으로 푼다. 소리 종류(스냅·드론)와 무관한 계산이다.
 *
 *  시간 구조 (샘플 = 12.5 kHz PCM 한 칸)
 *    프레임  256샘플 (20.48 ms)  : app.c가 한 번에 넣는 단위
 *    블록    512샘플, 256씩 이동  : FFT 한 번의 단위. 프레임 하나가 들어올 때마다 새 블록이 정확히 하나 완성된다
 *    창      6250샘플 (0.5 s)     : 블록 23개의 스펙트럼을 평균해 방위 하나를 낸다
 *    창 이동 3072샘플 (0.246 s)   : 창이 반쯤 겹친다 → 동시에 진행 중인 창은 많아야 2개
 *    배경    10 s (블록 487개)    : 재시작 직후(또는 B1 버튼) 같은 방식으로 평균한 "평소 소리"
 *
 *  한 프레임의 처리 (doa_push)
 *    1) PCM을 링버퍼에 쓴다
 *    2) 새로 완성된 블록을 FFT (block_spectrum) → 배경 합과 진행 중인 창 합에 더한다 (accumulate)
 *       → 같은 블록을 배경·창 2개가 함께 쓰므로 FFT는 프레임당 채널 3개분뿐이다
 *    3) 블록 23개가 다 찬 창이 있으면 마무리 (finalize)
 *         창 평균 교차 스펙트럼 − 배경 평균 교차 스펙트럼 → PHAT(크기를 1로) → 지연별 상관 → 봉우리 = 시간차
 *         → 채널 고유 지연 보정 → 최소제곱 방향 벡터 → atan2 = 방위, 길이 = norm → 유효 판정
 *
 *  창 전체(6250 × 3채널)를 저장하지 않고 블록마다 더하기만 하므로 메모리가 작고(링 6 KB) 계산이 프레임마다 고르게 나뉜다.
 *  PC 기준 구현은 Tools/doa/doa_stream.py, 같은 녹음으로 비교하는 도구는 Tools/doa/compare_mcu.py.
 */
#include "doa.h"
#include "arm_math.h"
#include <string.h>

// 대역 [LO, HI] Hz 에 들어가는 FFT 빈 (빈 k의 주파수 = k x fs / NFFT). doa_stream.py와 같은 포함 규칙(LO ≤ f ≤ HI)
// 빈 간격 = 12500 / 1024 ≈ 12.2 Hz. 실제 쓰는 대역은 K_LO 25 ≈ 305 Hz ~ K_HI 245 ≈ 2991 Hz.
// 주의: doa.h의 DOA_BAND_LO_HZ / DOA_BAND_HI_HZ는 이 숫자를 계산할 때의 근거이고, 코드에서 쓰는 것은 아래 K_LO / K_HI다.
//       대역을 바꾸려면 두 곳과 doa_stream.py --band 기본값을 같이 바꾼다 (I3).
#define K_LO      25u                                   // ceil(300 x 1024 / 12500)  = ceil(24.6)
#define K_HI      245u                                  // floor(3000 x 1024 / 12500) = floor(245.8)
#define NB        (K_HI - K_LO + 1u)                    // 221 : 대역 안 빈 수. 아래 모든 스펙트럼 배열은 이 빈들만 저장한다
#define BHOP      (DOA_BLOCK / 2u)                      // 블록 50% 겹침 → 256 (= 프레임 크기)
#define NBLK      ((DOA_OBS - DOA_BLOCK) / BHOP + 1u)   // 창 하나의 블록 수 = 23 (덮는 구간 22×256+512 = 6144샘플, 창 끝 106샘플은 안 씀)
#define BG_N      (DOA_BG_SECONDS * 12500u)             // 배경 길이 [샘플]
#define BG_NBLK   ((BG_N - DOA_BLOCK) / BHOP + 1u)      // 배경 블록 수 (10 s → 487)
#define RING      1024u                                 // 링버퍼 [샘플/채널]. 가장 오래 기다리는 블록 = 512 + 256 이내
#define NWIN      2u                                    // 동시에 진행하는 창 (창 w는 w+2가 시작하기 전에 끝난다)
#define MAXM      64                                    // 상관 지연 칸 수의 절반 상한 (실제 M = 57)
// M = (간격 0.07 m / 음속 343 m/s × 12500 + 여유 1) × 16 = (2.55 + 1) × 16 ≈ 57 → 지연 −57 ~ +57 (1/16 샘플 단위) = 115칸.
// 7 cm에서 물리적으로 가능한 최대 지연은 2.55샘플(204 µs)이고, 그 밖의 봉우리는 볼 필요가 없다.

_Static_assert(BHOP == DOA_FRAME, "block hop must equal the frame size (one new block per frame and window)");
_Static_assert(DOA_HOP > DOA_FRAME, "at most one window may finish per frame");
_Static_assert(DOA_OBS - DOA_BLOCK - (NBLK - 1u) * BHOP < DOA_HOP, "window w must finish before window w+2 starts");
_Static_assert(RING >= DOA_BLOCK + 2u * DOA_FRAME, "ring too small");
_Static_assert(DOA_HOP % BHOP == 0u, "window hop must be a multiple of the block hop (overlapping windows share block FFTs)");
_Static_assert((RING & (RING - 1u)) == 0u, "ring must be a power of two");

/* 마이크 쌍 (채널 번호 0 ~ 2 = MIC1 ~ 3). 쌍 p = (pair_i[p], pair_j[p]) = (1,2) (1,3) (2,3).
 * tau[p] = j가 i보다 늦게 도착한 시간 [샘플]. 양수면 소리가 i 쪽에 먼저 닿은 것 */
static const uint8_t pair_i[DOA_PAIRS] = {0, 0, 1};
static const uint8_t pair_j[DOA_PAIRS] = {1, 2, 2};

// 스펙트럼 합 (대역 안 빈만): 세 쌍의 교차 X_j·conj(X_i) (re, im) + 세 채널의 자기 |X|²
//  cr : 교차 스펙트럼. 위상 = 두 채널의 위상차 = 2π·f·(시간차) → 시간차 정보가 여기 들어 있다
//  au : 자기 스펙트럼(전력). 방향 계산에는 안 쓰고, 배경 대비 소리가 커졌는지(SNR) 볼 때만 쓴다
//  크기: (3쌍 × 221빈 × 2 + 3채널 × 221빈) × 4 B ≈ 8 KB. 배경 2벌 + 창 2개 = 32 KB가 doa.c 메모리의 절반이다
typedef struct {
	float32_t cr[DOA_PAIRS][NB][2];
	float32_t au[DOA_CH][NB];
} spec_t;

/* 진행 중인 관측 창 하나 */
typedef struct {
	bool     used;                             // 이 칸을 쓰는 중 (창이 시작됐고 아직 안 끝남)
	uint32_t s0;                               // 창의 첫 샘플 번호 (PCM 시간축)
	uint32_t nblk;                             // 지금까지 더한 블록 수 (NBLK가 되면 마무리)
	spec_t   sum;                              // 블록 스펙트럼 합 (마무리할 때 nblk로 나눠 평균)
} win_t;

/* ── 부팅 때 한 번 만들어 두는 표 (doa_init) ── */
static arm_rfft_fast_instance_f32 s_fft;       // CMSIS 실수 FFT(1024점) 설정
static float32_t s_hann[DOA_BLOCK];            // Hann 창 512개. 블록 양 끝을 0으로 줄여 잘린 경계가 만드는 가짜 주파수를 줄인다
static float32_t s_solve[2][DOA_PAIRS];        // 지연 → 방향 벡터 최소제곱 행렬
static float32_t s_delay[DOA_PAIRS];           // 쌍별 채널 지연 보정 [샘플]
static int32_t   s_m;                          // 상관 지연 범위 ±s_m / DOA_UP 샘플
static float32_t s_rot[MAXM + 1][2];           // 지연 l/DOA_UP 의 빈 간 회전 e^{jθ}, θ = 2π l / (NFFT·UP)
static float32_t s_rot0[MAXM + 1][2];          // 첫 빈(K_LO)의 회전 e^{jθ·K_LO}
static float32_t s_ph[DOA_PAIRS][NB][2];       // 세 쌍의 PHAT 가중 교차 스펙트럼 (finalize가 채우고 phat_peaks가 읽음)

/* ── 블록 처리용 ── */
static int16_t   s_ring[DOA_CH][RING];         // 최근 PCM 1024샘플 × 3채널 (6 KB). 인덱스 = 샘플 번호 & 1023 (2의 거듭제곱이라 & 로 나머지)
static float32_t s_fin[DOA_NFFT];              // FFT 입력 (계산 중 덮어써짐)
static float32_t s_fout[DOA_NFFT];             // FFT 출력 (re, im 교대. [0]=DC, [1]=Nyquist)
static float32_t s_xb[DOA_CH][NB][2];          // 블록 하나의 대역 스펙트럼
static uint32_t  s_xb_start;                   // s_xb가 어느 블록(첫 샘플 번호)의 것인지
static bool      s_xb_ok;                      // s_xb가 유효한가. 새 프레임이 들어오면 false로 지운다

/* ── 창과 배경 ── */
static win_t     s_win[NWIN];
static spec_t    s_bg;                         // 사용 중인 배경 (평균)
static spec_t    s_learn;                      // 배우는 중인 배경 (합)
static bool      s_bg_ready, s_learning, s_bg_req;   // 배경 있음 / 배우는 중 / 다음 프레임부터 배우라는 요청 (B1 버튼·부팅)
static uint32_t  s_bg_s0, s_learn_s0, s_learn_blk;   // 쓰는 배경의 시작 샘플 / 배우는 배경의 시작 샘플 / 지금까지 더한 배경 블록 수

static bool      s_started;                    // 재시작 뒤 시간축이 정해짐
static uint32_t  s_next_s0;                    // 다음 창의 첫 샘플

/* 부팅 시 한 번: FFT·창·방향 행렬·회전 표를 만들고, 첫 재시작 때 배경을 배우도록 해 둔다.
 * 이 함수를 부르지 않고 doa_push를 쓰면 FFT 설정이 비어 있어 동작하지 않는다 (app_init의 STREAM 분기에서 불러야 함). */
void doa_init(void)
{
	arm_rfft_fast_init_f32(&s_fft, DOA_NFFT);

	// np.hanning(512): 0.5 - 0.5 cos(2π n / (N - 1))
	for (uint32_t i = 0; i < DOA_BLOCK; i++)
		s_hann[i] = 0.5f - 0.5f * cosf(2.0f * PI * (float32_t)i / (float32_t)(DOA_BLOCK - 1u));

	// 마이크 좌표 → 최소제곱 행렬 (tdoa.c와 같은 식)
	//  평면파 가정: 방향 단위벡터 u(음원 쪽)에 대해 마이크 위치 r의 도착 시각은 −(r·u)/c.
	//  → 쌍 p의 시간차 tau_p = −(r_j − r_i)·u / c, 즉 a_p·u = −c·tau_p (a_p = r_j − r_i).
	//  식 3개(쌍 3개), 미지수 2개(ux, uy) → 최소제곱 해 u = (AᵀA)⁻¹Aᵀ b. 그 행렬 (AᵀA)⁻¹Aᵀ 를 s_solve에 미리 계산해 둔다.
	static const float32_t mic_deg[DOA_CH] = {0.0f, 120.0f, -120.0f};   // MIC1·2·3이 중심에서 놓인 각도
	const float32_t radius = DOA_SPACING_M / sqrtf(3.0f);              // 정삼각형 한 변 7 cm → 중심에서 꼭짓점까지 4.04 cm
	float32_t pos[DOA_CH][2], a[DOA_PAIRS][2];
	for (uint32_t m = 0; m < DOA_CH; m++) {
		const float32_t ang = (DOA_MIC_CW ? -mic_deg[m] : mic_deg[m]) * PI / 180.0f;
		pos[m][0] = radius * cosf(ang);
		pos[m][1] = radius * sinf(ang);
	}
	float32_t gxx = 0.0f, gxy = 0.0f, gyy = 0.0f;    // AᵀA의 세 성분 (2×2 대칭 행렬)
	for (uint32_t p = 0; p < DOA_PAIRS; p++) {
		a[p][0] = pos[pair_j[p]][0] - pos[pair_i[p]][0];
		a[p][1] = pos[pair_j[p]][1] - pos[pair_i[p]][1];
		gxx += a[p][0] * a[p][0]; gxy += a[p][0] * a[p][1]; gyy += a[p][1] * a[p][1];
	}
	const float32_t det = gxx * gyy - gxy * gxy;
	for (uint32_t p = 0; p < DOA_PAIRS; p++) {
		s_solve[0][p] = ( gyy * a[p][0] - gxy * a[p][1]) / det;
		s_solve[1][p] = (-gxy * a[p][0] + gxx * a[p][1]) / det;
	}

	// 채널 고유 지연: tau_ij(측정) = tau_ij(실제) + (d_j - d_i) → 빼서 보정
	const float32_t d_us[DOA_CH] = {DOA_DELAY_US_CH1, DOA_DELAY_US_CH2, DOA_DELAY_US_CH3};
	for (uint32_t p = 0; p < DOA_PAIRS; p++)
		s_delay[p] = (d_us[pair_j[p]] - d_us[pair_i[p]]) * 1e-6f * DOA_FS;

	// 탐색 지연 범위: 간격 / 음속 + 1 샘플 (doa_stream.py max_lag)
	s_m = (int32_t)roundf((DOA_SPACING_M / DOA_SOUND_SPEED * DOA_FS + 1.0f) * (float32_t)DOA_UP);
	if (s_m > MAXM)
		s_m = MAXM;
	// 회전 표: 지연 τ = l/16 샘플의 상관을 구하려면 빈 k마다 e^{j·2π·k·τ/NFFT}를 곱해야 한다.
	// 매번 cos/sin을 부르지 않도록, 첫 빈의 값(s_rot0)과 빈 하나 넘어갈 때 곱할 값(s_rot)만 저장하고
	// phat_peaks에서 복소수 곱셈으로 다음 빈의 값을 만들어 간다.
	for (int32_t l = 0; l <= s_m; l++) {
		const float32_t th = 2.0f * PI * (float32_t)l / (float32_t)(DOA_NFFT * DOA_UP);
		s_rot[l][0] = cosf(th);                  s_rot[l][1] = sinf(th);
		s_rot0[l][0] = cosf(th * (float32_t)K_LO); s_rot0[l][1] = sinf(th * (float32_t)K_LO);
	}

	memset(s_win, 0, sizeof(s_win));
	s_bg_ready = s_learning = false;
	s_bg_req = true;                            // 부팅 후 첫 재시작에서 배경을 배운다
	s_started = false;
	s_xb_ok = false;
}

/* B1 버튼(ISR)에서 호출: 다음 프레임부터 배경을 다시 배운다. 플래그만 세우고 실제 작업은 doa_push(main)가 한다 */
void doa_request_bg(void) { s_bg_req = true; }

// 블록 [start, start + 512) 의 세 채널 대역 스펙트럼 → s_xb
//  1) 링에서 512샘플을 꺼내 평균(DC)을 빼고 Hann 창을 곱한다
//  2) 뒤 512칸을 0으로 채워 1024점 FFT (0 채움: 순환 상관이 앞뒤로 겹쳐 섞이지 않게 하고, 빈 간격을 12.2 Hz로 촘촘하게)
//  3) 대역 안 빈(K_LO ~ K_HI)만 s_xb로 복사. 대역 밖은 버린다
static void block_spectrum(
	uint32_t start	// 블록의 첫 샘플 번호 (PCM 시간축). 링 위치는 start & 1023
)
{
	if (s_xb_ok && s_xb_start == start)
		return;                                 // 배경과 창의 블록이 겹치면 다시 계산하지 않는다
	for (uint32_t c = 0; c < DOA_CH; c++) {
		float32_t mean = 0.0f;
		for (uint32_t i = 0; i < DOA_BLOCK; i++) {
			s_fin[i] = (float32_t)s_ring[c][(start + i) & (RING - 1u)];
			mean += s_fin[i];
		}
		mean /= (float32_t)DOA_BLOCK;
		for (uint32_t i = 0; i < DOA_BLOCK; i++)
			s_fin[i] = (s_fin[i] - mean) * s_hann[i];
		memset(&s_fin[DOA_BLOCK], 0, (DOA_NFFT - DOA_BLOCK) * sizeof(float32_t));
		arm_rfft_fast_f32(&s_fft, s_fin, s_fout, 0);   // 마지막 인자 0 = 정방향 FFT
		memcpy(s_xb[c], &s_fout[2u * K_LO], sizeof(s_xb[c]));   // s_fout[2k], [2k+1] = 빈 k의 (re, im)
	}
	s_xb_start = start;
	s_xb_ok = true;
}

// 블록 하나(s_xb)를 합 s에 더한다 (창 합 또는 배경 합)
//  교차: X_j · conj(X_i) = (a + jb)(c − jd) = (ac + bd) + j(bc − ad)   (a,b = X_j의 re,im / c,d = X_i의 re,im)
//  자기: |X|² = re² + im²
//  여러 블록을 더하면 소리가 계속 같은 방향에서 오는 성분(위상이 일정)은 쌓이고, 잡음(위상이 제멋대로)은 서로 상쇄된다
static void accumulate(
	spec_t *s	// 더해 넣을 합: 진행 중인 창의 w->sum 또는 배우는 중인 배경 s_learn
)
{
	for (uint32_t p = 0; p < DOA_PAIRS; p++) {
		const float32_t (*xi)[2] = s_xb[pair_i[p]], (*xj)[2] = s_xb[pair_j[p]];
		for (uint32_t k = 0; k < NB; k++) {
			s->cr[p][k][0] += xj[k][0] * xi[k][0] + xj[k][1] * xi[k][1];
			s->cr[p][k][1] += xj[k][1] * xi[k][0] - xj[k][0] * xi[k][1];
		}
	}
	for (uint32_t c = 0; c < DOA_CH; c++)
		for (uint32_t k = 0; k < NB; k++)
			s->au[c][k] += s_xb[c][k][0] * s_xb[c][k][0] + s_xb[c][k][1] * s_xb[c][k][1];
}

// 교차 스펙트럼 R(대역 안) → PHAT 가중 → s_ph[p]
//  PHAT: 빈마다 R / |R| — 크기를 1로 맞추고 위상만 남긴다. 큰 저음 하나가 상관을 지배하지 않고 봉우리가 날카로워진다.
//  대가로 잡음뿐인 빈도 같은 무게를 받는다 (대역 상한을 함부로 넓히면 안 되는 이유).
//  eps = 대역 최대 크기의 1% : |R|이 거의 0인 빈을 1로 키워 잡음을 부풀리지 않게 하는 바닥값
static void phat_weight(
	const float32_t r[NB][2],	// 한 쌍의 평균 교차 스펙트럼 (배경 뺀 뒤), 대역 안 빈 221개 × (re, im)
	float32_t ph[NB][2]			// 결과: 크기를 1로 맞춘 교차 스펙트럼 (s_ph[p])
)
{
	float32_t mmax = 0.0f;
	for (uint32_t k = 0; k < NB; k++) {
		const float32_t m = sqrtf(r[k][0] * r[k][0] + r[k][1] * r[k][1]);
		ph[k][0] = m;
		if (m > mmax)
			mmax = m;
	}
	const float32_t eps = DOA_PHAT_EPS * mmax + 1e-30f;
	for (uint32_t k = 0; k < NB; k++) {
		const float32_t s = 1.0f / (ph[k][0] + eps);
		ph[k][0] = r[k][0] * s;
		ph[k][1] = r[k][1] * s;
	}
}

/* 세 쌍의 PHAT 상관을 지연 -M..M (1/DOA_UP 간격)에서 계산 → 쌍마다 피크 + 2차 보간
 * cc(τ) = (1/NB) Σ_k Re(P_k e^{j2πkτ/NFFT})  = irfft(P, NFFT·UP) × NFFT·UP / (2·NB) 의 τ = l/UP 값
 * C(l) = Σ Re(P_k)·cos, S(l) = Σ Im(P_k)·sin 로 나누면 cc(+l) = C − S, cc(−l) = C + S → l ≥ 0만 돈다 */
static void phat_peaks(
	float32_t tau[DOA_PAIRS],	// 결과: 쌍별 시간차 [샘플 @12.5 kHz], 보간 후. 채널 지연 보정 전
	float32_t peak[DOA_PAIRS]	// 결과: 쌍별 상관 봉우리 높이 (0 ~ 1)
)
{
	static float32_t cc[DOA_PAIRS][2 * MAXM + 1];
	const float32_t inv_nb = 1.0f / (float32_t)NB;
	for (int32_t l = 0; l <= s_m; l++) {
		const float32_t wr = s_rot[l][0], wi = s_rot[l][1];
		float32_t zr = s_rot0[l][0], zi = s_rot0[l][1];
		float32_t c0 = 0.0f, c1 = 0.0f, c2 = 0.0f, q0 = 0.0f, q1 = 0.0f, q2 = 0.0f;
		for (uint32_t k = 0; k < NB; k++) {
			c0 += s_ph[0][k][0] * zr; q0 += s_ph[0][k][1] * zi;
			c1 += s_ph[1][k][0] * zr; q1 += s_ph[1][k][1] * zi;
			c2 += s_ph[2][k][0] * zr; q2 += s_ph[2][k][1] * zi;
			const float32_t t = zr * wr - zi * wi;
			zi = zr * wi + zi * wr;
			zr = t;
		}
		cc[0][s_m + l] = (c0 - q0) * inv_nb; cc[0][s_m - l] = (c0 + q0) * inv_nb;
		cc[1][s_m + l] = (c1 - q1) * inv_nb; cc[1][s_m - l] = (c1 + q1) * inv_nb;
		cc[2][s_m + l] = (c2 - q2) * inv_nb; cc[2][s_m - l] = (c2 + q2) * inv_nb;
	}

	// 쌍마다 가장 큰 상관 칸(best)을 찾고, 양옆 칸과 함께 포물선을 맞춰 칸 사이의 진짜 꼭짓점을 구한다 (2차 보간).
	// 칸 간격이 이미 1/16 샘플이라 보간은 그보다 더 잘게 다듬는 정도다. 결과 단위는 샘플 (lag / 16).
	const int32_t n = 2 * s_m + 1;
	for (uint32_t p = 0; p < DOA_PAIRS; p++) {
		const float32_t *c = cc[p];
		int32_t best = 0;
		for (int32_t i = 1; i < n; i++)
			if (c[i] > c[best])
				best = i;                       // 같으면 앞쪽 (np.argmax)
		float32_t lag = (float32_t)(best - s_m), pk = c[best];
		if (best > 0 && best < n - 1) {
			const float32_t y0 = c[best - 1], y1 = c[best], y2 = c[best + 1];
			const float32_t d = y0 - 2.0f * y1 + y2;
			if (d < 0.0f) {
				const float32_t f = 0.5f * (y0 - y2) / d;
				lag += f;
				pk = y1 - 0.25f * (y0 - y2) * f;
			}
		}
		tau[p] = lag / (float32_t)DOA_UP;
		peak[p] = pk;
	}
}

/* 블록이 다 찬 창 하나로 방위를 계산한다 (창이 끝나는 프레임에서만, 약 0.25 s마다 한 번)
 *  ① 배경 대비 소리 크기(SNR) → PRESENT 판정
 *  ② 쌍마다: 창 평균 교차 스펙트럼 − 배경 평균 → PHAT → 상관 봉우리 = 시간차
 *  ③ 채널 고유 지연 보정 → 최소제곱 방향 벡터 → 방위각·norm
 *  ④ 유효 판정 (봉우리 높이, 닫힘, norm) → VALID
 * 이 프레임은 평소보다 무겁다 (CPU 최대값이 여기서 나온다). */
static void finalize(
	const win_t *w,		// 블록 23개가 다 찬 창 (w->sum = 블록 스펙트럼 합)
	doa_result_t *out	// 결과를 채울 곳 (doa_push의 out 그대로)
)
{
	static float32_t r[NB][2];                 // 한 쌍의 평균 교차 스펙트럼 (배경 뺀 뒤). static: 스택 1.7 KB를 아끼려고
	const uint32_t t0 = doa_now_cycles();
	const float32_t inv = 1.0f / (float32_t)w->nblk;   // 합 → 평균
	uint8_t flags = 0u;

	// ① 배경 대비 대역 전력: (창 평균 자기 전력 합) / (배경 평균 자기 전력 합) [dB].
	//    6 dB 이상이면 "평소보다 새 소리가 있다"(PRESENT). 배경이 없으면 비교할 수 없으니 항상 PRESENT
	float32_t snr_db = 0.0f;
	if (s_bg_ready) {
		float32_t pw = 0.0f, pb = 0.0f;
		for (uint32_t c = 0; c < DOA_CH; c++)
			for (uint32_t k = 0; k < NB; k++) {
				pw += w->sum.au[c][k];
				pb += s_bg.au[c][k];
			}
		snr_db = 10.0f * log10f(pw * inv / pb);
		flags |= DOA_FLAG_BG;
		if (snr_db >= DOA_MIN_SNR_DB)
			flags |= DOA_FLAG_PRESENT;
	} else {
		flags |= DOA_FLAG_PRESENT;
	}
	if (s_learning)
		flags |= DOA_FLAG_LEARNING;

	// ② 배경 빼기 + PHAT. 배경 교차 스펙트럼 = 세 마이크에 공통으로 들어오는 평소 소리(방 잡음, 보드 간섭).
	//    이걸 빼지 않으면 공통 잡음이 시간차를 0 쪽으로 끌어당긴다 (D0에서 norm 0.33).
	//    복소수 그대로 빼므로, 같은 방향에서 꾸준히 오던 소리만 지워지고 새 음원의 위상은 남는다
	for (uint32_t p = 0; p < DOA_PAIRS; p++) {
		for (uint32_t k = 0; k < NB; k++) {
			r[k][0] = w->sum.cr[p][k][0] * inv;
			r[k][1] = w->sum.cr[p][k][1] * inv;
			if (s_bg_ready) {
				r[k][0] -= s_bg.cr[p][k][0];
				r[k][1] -= s_bg.cr[p][k][1];
			}
		}
		phat_weight(r, s_ph[p]);
	}
	phat_peaks(out->tau, out->peak);
	// ③ 채널 고유 지연 보정: 측정된 시간차에는 앰프·배선 차이로 생긴 채널 간 지연(ch2 −23.1 µs 등)이 섞여 있다 → 뺀다
	for (uint32_t p = 0; p < DOA_PAIRS; p++)
		out->tau[p] -= s_delay[p];

	// 시간차 [샘플] → 경로 차 [m]: b_p = −c·tau_p / fs. 최소제곱 행렬을 곱하면 방향 벡터 (ux, uy)
	float32_t ux = 0.0f, uy = 0.0f;
	for (uint32_t p = 0; p < DOA_PAIRS; p++) {
		const float32_t b = -DOA_SOUND_SPEED * out->tau[p] / DOA_FS;
		ux += s_solve[0][p] * b;
		uy += s_solve[1][p] * b;
	}
	out->angle_deg = atan2f(uy, ux) * 180.0f / PI;   // MIC1 방향 0°, 반시계 + (−180 ~ 180)
	out->norm = sqrtf(ux * ux + uy * uy);            // 수평으로 오면 1, 위에서 올수록 작아짐 (≈ cos 고도각)

	// ④ 유효 판정 — 세 가지가 모두 맞아야 VALID
	//  - 세 쌍 중 가장 낮은 봉우리 ≥ 0.15 : 상관이 뚜렷한가
	//  - 닫힘 |tau12 + tau23 − tau13| ≤ 0.3샘플 : 삼각형을 한 바퀴 돈 시간차 합은 0이어야 한다. 크면 봉우리 하나가 가짜
	//  - norm 0.5 ~ 1.3 : 물리적으로 가능한 방향 벡터 길이인가 (0.5 = 고도 60°)
	float32_t pmin = out->peak[0];
	for (uint32_t p = 1; p < DOA_PAIRS; p++)
		if (out->peak[p] < pmin)
			pmin = out->peak[p];
	const float32_t closure = out->tau[0] + out->tau[2] - out->tau[1];
	if (pmin >= DOA_MIN_PEAK && fabsf(closure) <= DOA_MAX_CLOSURE &&
	    out->norm >= DOA_MIN_NORM && out->norm <= DOA_MAX_NORM)
		flags |= DOA_FLAG_VALID;

	out->s0 = w->s0;
	out->snr_db = snr_db;
	out->flags = flags;
	out->bg_s0 = s_bg_ready ? s_bg_s0 : 0u;
	out->bg_n = s_bg_ready ? BG_N : 0u;
	out->proc_us = (doa_now_cycles() - t0) / DOA_CPU_MHZ;      // 부호 없는 뺄셈이라 카운터가 한 바퀴 돌아도 맞다
}

/* 프레임 하나를 넣는다 (app.c on_stream_frame에서 매 프레임). 창이 끝나면 out을 채우고 true */
bool doa_push(
	const int16_t pcm[DOA_CH][DOA_FRAME],	// 전처리 출력 int16[3][256] (12.5 kHz, 프레임 하나)
	uint32_t frame_seq,						// 이 프레임 번호. 첫 샘플 번호 = (frame_seq − 1) × 256
	bool restart,							// 이 프레임 앞에서 MCU 입력이 끊겼음 (RESYNC) → 진행 중인 창을 버리고 새로 시작
	doa_result_t *out						// 창이 끝났을 때 결과를 쓸 곳 (반환이 true일 때만 유효)
)
{
	const uint32_t a0 = (frame_seq - 1u) * DOA_FRAME;     // 이 프레임 첫 샘플 번호
	const uint32_t n_abs = a0 + DOA_FRAME;                // 여기까지 받음 (미포함)

	// 1) 링버퍼에 쓰기. 위치 = 샘플 번호 & 1023 → 1024샘플 전의 데이터를 덮어쓴다
	for (uint32_t c = 0; c < DOA_CH; c++)
		for (uint32_t i = 0; i < DOA_FRAME; i++)
			s_ring[c][(a0 + i) & (RING - 1u)] = pcm[c][i];
	s_xb_ok = false;                                      // 블록 스펙트럼 캐시는 한 프레임 안에서만 쓴다

	// 2) 재시작: 입력이 끊겼거나(ADC 유실·overrun) 부팅 직후. 이 프레임은 FIR 과도 구간이 섞여 있으니 버리고,
	//    다음 프레임 첫 샘플부터 창을 새로 센다. 배워 둔 배경은 유지하고, 배우던 중이었으면 처음부터 다시 배운다
	if (restart || !s_started) {
		// 이 프레임은 FIR 과도 구간을 포함 → 다음 프레임부터 새 시간축
		memset(s_win, 0, sizeof(s_win));
		if (s_learning)
			s_bg_req = true;                    // 끊긴 배경은 처음부터 다시
		s_learning = false;
		s_started = true;
		s_next_s0 = n_abs;
		return false;
	}

	// 3) 배경 배우기 시작 (부팅 직후 첫 정상 프레임, 또는 B1 버튼). 이 프레임 첫 샘플부터 10 s.
	//    배우는 동안에도 기존 배경(있다면)으로 창 계산은 계속한다
	if (s_bg_req) {
		memset(&s_learn, 0, sizeof(s_learn));
		s_learning = true;
		s_learn_s0 = a0;
		s_learn_blk = 0u;
		s_bg_req = false;
	}

	// 4) 배경 블록: 끝이 n_abs 안에 들어온(= 다 받은) 블록을 더한다. 프레임마다 보통 하나
	while (s_learning && s_learn_blk < BG_NBLK && s_learn_s0 + s_learn_blk * BHOP + DOA_BLOCK <= n_abs) {
		block_spectrum(s_learn_s0 + s_learn_blk * BHOP);
		accumulate(&s_learn);
		s_learn_blk++;
	}
	// 487블록을 다 더했으면 평균을 내서 사용 중인 배경(s_bg)으로 바꾼다. spec_t 전체를 float 배열로 보고 한 번에 나눈다
	if (s_learning && s_learn_blk == BG_NBLK) {
		const float32_t inv = 1.0f / (float32_t)BG_NBLK;
		float32_t *dst = (float32_t *)&s_bg;
		const float32_t *src = (const float32_t *)&s_learn;
		for (uint32_t i = 0; i < sizeof(spec_t) / sizeof(float32_t); i++)
			dst[i] = src[i] * inv;
		s_bg_s0 = s_learn_s0;
		s_bg_ready = true;
		s_learning = false;
	}

	// 5) 창 진행. 창은 s_next_s0부터 3072샘플(12프레임)마다 하나씩 시작하고, 블록 23개(24프레임 분량)가 차면 끝난다.
	//    그래서 같은 시각에 진행 중인 창은 최대 2개(NWIN)다.
	//    각 칸에서: 새 창 시작 → 다 받은 블록을 더함 → 23개가 되면 finalize. 한 프레임에 끝나는 창은 하나뿐이다 (done)
	// 새 창 시작 (끝난 창 자리를 먼저 비우도록 블록 처리 뒤에도 한 번 더 본다)
	bool done = false;
	for (uint32_t pass = 0; pass < 2u; pass++) {
		for (uint32_t s = 0; s < NWIN && s_next_s0 < n_abs; s++) {
			if (s_win[s].used)
				continue;
			memset(&s_win[s], 0, sizeof(win_t));
			s_win[s].used = true;
			s_win[s].s0 = s_next_s0;
			s_next_s0 += DOA_HOP;
		}
		for (uint32_t s = 0; s < NWIN; s++) {
			win_t *w = &s_win[s];
			if (!w->used)
				continue;
			if (w->s0 + w->nblk * BHOP + RING < n_abs) {   // 링에서 이미 덮어쓴 구간 (일어나면 안 됨)
				w->used = false;
				continue;
			}
			while (w->nblk < NBLK && w->s0 + w->nblk * BHOP + DOA_BLOCK <= n_abs) {
				block_spectrum(w->s0 + w->nblk * BHOP);
				accumulate(&w->sum);
				w->nblk++;
			}
			if (w->nblk == NBLK && !done) {
				finalize(w, out);
				w->used = false;
				done = true;
			}
		}
	}
	return done;
}
