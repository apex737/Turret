/*
 * harm.c : MIC1 PCM → 고조파 점수 B0 (Step8b 이식, 규약은 harm.h)
 *
 *  흐름 (입력 프레임 256샘플마다 harm_push)
 *    1) MIC1 샘플을 2048 링에 쓰고, 1024샘플 묶음(hop)마다 합·제곱합을 남긴다 (창 RMS용)
 *    2) 1024샘플이 새로 차면 프레임 하나 계산 (DOA 창이 끝난 프레임이면 다음 호출로 미룸)
 *         평균 빼기·Hann → 1024점 복소 FFT(제자리) → 실수 FFT 합치기로 빈 0 ~ 476 전력 P
 *         → 33빈 중앙값 바닥 → SNR → ±1빈 최대 → pk = clip(SNR − 1, 0, 9) → 진행 중인 창 누적(acc)에 더함
 *    3) 창의 마지막 프레임(11번째)을 더하면 f0 40 ~ 700 Hz마다 Σ고조파 acc ÷ 11의 최댓값 → 결과
 *  창 누적은 동시에 둘까지 (프레임 6개마다 시작, 11개 길이)
 */
#include "harm.h"
#include "harm_hann.h"
#include "doa.h"
#include "arm_math.h"
#include "arm_const_structs.h"
#include "arm_common_tables.h"
#include <string.h>
#include <math.h>

// 빈 범위: f0 후보와 고조파가 쓰는 빈 = round(h·f0 ÷ Δf), Δf = 12500 ÷ 2048 = 6.1035 Hz
#define KLO     7u                       // round(1 × 40 ÷ 6.1035) = round(6.55)
#define KHI     459u                     // round(4 × 700 ÷ 6.1035) = round(458.75)
#define NK      (KHI - KLO + 1u)         // 453 : 누적할 빈 수
#define SLO     (KLO - 1u)               // SNR이 필요한 빈 (±1빈 최대 때문에 한 칸씩 더)
#define SHI     (KHI + 1u)
#define HALF    (HARM_FLOOR_BINS / 2u)   // 16 : 바닥 중앙값의 한쪽 이웃 수
#define NP      (SHI + HALF + 1u)        // 477 : 전력 P가 필요한 빈 0 ~ 476
#define SNR_AT  512u                     // 작업 공간에서 SNR을 둘 자리 (P는 앞 477칸)
#define NHOP    16u                      // hop 통계 링 칸 수 (창 하나 = hop 12개)
#define WIN_N   (HARM_NFFT + (HARM_NFR - 1u) * HARM_HOP)   // 12288 : 창 길이 [샘플]

_Static_assert(KHI + HALF < HARM_NFFT / 2u, "P bins must stay below Nyquist");
_Static_assert(NP <= SNR_AT && SNR_AT + (SHI - SLO + 1u) <= HARM_NFFT, "scratch layout: P [0, NP), SNR [SNR_AT, ...) inside 2048 floats");

static int16_t  s_ring[HARM_NFFT];        // MIC1 최근 2048샘플 (위치 = 받은 샘플 수 % 2048)
static uint32_t s_got;                    // 재시작 뒤 받은 샘플 수
static uint32_t s_base;                   // 재시작 뒤 첫 샘플 번호 (PCM 시간축)
static bool     s_started;                // false면 다음 프레임이 재시작 프레임
static bool     s_pending;                // 계산할 프레임이 미뤄져 있음
static uint32_t s_pend_j;                 // 미룬 프레임 번호 (재시작 뒤 0부터)
static bool     s_first_win;              // 재시작 뒤 첫 창 (결과에 HARM_FLAG_RESTART)
static float32_t s_acc[2][NK];            // 진행 중인 창 두 개의 빈별 pk 합. 칸 = 창 번호 % 2
static float32_t s_hsum[NHOP], s_hsq[NHOP];   // hop별 샘플 합·제곱합 (칸 = hop 번호 % 16)
static float32_t s_cur_sum, s_cur_sq;     // 지금 채우는 hop의 합·제곱합
static uint32_t s_proc_max;               // 마지막 결과 뒤 프레임 계산 한 번의 최대 사이클

