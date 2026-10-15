#include "preproc.h"
#include "arm_math.h"
#include <math.h>

#define CLIP_LO 8u
#define CLIP_HI 4087u

static arm_fir_decimate_instance_f32 s_fir[PREPROC_CH];
static float32_t s_state[PREPROC_CH][FIR_NUM_TAPS + PREPROC_IN - 1u];   /* CMSIS 요구 크기: numTaps + blockSize − 1 */
static float32_t s_in[PREPROC_IN];
static float32_t s_out[PREPROC_OUT];

_Static_assert(PREPROC_IN % FIR_DECIM_M == 0u, "block size must be a multiple of M");

void preproc_reset(void)
{
	for (uint32_t c = 0; c < PREPROC_CH; c++) {
		/* init이 상태 버퍼를 0으로 채운다 */
		if (arm_fir_decimate_init_f32(&s_fir[c], (uint16_t)FIR_NUM_TAPS, (uint8_t)FIR_DECIM_M,
		                              fir_coeffs, s_state[c], PREPROC_IN) != ARM_MATH_SUCCESS)
			error_handle();
	}
}

bool preproc_run(const uint16_t in[PREPROC_CH][PREPROC_IN], int16_t out[PREPROC_CH][PREPROC_OUT])
{
	bool clip = false;
	for (uint32_t c = 0; c < PREPROC_CH; c++) {
		for (uint32_t i = 0; i < PREPROC_IN; i++) {
			const uint32_t v = in[c][i];
			clip |= (v <= CLIP_LO) || (v >= CLIP_HI);
			s_in[i] = (float32_t)((int32_t)v - PREPROC_ADC_CENTER);
		}
		arm_fir_decimate_f32(&s_fir[c], s_in, s_out, PREPROC_IN);
		for (uint32_t k = 0; k < PREPROC_OUT; k++) {
			/* lrintf: 현재 FPU 반올림 모드(기본 nearest-even)로 정수화. PC 기준은 np.rint와 같음 */
			const int32_t r = (int32_t)lrintf(s_out[k] * PREPROC_PCM_SCALE);
			out[c][k] = (int16_t)__SSAT(r, 16);
		}
	}
	return clip;
}
