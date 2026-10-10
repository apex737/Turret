#include "tdoa.h"
#include "arm_math.h"
#include <string.h>

// 대역 [LO, HI] Hz 에 들어가는 FFT 빈 번호 (빈 k의 주파수 = k x fs / NFFT)
#define K_LO     ((TDOA_BAND_LO_HZ * TDOA_NFFT + TDOA_FS - 1u) / TDOA_FS)  // 올림 → 6
#define K_HI     (TDOA_BAND_HI_HZ * TDOA_NFFT / TDOA_FS)                   // 내림 → 30
#define NBAND    (K_HI - K_LO + 1u)                                        // 25
#define NLAG     (2u * TDOA_MAX_LAG + 1u)                                  // 지연 -13 ~ +13 → 27
#define TAPER    (TDOA_WIN / 5u)                                           // 창 양 끝에서 줄이는 길이

_Static_assert(TDOA_WIN <= TDOA_NFFT, "window must fit in FFT");
_Static_assert(2 * TDOA_MAX_LAG < TDOA_NFFT, "lag range must fit in FFT");

static const uint8_t pair_i[TDOA_PAIRS] = {0, 0, 1};
static const uint8_t pair_j[TDOA_PAIRS] = {1, 2, 2};

static arm_rfft_fast_instance_f32 fft;
static float32_t window[TDOA_WIN];            // 양 끝만 코사인으로 줄이는 창 (Tukey)
static float32_t solve[2][TDOA_PAIRS];        // 지연 3개 → 방향 벡터(x, y) 최소제곱 행렬
static float32_t spec[TDOA_CH][TDOA_NFFT];    // 채널별 스펙트럼 (re, im 교대로 256쌍)
static float32_t work[TDOA_NFFT];             // FFT 입력 / PHAT 적용한 교차 스펙트럼
static float32_t corr[TDOA_NFFT];             // IFFT 결과 (상관 곡선)

void tdoa_init(void)
{
	arm_rfft_fast_init_f32(&fft, TDOA_NFFT);

	for (uint32_t i = 0; i < TDOA_WIN; i++)
		window[i] = 1.0f;
	for (uint32_t i = 0; i < TAPER; i++)
	{
		float32_t r = 0.5f - 0.5f * cosf(PI * ((float32_t)i + 0.5f) / (float32_t)TAPER);
		window[i] = r;
		window[TDOA_WIN - 1u - i] = r;
	}

	// 마이크 좌표: 중심이 원점인 정삼각형, MIC1이 0° 방향
	static const float32_t mic_deg[TDOA_CH] = {0.0f, 120.0f, -120.0f};
	const float32_t radius = TDOA_SPACING_M / sqrtf(3.0f);
	float32_t pos[TDOA_CH][2];
	for (uint32_t m = 0; m < TDOA_CH; m++)
	{
		float32_t a = (TDOA_MIC_CW ? -mic_deg[m] : mic_deg[m]) * PI / 180.0f;
		pos[m][0] = radius * cosf(a);
		pos[m][1] = radius * sinf(a);
	}

	// 평면파 가정: (p_j - p_i)·u = -c·tau_ij  →  A u = b  (식 3개, 미지수 2개)
	// 최소제곱 해 u = (AᵀA)⁻¹Aᵀ b. 배치가 고정이라 (AᵀA)⁻¹Aᵀ 를 미리 계산해 둔다.
	float32_t a[TDOA_PAIRS][2];
	float32_t gxx = 0.0f, gxy = 0.0f, gyy = 0.0f;
	for (uint32_t p = 0; p < TDOA_PAIRS; p++)
	{
		a[p][0] = pos[pair_j[p]][0] - pos[pair_i[p]][0];
		a[p][1] = pos[pair_j[p]][1] - pos[pair_i[p]][1];
		gxx += a[p][0] * a[p][0];
		gxy += a[p][0] * a[p][1];
		gyy += a[p][1] * a[p][1];
	}
	const float32_t det = gxx * gyy - gxy * gxy;
	for (uint32_t p = 0; p < TDOA_PAIRS; p++)
	{
		solve[0][p] = ( gyy * a[p][0] - gxy * a[p][1]) / det;
		solve[1][p] = (-gxy * a[p][0] + gxx * a[p][1]) / det;
	}
}