void harm_init(void)
{
	s_started = false;
	s_pending = false;
}

static void restart_at(uint32_t base)
{
	s_base = base;
	s_got = 0u;
	s_pending = false;
	s_first_win = true;
	s_cur_sum = s_cur_sq = 0.0f;
	s_proc_max = 0u;
	memset(s_acc, 0, sizeof(s_acc));
}

/* 정렬된 33칸 배열 w에서 값 v 하나를 빼고(같은 값의 첫 자리) 값 u를 넣는다 → 중앙값 = w[16] */
static void win_replace(float32_t *w, float32_t v, float32_t u)
{
	uint32_t i = 0u;
	while (i < HARM_FLOOR_BINS - 1u && w[i] != v)
		i++;
	for (; i < HARM_FLOOR_BINS - 1u; i++)          // v 자리를 지우고 뒤를 당긴다
		w[i] = w[i + 1u];
	i = HARM_FLOOR_BINS - 1u;
	while (i > 0u && w[i - 1u] > u) {               // u가 들어갈 자리까지 뒤로 민다
		w[i] = w[i - 1u];
		i--;
	}
	w[i] = u;
}

/* 프레임 j(재시작 뒤 0부터) 하나를 계산해 진행 중인 창에 더한다. 창이 끝나면 out을 채우고 true
 *  j : 프레임 번호. 이 프레임 = 샘플 [s_base + 1024·j, +2048), 링에서 위치 (1024·j + i) % 2048
 *  부작용: doa_scratch() 8 KB를 덮어쓴다 (doa_push 밖에서만 부를 것), s_acc 갱신 */
