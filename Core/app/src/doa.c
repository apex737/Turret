#include "doa.h"
#include "arm_math.h"
#include <string.h>

// 대역 [LO, HI] Hz 에 들어가는 FFT 빈 (빈 k의 주파수 = k x fs / NFFT). doa_stream.py와 같은 포함 규칙(LO ≤ f ≤ HI)
#define K_LO      25u                                   // ceil(300 x 1024 / 12500)  = ceil(24.6)
#define K_HI      245u                                  // floor(3000 x 1024 / 12500) = floor(245.8)
#define NB        (K_HI - K_LO + 1u)                    // 221
#define BHOP      (DOA_BLOCK / 2u)                      // 블록 50% 겹침 → 256
#define NBLK      ((DOA_OBS - DOA_BLOCK) / BHOP + 1u)   // 창 하나의 블록 수 = 23
#define BG_N      (DOA_BG_SECONDS * 12500u)             // 배경 길이 [샘플]
#define BG_NBLK   ((BG_N - DOA_BLOCK) / BHOP + 1u)      // 배경 블록 수 (10 s → 487)
#define RING      1024u                                 // 링버퍼 [샘플/채널]. 가장 오래 기다리는 블록 = 512 + 256 이내
#define NWIN      2u                                    // 동시에 진행하는 창 (창 w는 w+2가 시작하기 전에 끝난다)
#define MAXM      64                                    // 상관 지연 칸 수의 절반 상한 (실제 M = 57)

_Static_assert(BHOP == DOA_FRAME, "block hop must equal the frame size (one new block per frame and window)");
_Static_assert(DOA_HOP > DOA_FRAME, "at most one window may finish per frame");
_Static_assert(DOA_OBS - DOA_BLOCK - (NBLK - 1u) * BHOP < DOA_HOP, "window w must finish before window w+2 starts");
_Static_assert(RING >= DOA_BLOCK + 2u * DOA_FRAME, "ring too small");
_Static_assert(DOA_HOP % BHOP == 0u, "window hop must be a multiple of the block hop (overlapping windows share block FFTs)");
_Static_assert((RING & (RING - 1u)) == 0u, "ring must be a power of two");

static const uint8_t pair_i[DOA_PAIRS] = {0, 0, 1};
static const uint8_t pair_j[DOA_PAIRS] = {1, 2, 2};

// 스펙트럼 합 (대역 안 빈만): 세 쌍의 교차 X_j·conj(X_i) (re, im) + 세 채널의 자기 |X|²
typedef struct {
	float32_t cr[DOA_PAIRS][NB][2];
	float32_t au[DOA_CH][NB];
} spec_t;

typedef struct {
	bool     used;
	uint32_t s0;
	uint32_t nblk;
	spec_t   sum;
} win_t;

static arm_rfft_fast_instance_f32 s_fft;
static float32_t s_hann[DOA_BLOCK];
static float32_t s_solve[2][DOA_PAIRS];        // 지연 → 방향 벡터 최소제곱 행렬
static float32_t s_delay[DOA_PAIRS];           // 쌍별 채널 지연 보정 [샘플]
static int32_t   s_m;                          // 상관 지연 범위 ±s_m / DOA_UP 샘플
static float32_t s_rot[MAXM + 1][2];           // 지연 l/DOA_UP 의 빈 간 회전 e^{jθ}, θ = 2π l / (NFFT·UP)
static float32_t s_rot0[MAXM + 1][2];          // 첫 빈(K_LO)의 회전 e^{jθ·K_LO}
static float32_t s_ph[DOA_PAIRS][NB][2];       // 세 쌍의 PHAT 가중 교차 스펙트럼

static int16_t   s_ring[DOA_CH][RING];
static float32_t s_fin[DOA_NFFT];              // FFT 입력 (계산 중 덮어써짐)
static float32_t s_fout[DOA_NFFT];             // FFT 출력 (re, im 교대. [0]=DC, [1]=Nyquist)
static float32_t s_xb[DOA_CH][NB][2];          // 블록 하나의 대역 스펙트럼
static uint32_t  s_xb_start;
static bool      s_xb_ok;

static win_t     s_win[NWIN];
static spec_t    s_bg;                         // 사용 중인 배경 (평균)
static spec_t    s_learn;                      // 배우는 중인 배경 (합)
static bool      s_bg_ready, s_learning, s_bg_req;
static uint32_t  s_bg_s0, s_learn_s0, s_learn_blk;

