#include "adc.h"

static uint16_t adc_buffer[ADC_DMA_LENGTH]
    __attribute__((aligned(4)));

static ADC_HandleTypeDef *s_mstr, *s_slv1, *s_slv2;
static TIM_HandleTypeDef *s_tim;

// 포인터 변수 자체가 volatile (ISR이 바꿈)
static const uint16_t * volatile readyHalf = NULL;   // 준비된 절반 시작주소
static volatile uint32_t readySeq;                    // readyHalf의 프레임 번호
static volatile uint32_t frameSeq;                    // 만들어진 반버퍼 수 (ISR이 증가)
static volatile uint32_t dropCnt;                     // 가져가지 못하고 덮어쓰인 프레임
static volatile uint32_t ovrCnt;                      // ADC overrun 횟수
static volatile bool     ovrPending;                  // 재시작 필요 (ISR → main)

static void start_all(void)
{
	if (HAL_ADC_Start(s_slv1) != HAL_OK) error_handle();
	if (HAL_ADC_Start(s_slv2) != HAL_OK) error_handle();
	if (HAL_ADCEx_MultiModeStart_DMA(s_mstr, (uint32_t *)adc_buffer, ADC_DMA_LENGTH) != HAL_OK)
		error_handle();
	if (HAL_TIM_Base_Start(s_tim) != HAL_OK) error_handle();      // 마지막: 첫 트리거부터 ADC1이 buffer[0]
}

void adc_init(ADC_HandleTypeDef *hadcMstr,
              ADC_HandleTypeDef *hadcSlv1,
              ADC_HandleTypeDef *hadcSlv2,
              TIM_HandleTypeDef *htim)
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

void HAL_ADC_ErrorCallback(ADC_HandleTypeDef *hadc)
{
	if (hadc->Instance == ADC1 && (hadc->ErrorCode & HAL_ADC_ERROR_OVR)) {
		ovrCnt++;
		ovrPending = true;     // DMA가 멈췄으므로 main에서 재시작
	}
}

void adc_service(void)
{
	if (!ovrPending) return;
	HAL_TIM_Base_Stop(s_tim);
	HAL_ADCEx_MultiModeStop_DMA(s_mstr);
	HAL_ADC_Stop(s_slv1);
	HAL_ADC_Stop(s_slv2);
	__disable_irq();
	readyHalf = NULL;
	ovrPending = false;
	__enable_irq();
	__HAL_TIM_SET_COUNTER(s_tim, 0);
	start_all();
}

static inline void adc_on_half_ready(const uint16_t* half)
{
	if(readyHalf != NULL) {
		dropCnt++;             // 이전 반버퍼를 아무도 가져가지 않았는데 새 것이 옴 → 이전 것은 사라짐
	}
	readyHalf = half;
	readySeq = ++frameSeq;     // 번호는 1부터
}

// 앞쪽 절반 수신 완료
void HAL_ADC_ConvHalfCpltCallback(ADC_HandleTypeDef *hadc)
{
	if(hadc->Instance == ADC1)
		adc_on_half_ready(&adc_buffer[0]);
}

// 뒤쪽 절반 수신 완료
void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *hadc)
{
	if(hadc->Instance == ADC1)
		adc_on_half_ready(&adc_buffer[ADC_HALF_LENGTH]);
}

bool adc_get_frame(uint16_t out[ADC_CH_CNT][ADC_SAMPLES_PER_HALF], uint32_t *seq)
{
	// HT/TC 콜백이 readyHalf, readySeq, frameSeq를 바꾸므로 셋을 한 번에 읽는다
	__disable_irq();
	const uint16_t *src = readyHalf;
	const uint32_t my_seq = readySeq;
	readyHalf = NULL;
	__enable_irq();

	if(src == NULL)
		return false;

	for (uint32_t i = 0; i < ADC_SAMPLES_PER_HALF; i++)
	{
		out[0][i] = src[ADC_CH_CNT * i + 0U];
		out[1][i] = src[ADC_CH_CNT * i + 1U];
		out[2][i] = src[ADC_CH_CNT * i + 2U];
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