// 이어붙인 캡처의 i번째 샘플
static inline uint32_t sample(const tdoa_frame_t frames[], uint32_t ch, uint32_t i)
{
	return frames[i / TDOA_FRAME][ch][i % TDOA_FRAME];
}

// i번째 샘플이 평균에서 벗어난 정도 (3채널 중 최대). 나눗셈을 피하려고 n배 한 정수로 계산:
// |x - 평균| x n = |n·x - 합|
static uint32_t deviation(const tdoa_frame_t frames[], const int32_t sum[], uint32_t n, uint32_t i)
{
	uint32_t worst = 0;
	for (uint32_t ch = 0; ch < TDOA_CH; ch++)
	{
		int32_t d = (int32_t)(n * sample(frames, ch, i)) - sum[ch];
		if (d < 0)
			d = -d;
		if ((uint32_t)d > worst)
			worst = (uint32_t)d;
	}
	return worst;
}

// 소리 시작 위치: 3채널 중 가장 먼저 잡음을 크게 넘는 샘플.
// 잡음 = 앞쪽 1/4 구간의 평균 편차.  문턱 = max(8 x 잡음, 최대 편차 / 20)
// 전부 정수 연산이라 Tools/gcc_phat.py 의 find_onset()과 결과가 정확히 같다.
static uint32_t find_onset(const tdoa_frame_t frames[], uint32_t n)
{
	int32_t sum[TDOA_CH] = {0};
	for (uint32_t ch = 0; ch < TDOA_CH; ch++)
		for (uint32_t i = 0; i < n; i++)
			sum[ch] += (int32_t)sample(frames, ch, i);

	const uint32_t q = (n / 4u > 16u) ? n / 4u : 16u;
	uint64_t noise_sum = 0;
	uint32_t peak = 0, peak_idx = 0;
	for (uint32_t i = 0; i < n; i++)
	{
		uint32_t d = deviation(frames, sum, n, i);
		if (i < q)
			noise_sum += d;
		if (d > peak)
		{
			peak = d;
			peak_idx = i;
		}
	}

	// d > max(8·noise_sum/q, peak/20)  ⇔  d·20·q > max(160·noise_sum, peak·q)
	uint64_t thr = 160u * noise_sum;
	if ((uint64_t)peak * q > thr)
		thr = (uint64_t)peak * q;
	for (uint32_t i = 0; i < n; i++)
		if ((uint64_t)deviation(frames, sum, n, i) * 20u * q > thr)
			return i;
	return peak_idx; // 문턱을 넘는 샘플이 없으면 가장 큰 샘플 위치
}