static bool      s_started;                    // 재시작 뒤 시간축이 정해짐
static uint32_t  s_next_s0;                    // 다음 창의 첫 샘플

void doa_init(void)
{
	arm_rfft_fast_init_f32(&s_fft, DOA_NFFT);

	// np.hanning(512): 0.5 - 0.5 cos(2π n / (N - 1))
	for (uint32_t i = 0; i < DOA_BLOCK; i++)
		s_hann[i] = 0.5f - 0.5f * cosf(2.0f * PI * (float32_t)i / (float32_t)(DOA_BLOCK - 1u));

	// 마이크 좌표 → 최소제곱 행렬 (tdoa.c와 같은 식)
	static const float32_t mic_deg[DOA_CH] = {0.0f, 120.0f, -120.0f};
	const float32_t radius = DOA_SPACING_M / sqrtf(3.0f);
	float32_t pos[DOA_CH][2], a[DOA_PAIRS][2];
	for (uint32_t m = 0; m < DOA_CH; m++) {
		const float32_t ang = (DOA_MIC_CW ? -mic_deg[m] : mic_deg[m]) * PI / 180.0f;
		pos[m][0] = radius * cosf(ang);
		pos[m][1] = radius * sinf(ang);
	}
	float32_t gxx = 0.0f, gxy = 0.0f, gyy = 0.0f;
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

void doa_request_bg(void) { s_bg_req = true; }

// 블록 [start, start + 512) 의 세 채널 대역 스펙트럼 → s_xb
static void block_spectrum(uint32_t start)
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
		arm_rfft_fast_f32(&s_fft, s_fin, s_fout, 0);
		memcpy(s_xb[c], &s_fout[2u * K_LO], sizeof(s_xb[c]));
	}
	s_xb_start = start;
	s_xb_ok = true;
}

static void accumulate(spec_t *s)
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
static void phat_weight(const float32_t r[NB][2], float32_t ph[NB][2])
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
static void phat_peaks(float32_t tau[DOA_PAIRS], float32_t peak[DOA_PAIRS])
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

static void finalize(const win_t *w, doa_result_t *out)
{
	static float32_t r[NB][2];
	const uint32_t t0 = doa_now_cycles();
	const float32_t inv = 1.0f / (float32_t)w->nblk;
	uint8_t flags = 0u;

	// 배경 대비 대역 전력
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
	for (uint32_t p = 0; p < DOA_PAIRS; p++)
		out->tau[p] -= s_delay[p];

	float32_t ux = 0.0f, uy = 0.0f;
	for (uint32_t p = 0; p < DOA_PAIRS; p++) {
		const float32_t b = -DOA_SOUND_SPEED * out->tau[p] / DOA_FS;
		ux += s_solve[0][p] * b;
		uy += s_solve[1][p] * b;
	}
	out->angle_deg = atan2f(uy, ux) * 180.0f / PI;
	out->norm = sqrtf(ux * ux + uy * uy);

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

bool doa_push(const int16_t pcm[DOA_CH][DOA_FRAME], uint32_t frame_seq, bool restart, doa_result_t *out)
{
	const uint32_t a0 = (frame_seq - 1u) * DOA_FRAME;     // 이 프레임 첫 샘플 번호
	const uint32_t n_abs = a0 + DOA_FRAME;                // 여기까지 받음 (미포함)

	for (uint32_t c = 0; c < DOA_CH; c++)
		for (uint32_t i = 0; i < DOA_FRAME; i++)
			s_ring[c][(a0 + i) & (RING - 1u)] = pcm[c][i];
	s_xb_ok = false;

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

	if (s_bg_req) {
		memset(&s_learn, 0, sizeof(s_learn));
		s_learning = true;
		s_learn_s0 = a0;
		s_learn_blk = 0u;
		s_bg_req = false;
	}

	// 배경 블록
	while (s_learning && s_learn_blk < BG_NBLK && s_learn_s0 + s_learn_blk * BHOP + DOA_BLOCK <= n_abs) {
		block_spectrum(s_learn_s0 + s_learn_blk * BHOP);
		accumulate(&s_learn);
		s_learn_blk++;
	}
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
