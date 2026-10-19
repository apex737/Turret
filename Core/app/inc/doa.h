#ifndef INC_DOA_H_
#define INC_DOA_H_

/*
 * doa : 연속 수음(12.5 kHz 3채널 PCM)에서 음원 방위를 구한다 (Step7 D1을 MCU로 옮긴 것)
 *
 *  - Tools/doa/doa_stream.py 의 estimate() + 배경 빼기(--bg)와 같은 계산. 아래 상수는 그쪽 기본값과 같아야
 *    Tools/doa/compare_mcu.py 로 두 결과를 비교할 수 있다.
 *  - 관측 창 0.5 s(6250 샘플)를 3072 샘플(0.246 s)마다 민다. 창 안을 50% 겹친 Hann 512 블록으로 나눠
 *    교차·자기 스펙트럼을 평균한다 (23블록, nfft 1024). 창을 통째로 저장하지 않고 블록이 준비될 때마다 더한다.
 *    창 이동과 배경 시작이 블록 간격(256)의 배수라 겹치는 창과 배경이 같은 블록 FFT를 함께 쓴다 (프레임당 블록 하나).
 *  - 배경: 재시작 직후 DOA_BG_SECONDS 동안 같은 방식으로 평균한 스펙트럼. 창의 교차 스펙트럼에서 빼고 PHAT한다.
 *    배경을 배우는 중에는 빼기 없이(D0) 계산하고 결과에 표시한다. doa_request_bg()로 다시 배운다 (B1 버튼).
 *  - PHAT 상관은 지연 ±max_lag 범위만 1/16 샘플 간격으로 직접 계산한다 (= PC의 16배 제로패딩 IFFT와 같은 값).
 *    회전 인자는 부팅 때 표로 만들고, 세 쌍이 같은 회전을 공유하며, ±지연 대칭으로 절반만 돈다.
 *    → 피크 + 2차 보간 → 채널 고유 지연 보정 → 방향 벡터 최소제곱 → 각도.
 *  - FFT는 CMSIS-DSP arm_rfft_fast_f32. HAL에 의존하지 않는다 (PC용 gcc로 빌드해 시험: Tools/doa/test_doa_host.py).
 *
 * 부호 규칙 (tdoa.h와 같음)
 *  tau_ij = (j 도달 시각) - (i 도달 시각) [샘플, 12.5 kHz]. 쌍 순서 (1,2) (1,3) (2,3).
 *  각도: 중심에서 MIC1 방향이 0°, 위에서 봤을 때 반시계가 +. MIC2 = +120°, MIC3 = -120°.
 * 시간축: 샘플 번호 = STREAM 패킷의 (frame_seq − 1) × 256 + 블록 안 위치 (PC wav의 시간축과 같음).
 */

#include "def.h"

#define DOA_CH            3u
#define DOA_FRAME         256u      // 프레임당 샘플 수 (PREPROC_OUT과 같아야 함)
#define DOA_FS            12500.0f  // 샘플레이트 [Hz] (50 kHz ÷ 4)

#define DOA_OBS           6250u     // 관측 창 [샘플] = 0.5 s       (doa_stream.py --obs 0.5)
#define DOA_HOP           3072u     // 창 이동 [샘플] = 0.246 s. 블록 간격의 배수 (PC --hop 0.25와 결과 의미는 같음)
#define DOA_BLOCK         512u      // 교차 스펙트럼 평균 블록     (--block 512)
#define DOA_NFFT          (2u * DOA_BLOCK)
#define DOA_BAND_LO_HZ    300.0f    // 사용 대역 [Hz]              (--band 300 3000)
#define DOA_BAND_HI_HZ    3000.0f
#define DOA_UP            16u       // 상관을 1/DOA_UP 샘플 간격으로 계산
#define DOA_PHAT_EPS      0.01f     // PHAT 바닥값 (대역 내 최대 크기 대비)

