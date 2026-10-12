#ifndef INC_TDOA_H_
#define INC_TDOA_H_
#include "def.h"
/*
 * tdoa : 마이크 3채널 캡처에서 쌍별 도달 시간차(GCC-PHAT)와 음원 방향을 구한다.
 *
 *  - Tools/gcc_phat.py 의 analyze()를 MCU로 옮긴 것. 아래 상수는 그쪽 기본값과 같아야
 *    두 결과를 비교할 수 있다. (PC는 up=1 로 놓고 비교)
 *  - 처리 순서: onset 탐색 → 구간 자르기 → 평균 제거 + 창 → FFT → 교차 스펙트럼
 *               → 대역 제한 + PHAT → IFFT → 피크 + 2차 보간 → 방향 벡터 최소제곱 → 각도
 *  - FFT는 CMSIS-DSP(arm_rfft_fast_f32) 사용. HAL에는 의존하지 않는다.
 *
 * 부호 규칙
 *  tau_ij = (j 도달 시각) - (i 도달 시각) [샘플]. 양수 = MIC j가 MIC i보다 늦게 들음.
 *  각도: 중심에서 MIC1 방향이 0°, 위에서 봤을 때 반시계가 +. MIC2 = +120°, MIC3 = -120°.
 */

#define TDOA_CH           3u        // 마이크 수
#define TDOA_FRAME        1024u     // 프레임당 샘플 수 (ADC_SAMPLES_PER_HALF 와 같아야 함)
#define TDOA_FS           50000u    // 샘플링 주파수 [Hz]

#define TDOA_WIN          250u      // 분석 구간 길이 [샘플] = 5 ms
#define TDOA_PRE          50u       // onset보다 이만큼 앞에서 구간 시작 [샘플] = 1 ms
#define TDOA_NFFT         512u      // FFT 크기 (구간 뒤를 0으로 채움)
#define TDOA_BAND_LO_HZ   500u      // 사용할 대역 [Hz]
#define TDOA_BAND_HI_HZ   3000u
#define TDOA_MAX_LAG      13        // 탐색할 최대 지연 [샘플] = ceil(간격 / 음속 x fs) + 2
#define TDOA_PHAT_EPS     0.01f     // PHAT 정규화 바닥값 (대역 내 최대 크기 대비)

#define TDOA_SPACING_M    0.07f     // 마이크 간격 [m] (정삼각형 한 변)
#define TDOA_SOUND_SPEED  343.0f    // 음속 [m/s]
#define TDOA_MIC_CW       0         // 마이크 번호가 시계 방향으로 붙어 있으면 1

// 신뢰 판정 기준 (Tools/gcc_phat.py 의 --min-peak, --min-norm, --max-norm 과 같아야 함)
#define TDOA_MIN_PEAK     0.5f      // 세 쌍 중 가장 낮은 피크가 이 값 이상이어야 함
#define TDOA_MIN_NORM     0.3f      // 이보다 작으면 음원이 거의 위/아래에 있어 수평 각도가 불안정
#define TDOA_MAX_NORM     1.2f      // 1을 크게 넘는 값은 물리적으로 불가능 (엉뚱한 피크를 고른 것)

#define TDOA_PAIRS        3u        // (1,2) (1,3) (2,3)

// 프레임 하나 = [채널][샘플]. frames[k][ch][i] 로 읽는다.
typedef const uint16_t (*tdoa_frame_t)[TDOA_FRAME];

typedef struct {
	float    tau[TDOA_PAIRS];   // tau12, tau13, tau23 [샘플]
	float    peak[TDOA_PAIRS];  // 쌍별 상관 피크 높이 (0~1). 낮으면 신뢰하기 어려움
	float    angle_deg;         // 방향 [deg]
	float    norm;              // 방향 벡터 길이 (멀고 같은 평면이면 1)
	uint16_t onset;             // 소리 시작 위치 [샘플] (frames를 이어붙인 기준)
	uint16_t win_start;         // 분석 구간 시작 위치 [샘플]
	bool     valid;             // 신뢰 가능: 피크와 norm이 위 기준을 모두 만족. false면 angle_deg를 쓰지 말 것
} tdoa_result_t;

// 창, FFT, 방향 계산 행렬 준비. 부팅 시 한 번 호출.
void tdoa_init(void);

// frames[0..nframes-1] 을 시간 순서로 이어붙인 캡처에서 지연과 방향을 구한다. (nframes = 1 또는 2)
void tdoa_process(const tdoa_frame_t frames[], uint32_t nframes, tdoa_result_t *out);

#endif /* INC_TDOA_H_ */
