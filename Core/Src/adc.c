#include "adc.h"

static uint16_t adc_buffer[ADC_DMA_LENGTH]
    __attribute__((aligned(4)));

void adc_init(ADC_HandleTypeDef *hadcMstr,
              ADC_HandleTypeDef *hadcSlv1,
              ADC_HandleTypeDef *hadcSlv2)
{
	if (HAL_ADC_Start(hadcSlv1) != HAL_OK)
	        error_handle();

	if (HAL_ADC_Start(hadcSlv2) != HAL_OK)
		error_handle();

	if (HAL_ADCEx_MultiModeStart_DMA(hadcMstr,
			(uint32_t *)adc_buffer, ADC_DMA_LENGTH) != HAL_OK)
		error_handle();
}

// 포인터 변수 자체가 volatile
// 준비된 절반 시작주소
static const uint16_t * volatile readyHalf = NULL;
static volatile uint32_t frameSeq;				  // 프레임 카운트
static volatile uint32_t dropCnt;				  // 놓친 프레임

// Why Inline??
static inline void adc_on_half_ready(const uint16_t* half)
{
	if(readyHalf != NULL) {
		dropCnt++;
	}
	readyHalf = half;
	frameSeq++;
}

// 앞쪽 절반 수신 완료
void HAL_ADC_ConvHalfCpltCallback(ADC_HandleTypeDef *hadc)
{
	if(hadc->Instance == ADC1)
	{
		adc_on_half_ready(&adc_buffer[0]);
	}
}

// 뒤쪽 절반 수신 완료
void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *hadc)
{
	if(hadc->Instance == ADC1)
	{
		adc_on_half_ready(&adc_buffer[ADC_HALF_LENGTH]);
	}
}

// app.c 에서 참조를 전달하면 데이터를 채널별로 담아서 돌려준다.
bool adc_get_frame(uint16_t out[ADC_CH_CNT][ADC_SAMPLES_PER_HALF])
{
	// 왜 irq를 disable 하는가?
	// HT/TC 콜백은 readyHalf, frameSeq를 변경하기 때문
	__disable_irq();

	const uint16_t *src = readyHalf;	// 복사할 프레임
	uint32_t seq = frameSeq;			// 오버런 검사
	readyHalf = NULL;

	__enable_irq();

	if(src == NULL) {
		return false;
	}

	for (uint32_t i = 0; i < ADC_SAMPLES_PER_HALF; i++)
	{
		out[0][i] = src[ADC_CH_CNT * i + 0U];
		out[1][i] = src[ADC_CH_CNT * i + 1U];
		out[2][i] = src[ADC_CH_CNT * i + 2U];
	}

	// Overrun 감지 방식
	// 복사 중에 다음 절반까지 찼다?? -> DMA가 src 영역을 덮어쓰고있다! (프레임 폐기)
	if (frameSeq != seq)
	{
		dropCnt++;
		return false;
	}

	return true;
}


uint32_t adc_get_drop_cnt(void) { return dropCnt; }

























