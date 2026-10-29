/*
 * adc.c : 마이크 3개를 동시에 50 kHz로 재서 DMA 핑퐁 버퍼에 받고, 반버퍼(프레임)를 main에 넘긴다 (규약은 adc.h)
 *
 *  하드웨어가 하는 일 (CPU 개입 없음)
 *    TIM2 갱신 이벤트(50 kHz) → ADC1(마스터)이 트리거를 받고 ADC2·3(슬레이브)이 같은 순간 함께 변환 (삼중 동시 모드)
 *    → DMA2가 결과 3개를 [ADC1, ADC2, ADC3] 순서로 adc_buffer에 이어 쓴다 (원형 모드: 끝까지 쓰면 처음으로)
 *
 *  adc_buffer 배치 (uint16 12288개 = 24 KB)
 *    [ 앞쪽 절반 : 1024트리거 × 6값 인터리브 ][ 뒤쪽 절반 : 1024트리거 × 6값 인터리브 ]
 *      m1 m2 m3 m4 x x m1 m2 m3 m4 x x …         (m4 = ADC1 rank 2, x = ADC2·3 rank 2 자리 채우기)
 *    DMA가 뒤쪽을 채우는 동안 main이 앞쪽을 가져가고, 그 반대도 같다 (핑퐁). 절반 하나 = 1024 / 50 kHz = 20.48 ms
 *
 *  ISR과 main의 역할 분담
 *    ISR  (HAL_ADC_ConvHalfCpltCallback / ConvCpltCallback) : "어느 절반이 찼는지 + 번호"만 기록하고 바로 끝난다
 *    main (adc_get_frame)                                    : 그 절반을 채널별로 복사해 가져간다
 *  준비된 절반을 담는 칸(readyHalf)은 하나뿐이다. main이 늦어 다음 절반이 먼저 차면 이전 것은 버려지고 drop이 오른다.
 */
#include "adc.h"

/* DMA가 직접 쓰는 원형 버퍼. aligned(4): DMA 전송 단위(half-word × 2)를 맞추기 위해 4바이트 경계에서 시작 */
static uint16_t adc_buffer[ADC_DMA_LENGTH]
    __attribute__((aligned(4)));

/* app_init이 넘겨준 HAL 핸들 (main.c의 hadc1·2·3, htim2). 재시작할 때 다시 쓰려고 보관 */
static ADC_HandleTypeDef *s_mstr, *s_slv1, *s_slv2;
static TIM_HandleTypeDef *s_tim;

// 포인터 변수 자체가 volatile (ISR이 바꿈)
static const uint16_t * volatile readyHalf = NULL;   // 준비된 절반 시작주소
static volatile uint32_t readySeq;                    // readyHalf의 프레임 번호
static volatile uint32_t frameSeq;                    // 만들어진 반버퍼 수 (ISR이 증가)
static volatile uint32_t dropCnt;                     // 가져가지 못하고 덮어쓰인 프레임
static volatile uint32_t ovrCnt;                      // ADC overrun 횟수
static volatile bool     ovrPending;                  // 재시작 필요 (ISR → main)
/* volatile: 위 변수들은 ISR과 main이 함께 읽고 쓴다. 컴파일러가 값을 레지스터에 담아 두고 재사용하지 못하게 해서
 * main이 매번 메모리에서 최신 값을 읽게 한다. (여러 변수를 "한 번에" 읽는 것은 volatile로 안 되므로 임계 구역을 쓴다) */

/* 슬레이브 2개 → 마스터(+DMA) → 타이머 순으로 켠다.
 * 타이머가 마지막인 이유: 타이머가 먼저 돌면 DMA가 준비되기 전에 변환이 시작돼, 버퍼 첫 칸이 ADC1이 아닐 수 있다.
 * 그러면 인터리브 순서가 한 칸 밀려 채널이 뒤바뀐다. */
static void start_all(void)
{
	if (HAL_ADC_Start(s_slv1) != HAL_OK) error_handle();
	if (HAL_ADC_Start(s_slv2) != HAL_OK) error_handle();
	if (HAL_ADCEx_MultiModeStart_DMA(s_mstr, (uint32_t *)adc_buffer, ADC_DMA_LENGTH) != HAL_OK)
		error_handle();
	if (HAL_TIM_Base_Start(s_tim) != HAL_OK) error_handle();      // 마지막: 첫 트리거부터 ADC1이 buffer[0]
}

void adc_init(
	ADC_HandleTypeDef *hadcMstr,	// ADC1 (마스터, MIC1). 다중 모드 DMA를 이 핸들로 시작한다
	ADC_HandleTypeDef *hadcSlv1,	// ADC2 (슬레이브, MIC2)
	ADC_HandleTypeDef *hadcSlv2,	// ADC3 (슬레이브, MIC3)
	TIM_HandleTypeDef *htim			// TIM2: 50 kHz 변환 트리거. 맨 마지막에 켠다
)
{
	s_mstr = hadcMstr; s_slv1 = hadcSlv1; s_slv2 = hadcSlv2; s_tim = htim;
	// OVR 인터럽트는 HAL_ADCEx_MultiModeStart_DMA가 켠다. NVIC만 열어 주면 HAL_ADC_ErrorCallback이 불린다
	HAL_NVIC_SetPriority(ADC_IRQn, 1, 0);
	HAL_NVIC_EnableIRQ(ADC_IRQn);
	start_all();
}

/* CubeMX에서 ADC 전역 인터럽트를 켜면 stm32f4xx_it.c에 같은 함수가 생겨 링크 에러가 난다.
 * 그때는 이 함수를 지우고 그쪽의 HAL_ADC_IRQHandler(&hadc1)를 쓰면 된다. */
