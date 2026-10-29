#ifndef INC_PREPROC_H_
#define INC_PREPROC_H_

/*
 * preproc : 50 kHz 4채널 프레임 → FIR 저역 + ↓4 → 12.5 kHz int16 PCM (Step5, Step8e에서 4채널)
 *
 *  - CMSIS-DSP arm_fir_decimate_f32. 네 채널이 같은 계수(fir_coeffs.h)·같은 데시메이션 위상을 쓰고,
 *    상태 버퍼는 채널마다 따로 둔다. 정상 프레임 사이에서는 상태를 지우지 않는다 (경계에서 지우면 48.8 Hz 빗이 생김).
 *  - 변환 규약 (Tools/fir_design.py, config/frontend_config.json과 같음)
 *      x = (float)(adc - 2048)                       12비트 → 0 중심
 *      y[k] = Σ b[j]·x[4k − j]                       CMSIS 출력 위상 (상태 0에서 시작, 호스트 실측)
 *      pcm = sat16(round_nearest_even(y × 16))       12비트 범위를 int16 범위로
 *  - 유실 뒤에는 preproc_reset()으로 상태를 0으로 만든다. 그 뒤 첫 PREPROC_TRANSIENT_OUT 샘플은 과도 구간이다.
 */

#include "def.h"
#include "fir_coeffs.h"

#define PREPROC_CH            4u
#define PREPROC_SUB           256u                                    /* FIR을 한 번에 돌리는 입력 수. 상태 버퍼 = 탭 + SUB − 1 (RAM 절약) */
#define PREPROC_IN            1024u                                   /* 프레임당 입력 (50 kHz) */
#define PREPROC_OUT           (PREPROC_IN / FIR_DECIM_M)              /* 프레임당 출력 (12.5 kHz) = 256 */
#define PREPROC_ADC_CENTER    2048
#define PREPROC_PCM_SCALE     16.0f
#define PREPROC_TRANSIENT_OUT ((FIR_NUM_TAPS + FIR_DECIM_M - 1u) / FIR_DECIM_M)   /* 19 */

/* 상태를 0으로 초기화 (부팅 시, 유실 뒤) */
void preproc_reset(void);

/* 프레임 하나를 처리한다. 반환값: 입력에 클리핑 샘플(≤8 또는 ≥4087)이 있었으면 true */
bool preproc_run(const uint16_t in[PREPROC_CH][PREPROC_IN], int16_t out[PREPROC_CH][PREPROC_OUT]);

#endif /* INC_PREPROC_H_ */