#define DOA_SPACING_M     0.07f     // 마이크 간격 [m] (config/geometry.json, 정삼각형 한 변)
#define DOA_SOUND_SPEED   343.0f
#define DOA_MIC_CW        0

// 채널 고유 지연 [us] (config/geometry.json channel_delay_us). 마이크 모듈·게인을 바꾸면 다시 잰다
#define DOA_DELAY_US_CH1  0.0f
#define DOA_DELAY_US_CH2  (-23.1f)
#define DOA_DELAY_US_CH3  4.3f

// 유효 판정 (doa_stream.py --min-peak, --max-closure, --min-norm, --max-norm, --min-snr)
#define DOA_MIN_PEAK      0.15f
#define DOA_MAX_CLOSURE   0.3f      // [샘플]
#define DOA_MIN_NORM      0.5f
#define DOA_MAX_NORM      1.3f
#define DOA_MIN_SNR_DB    6.0f      // 배경 대비 대역 전력. 이보다 작으면 새 음원이 없는 창 (present = false)

#define DOA_BG_SECONDS    10u       // 배경을 배우는 시간 (PC 시험은 60 s를 썼다)

#define DOA_PAIRS         3u

#define DOA_FLAG_VALID    0x01u     // 피크·닫힘 오차·norm 기준을 모두 만족
#define DOA_FLAG_PRESENT  0x02u     // 배경보다 DOA_MIN_SNR_DB 이상 큼 (배경이 없으면 항상 1)
#define DOA_FLAG_BG       0x04u     // 배경 빼기를 적용함 (D1). 0이면 D0
#define DOA_FLAG_LEARNING 0x08u     // 이 창이 끝날 때 배경을 배우는 중이었음

typedef struct {
	uint32_t s0;                    // 관측 창 첫 샘플 번호
	float    tau[DOA_PAIRS];        // 채널 지연 보정 후 [샘플]
	float    peak[DOA_PAIRS];       // PHAT 상관 피크 (0~1)
	float    angle_deg;             // -180 ~ 180
	float    norm;                  // 방향 벡터 길이 (수평 평면파면 1, cos(고도각))
	float    snr_db;                // 배경 대비 대역 전력 [dB]. 배경이 없으면 0
	uint8_t  flags;                 // DOA_FLAG_*
	uint32_t bg_s0;                 // 사용한 배경의 첫 샘플 번호 (PC 비교용)
	uint32_t bg_n;                  // 배경 길이 [샘플]
	uint32_t proc_us;               // 창 마무리(상관·각도) 계산 시간
} doa_result_t;

// 창, FFT, 방향 계산 행렬 준비. 부팅 시 한 번.
void doa_init(void);

/* PCM 한 프레임을 넣는다. 블록이 준비되면 그 자리에서 처리하고, 끝난 창이 있으면 결과를 out에 쓰고 true.
 * (창 이동 3072 > 프레임 256이라 한 프레임에서 창은 많아야 하나 끝난다)
 * restart: 이 프레임 앞에서 MCU 쪽 입력이 끊겼음 (ADC 유실·overrun → 전처리 재시작). 진행 중인 창을 버리고
 *          다음 프레임부터 새로 시작한다 (이 프레임은 FIR 과도 구간을 포함). 배워 둔 배경은 유지,
 *          배우던 중이었으면 처음부터 다시 배운다. */
bool doa_push(const int16_t pcm[DOA_CH][DOA_FRAME], uint32_t frame_seq, bool restart, doa_result_t *out);

// 다음 프레임부터 배경을 다시 배운다 (주변 소음이 바뀌었을 때). 배우는 동안은 기존 배경을 계속 쓴다.
void doa_request_bg(void);

// 마무리 계산 시간 측정용 사이클 카운터 (MCU는 DWT->CYCCNT, 호스트는 0을 돌려줘도 된다). DOA_CPU_MHZ로 나눠 us로 바꾼다
#define DOA_CPU_MHZ       180u
uint32_t doa_now_cycles(void);

#endif /* INC_DOA_H_ */