void ADC_IRQHandler(void)
{
	if (s_mstr) HAL_ADC_IRQHandler(s_mstr);
}

/* ADC 오류 ISR. overrun = 새 변환 결과가 나왔는데 DMA가 이전 결과를 아직 안 읽어 간 상태.
 * 이때 하드웨어가 DMA 요청을 멈추므로 버퍼가 더는 채워지지 않는다. ISR에서는 표시만 하고 재시작은 main이 한다
 * (HAL 정지·시작 함수는 시간이 걸리고 ISR 안에서 부르기에 적합하지 않다). */
void HAL_ADC_ErrorCallback(
	ADC_HandleTypeDef *hadc	// 오류가 난 ADC. HAL이 넘겨준다 (마스터 ADC1만 본다)
)
{
	if (hadc->Instance == ADC1 && (hadc->ErrorCode & HAL_ADC_ERROR_OVR)) {
		ovrCnt++;
		ovrPending = true;     // DMA가 멈췄으므로 main에서 재시작
	}
}

/* main 루프에서 매번 호출. overrun 표시가 있을 때만 전부 멈췄다가 start_all() 순서로 다시 켠다.
 * 주의: frameSeq는 0으로 되돌리지 않고 이어서 센다. 그래서 재시작 전후 프레임 번호가 연속처럼 보인다.
 *       끊김은 ovr 카운터가 늘었는지로 알아야 한다 (app.c on_stream_frame이 그렇게 판정한다). */
void adc_service(void)
{
	if (!ovrPending) return;
	HAL_TIM_Base_Stop(s_tim);
	HAL_ADCEx_MultiModeStop_DMA(s_mstr);
	HAL_ADC_Stop(s_slv1);
	HAL_ADC_Stop(s_slv2);
	__disable_irq();
	readyHalf = NULL;          // 멈추기 전에 준비돼 있던 절반은 버린다 (재시작하면 DMA가 버퍼 처음부터 다시 쓴다)
	ovrPending = false;
	__enable_irq();
	__HAL_TIM_SET_COUNTER(s_tim, 0);   // 타이머 카운터를 0부터: 재시작 후 첫 트리거 시점을 일정하게
	start_all();
}

/* 반버퍼 하나가 다 찼을 때 ISR에서 호출. "준비된 절반" 칸에 주소를 넣고 번호를 매긴다.
 * 번호는 main이 가져간 횟수가 아니라 만들어진 순서라서, main이 놓친 프레임은 번호가 건너뛰는 것으로 드러난다. */
static inline void adc_on_half_ready(
	const uint16_t* half	// 방금 다 찬 절반의 시작 주소 (&adc_buffer[0] 또는 &adc_buffer[ADC_HALF_LENGTH])
)
{
	if(readyHalf != NULL) {
		dropCnt++;             // 이전 반버퍼를 아무도 가져가지 않았는데 새 것이 옴 → 이전 것은 사라짐
	}
	readyHalf = half;
	readySeq = ++frameSeq;     // 번호는 1부터
}

// 앞쪽 절반 수신 완료
void HAL_ADC_ConvHalfCpltCallback(
	ADC_HandleTypeDef *hadc	// 이벤트를 낸 ADC. HAL이 넘겨준다 (DMA를 가진 ADC1만 처리)
)
{
	if(hadc->Instance == ADC1)
		adc_on_half_ready(&adc_buffer[0]);
}

// 뒤쪽 절반 수신 완료
void HAL_ADC_ConvCpltCallback(
	ADC_HandleTypeDef *hadc	// 이벤트를 낸 ADC. HAL이 넘겨준다 (DMA를 가진 ADC1만 처리)
)
{
	if(hadc->Instance == ADC1)
		adc_on_half_ready(&adc_buffer[ADC_HALF_LENGTH]);
}



bool adc_get_frame(
	uint16_t out[ADC_CH_CNT][ADC_SAMPLES_PER_HALF],	// 마이크 4개 값을 out[4]에 나눠 담는다 (자리 채우기 2개는 버림)
	uint32_t *seq	// 프레임 번호
)
{
	// HT/TC 콜백이 readyHalf, readySeq, frameSeq를 바꾸므로
	// 인터럽트를 비활성화 한 뒤, 셋을 한 번에 읽는다
	__disable_irq();
	const uint16_t *src = readyHalf;
	const uint32_t my_seq = readySeq;
	readyHalf = NULL;
	__enable_irq();

	if(src == NULL)
		return false;          // 새로 찬 절반이 없음

	/* 인터리브 해제: 트리거마다 [A1r1 A2r1 A3r1 A1r2 A2r2 A3r2]
	 *   out[0] = ADC1 r1 (PA0, MIC1 0°), out[1] = ADC2 r1 (PA1, MIC2 120°), out[2] = ADC3 r1 (PC0, MIC3 −120°),
	 *   out[3] = ADC1 r2 (PA4, MIC4 위, 1.78 us 늦음). [4]·[5]는 자리 채우기라 버린다 */
	for (uint32_t i = 0; i < ADC_SAMPLES_PER_HALF; i++)
	{
		const uint16_t *t = &src[ADC_SEQ_LEN * i];
		out[0][i] = t[0];
		out[1][i] = t[1];
		out[2][i] = t[2];
		out[3][i] = t[3];
	}

	// 복사하는 동안 다른 쪽 반버퍼가 완료됐다면(frameSeq 증가) 그 순간부터 DMA는 src 쪽 절반을 덮어쓰고 있다 → 폐기
	if (frameSeq != my_seq)
	{
		dropCnt++;
		return false;
	}

	*seq = my_seq;
	return true;
}

uint32_t adc_get_drop_cnt(void) { return dropCnt; }
uint32_t adc_get_ovr_cnt(void)  { return ovrCnt; }