static bool process(uint32_t j, harm_result_t *out)
{
	const uint32_t t0 = doa_now_cycles();
	float32_t *b = doa_scratch();
	const uint32_t r0 = (j * HARM_HOP) % HARM_NFFT;

	// 1) 평균(DC) 빼기 + Hann (np.hanning 2048, 대칭이라 표는 앞 절반)
	float32_t mean = 0.0f;
	for (uint32_t i = 0; i < HARM_NFFT; i++)
		mean += (float32_t)s_ring[(r0 + i) % HARM_NFFT];
	mean /= (float32_t)HARM_NFFT;
	for (uint32_t i = 0; i < HARM_NFFT / 2u; i++) {
		b[i] = ((float32_t)s_ring[(r0 + i) % HARM_NFFT] - mean) * harm_hann[i];
		b[HARM_NFFT - 1u - i] = ((float32_t)s_ring[(r0 + HARM_NFFT - 1u - i) % HARM_NFFT] - mean) * harm_hann[i];
	}

	// 2) 실수 2048점 FFT = 짝·홀 샘플을 (re, im)으로 본 1024점 복소 FFT(제자리) + 합치기 (CMSIS stage_rfft_f32와 같은 식).
	//    합치기 결과는 출력 버퍼 없이 전력만 b[0 .. NP−1]에 쓴다. 빈 k의 계산은 b[2k..]와 b[2048−2k..]만 읽으므로,
	//    b[k](k < 2k)에 써도 아직 읽을 값을 덮지 않는다 (뒤쪽 b[2048−2k]는 k ≤ 476이라 1096 이상)
	arm_cfft_f32(&arm_cfft_sR_f32_len1024, b, 0u, 1u);
	const float32_t *tw = twiddleCoef_rfft_2048;
	{
		const float32_t dc = b[0] + b[1];          // X[0] = Re Z0 + Im Z0
		b[0] = dc * dc;
	}
	for (uint32_t k = 1u; k < NP; k++) {
		const float32_t ar = b[2u * k], ai = b[2u * k + 1u];
		const float32_t br = b[HARM_NFFT - 2u * k], bi = b[HARM_NFFT - 2u * k + 1u];
		const float32_t twr = tw[2u * k], twi = tw[2u * k + 1u];
		const float32_t t1a = br - ar, t1b = bi + ai;
		const float32_t xr = 0.5f * (ar + br + twr * t1a + twi * t1b);
		const float32_t xi = 0.5f * (ai - bi + twi * t1a - twr * t1b);
		b[k] = xr * xr + xi * xi;
	}

	// 3) 바닥 = 이웃 33빈(가장자리는 0번 빈 반복) 중앙값 ÷ ln2, SNR = P ÷ 바닥 → b[SNR_AT + (빈 − SLO)]
	float32_t w[HARM_FLOOR_BINS];
	for (uint32_t i = 0; i < HARM_FLOOR_BINS; i++) {
		const int32_t k = (int32_t)SLO - (int32_t)HALF + (int32_t)i;
		w[i] = b[k < 0 ? 0 : k];
	}
	for (uint32_t i = 1u; i < HARM_FLOOR_BINS; i++) {          // 삽입 정렬 (33개)
		const float32_t v = w[i];
		uint32_t m = i;
		while (m > 0u && w[m - 1u] > v) { w[m] = w[m - 1u]; m--; }
		w[m] = v;
	}
	const float32_t inv_ln2 = 1.0f / 0.69314718056f;
	for (uint32_t k = SLO; k <= SHI; k++) {
		if (k > SLO) {
			const int32_t out_k = (int32_t)k - (int32_t)HALF - 1;
			win_replace(w, b[out_k < 0 ? 0 : out_k], b[k + HALF]);
		}
		const float32_t floor_v = w[HALF] * inv_ln2;
		b[SNR_AT + (k - SLO)] = b[k] / (floor_v + 1e-30f);
	}

	// 4) pk = clip(±1빈 최대 − 1, 0, 9) → 이 프레임이 들어가는 창(최대 2개)에 더한다
	const uint32_t w_hi = j / HARM_WIN_HOP;                                     // 이 프레임을 포함하는 가장 늦은 창
	const uint32_t w_lo = (j >= HARM_NFR - 1u) ? (j - (HARM_NFR - 1u) + HARM_WIN_HOP - 1u) / HARM_WIN_HOP : 0u;
	if (j % HARM_WIN_HOP == 0u)
		memset(s_acc[w_hi % 2u], 0, sizeof(s_acc[0]));                     // 새 창 시작
	const float32_t *snr = &b[SNR_AT];
	for (uint32_t k = KLO; k <= KHI; k++) {
		float32_t m = snr[k - SLO];
		if (snr[k - SLO - 1u] > m) m = snr[k - SLO - 1u];
		if (snr[k - SLO + 1u] > m) m = snr[k - SLO + 1u];
		float32_t v = m - 1.0f;
		v = v < 0.0f ? 0.0f : (v > HARM_CAP - 1.0f ? HARM_CAP - 1.0f : v);
		for (uint32_t wi = w_lo; wi <= w_hi; wi++)
			s_acc[wi % 2u][k - KLO] += v;
	}

	const uint32_t cyc = doa_now_cycles() - t0;
	if (cyc > s_proc_max)
		s_proc_max = cyc;

	// 5) 창의 마지막 프레임이면 f0 탐색
	if (j < HARM_NFR - 1u || (j - (HARM_NFR - 1u)) % HARM_WIN_HOP != 0u)
		return false;
	const uint32_t wd = (j - (HARM_NFR - 1u)) / HARM_WIN_HOP;                 // 끝난 창 번호
	const float32_t *acc = s_acc[wd % 2u];
	const float32_t bin_per_hz = (float32_t)HARM_NFFT / HARM_FS;               // 1 ÷ Δf
	float32_t best = -1.0f, best_f0 = 0.0f;
	for (uint32_t c = HARM_F0_MIN; c <= HARM_F0_MAX; c++) {
		float32_t s = 0.0f;
		for (uint32_t h = 1u; h <= HARM_H; h++) {
			const uint32_t k = (uint32_t)floorf((float32_t)(h * c) * bin_per_hz + 0.5f);
			s += acc[k - KLO];
		}
		s /= (float32_t)HARM_NFR;
		if (s > best) { best = s; best_f0 = (float32_t)c; }
	}
	// 창 RMS: hop wd·6 ~ wd·6 + 11 (12개 = 12288샘플)
	float32_t sum = 0.0f, sq = 0.0f;
	for (uint32_t h = 0; h < WIN_N / HARM_HOP; h++) {
		sum += s_hsum[(wd * HARM_WIN_HOP + h) % NHOP];
		sq  += s_hsq[(wd * HARM_WIN_HOP + h) % NHOP];
	}
	const float32_t mu = sum / (float32_t)WIN_N;
	float32_t var = sq / (float32_t)WIN_N - mu * mu;
	if (var < 1e-6f) var = 1e-6f;

	out->s0 = s_base + wd * HARM_WIN_HOP * HARM_HOP;
	out->n = WIN_N;
	out->score = best;
	out->f0 = best_f0;
	out->rms_db = 10.0f * log10f(var) - 90.308999f;                         // 20·log10(32768) = 90.309
	out->frames = (uint16_t)HARM_NFR;
	const uint32_t us = s_proc_max / DOA_CPU_MHZ;
	out->proc_us = (uint16_t)(us > 0xFFFFu ? 0xFFFFu : us);
	out->flags = (uint8_t)((best >= HARM_THR ? HARM_FLAG_POS : 0u) | (s_first_win ? HARM_FLAG_RESTART : 0u));
	s_first_win = false;
	s_proc_max = 0u;
	return true;
}