void tdoa_process(const tdoa_frame_t frames[], uint32_t nframes, tdoa_result_t *out)
{
	const uint32_t n = nframes * TDOA_FRAME;

	// 1) 분석 구간: onset보다 PRE 앞에서 시작, 3채널에 같은 구간을 쓴다
	const uint32_t onset = find_onset(frames, n);
	int32_t lo = (int32_t)onset - (int32_t)TDOA_PRE;
	if (lo > (int32_t)(n - TDOA_WIN))
		lo = (int32_t)(n - TDOA_WIN);
	if (lo < 0)
		lo = 0;
	out->onset = (uint16_t)onset;
	out->win_start = (uint16_t)lo;

	// 2) 채널별: 평균 제거 → 창 → 뒤를 0으로 채움 → FFT
	for (uint32_t ch = 0; ch < TDOA_CH; ch++)
	{
		float32_t mean;
		for (uint32_t i = 0; i < TDOA_WIN; i++)
			work[i] = (float32_t)sample(frames, ch, (uint32_t)lo + i);
		arm_mean_f32(work, TDOA_WIN, &mean);
		arm_offset_f32(work, -mean, work, TDOA_WIN);
		arm_mult_f32(work, window, work, TDOA_WIN);
		memset(&work[TDOA_WIN], 0, (TDOA_NFFT - TDOA_WIN) * sizeof(float32_t));
		arm_rfft_fast_f32(&fft, work, spec[ch], 0); // work는 계산 중 덮어써진다
	}

	// 3) 쌍별 GCC-PHAT
	for (uint32_t p = 0; p < TDOA_PAIRS; p++)
	{
		float32_t conj_i[2u * NBAND], cross[2u * NBAND], mag[NBAND], cc[NLAG];
		float32_t mag_max, peak;
		uint32_t idx;

		// 교차 스펙트럼 X_j·conj(X_i). 대역 안의 빈(K_LO ~ K_HI)만 계산
		arm_cmplx_conj_f32(&spec[pair_i[p]][2u * K_LO], conj_i, NBAND);
		arm_cmplx_mult_cmplx_f32(&spec[pair_j[p]][2u * K_LO], conj_i, cross, NBAND);

		// PHAT: 크기로 나눠 위상만 남긴다. 바닥값은 신호가 거의 없는 빈의 잡음 증폭을 막는다
		arm_cmplx_mag_f32(cross, mag, NBAND);
		arm_max_f32(mag, NBAND, &mag_max, &idx);
		const float32_t eps = TDOA_PHAT_EPS * mag_max + 1e-30f;

		// 대역 밖은 0으로 둔다 (= 주파수 영역 BPF)
		memset(work, 0, sizeof(work));
		for (uint32_t k = 0; k < NBAND; k++)
		{
			const float32_t s = 1.0f / (mag[k] + eps);
			work[2u * (K_LO + k)]      = cross[2u * k] * s;
			work[2u * (K_LO + k) + 1u] = cross[2u * k + 1u] * s;
		}

		// IFFT → 상관 곡선. 지연 l 의 값은 corr[l], 음수 지연은 뒤쪽(corr[NFFT + l])에 있다.
		// NFFT / (2·NBAND) 를 곱하면 완전히 정렬됐을 때 피크가 1이 된다.
		arm_rfft_fast_f32(&fft, work, corr, 1);
		const float32_t scale = (float32_t)TDOA_NFFT / (2.0f * (float32_t)NBAND);
		for (int32_t l = -TDOA_MAX_LAG; l <= TDOA_MAX_LAG; l++)
			cc[l + TDOA_MAX_LAG] = corr[(l + (int32_t)TDOA_NFFT) % (int32_t)TDOA_NFFT] * scale;

		// 피크 탐색 + 2차(포물선) 보간으로 샘플 사이 위치 추정
		arm_max_f32(cc, NLAG, &peak, &idx);
		float32_t tau = (float32_t)((int32_t)idx - TDOA_MAX_LAG);
		if (idx > 0u && idx < NLAG - 1u)
		{
			const float32_t y0 = cc[idx - 1u], y1 = cc[idx], y2 = cc[idx + 1u];
			const float32_t d = y0 - 2.0f * y1 + y2;
			if (d < 0.0f)
			{
				const float32_t frac = 0.5f * (y0 - y2) / d;
				tau += frac;
				peak = y1 - 0.25f * (y0 - y2) * frac;
			}
		}
		out->tau[p] = tau;
		out->peak[p] = peak;
	}

	// 4) 지연 3개 → 방향 벡터 → 각도
	float32_t ux = 0.0f, uy = 0.0f;
	for (uint32_t p = 0; p < TDOA_PAIRS; p++)
	{
		const float32_t b = -TDOA_SOUND_SPEED * out->tau[p] / (float32_t)TDOA_FS; // 경로차 [m]
		ux += solve[0][p] * b;
		uy += solve[1][p] * b;
	}
	out->angle_deg = atan2f(uy, ux) * 180.0f / PI;
	out->norm = sqrtf(ux * ux + uy * uy);

	// 5) 신뢰 판정: 세 쌍의 피크가 모두 충분히 높고, 방향 벡터 길이가 그럴듯한 범위일 때만 유효
	float32_t peak_min = out->peak[0];
	for (uint32_t p = 1; p < TDOA_PAIRS; p++)
		if (out->peak[p] < peak_min)
			peak_min = out->peak[p];
	out->valid = (peak_min >= TDOA_MIN_PEAK) &&
	             (out->norm >= TDOA_MIN_NORM) && (out->norm <= TDOA_MAX_NORM);
}