bool harm_push(
	const int16_t pcm[HARM_FRAME],	// MIC1 전처리 출력 256샘플 (12.5 kHz)
	uint32_t frame_seq,				// 이 프레임 번호. 첫 샘플 번호 = (frame_seq − 1) × 256
	bool restart,					// 입력이 끊겼음 (RESYNC) → 진행 중인 창을 버림
	bool defer,						// true면 이번 호출에서는 새 프레임 계산을 미룬다 (DOA 창이 끝난 프레임)
	harm_result_t *out				// 창이 끝났을 때 결과 (반환 true일 때만 유효)
)
{
	bool done = false;
	// 0) 미뤄 둔 프레임이 있으면 먼저 (링의 그 2048샘플을 덮기 전에)
	if (s_pending && !restart && s_started) {
		done = process(s_pend_j, out);
		s_pending = false;
	}
	// 1) 재시작: 이 프레임은 FIR 과도 구간이 섞여 있어 버리고 다음 프레임부터 센다 (doa_push와 같음)
	if (restart || !s_started) {
		s_started = true;
		restart_at(frame_seq * HARM_FRAME);                                 // 다음 프레임 첫 샘플 = (frame_seq + 1 − 1) × 256
		return done;
	}
	// 2) 링에 쓰고 hop 통계를 쌓는다
	for (uint32_t i = 0; i < HARM_FRAME; i++) {
		const float32_t v = (float32_t)pcm[i];
		s_ring[s_got % HARM_NFFT] = pcm[i];
		s_cur_sum += v;
		s_cur_sq += v * v;
		s_got++;
		if (s_got % HARM_HOP == 0u) {
			const uint32_t hop = s_got / HARM_HOP - 1u;
			s_hsum[hop % NHOP] = s_cur_sum;
			s_hsq[hop % NHOP] = s_cur_sq;
			s_cur_sum = s_cur_sq = 0.0f;
		}
	}
	// 3) 새 프레임이 찼으면 계산 (또는 미룸)
	if (s_got >= HARM_NFFT && (s_got - HARM_NFFT) % HARM_HOP == 0u) {
		const uint32_t j = (s_got - HARM_NFFT) / HARM_HOP;
		if (defer || done) {                                                   // 한 호출에 계산은 한 번만
			s_pending = true;
			s_pend_j = j;
		} else {
			done = process(j, out);
		}
	}
	return done;
}
