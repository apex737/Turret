#include "def.h"
#include "app.h"
#include "adc.h"
#include <math.h>

static uint16_t frame[ADC_CH_CNT][ADC_SAMPLES_PER_HALF];

/* CubeMonitor 관찰용: static 없이 전역 + volatile → ELF 심볼로 보이고, 최적화로 사라지지 않음 */
volatile uint16_t mon_mean[ADC_CH_CNT];   // DC 바이어스 (평균)
volatile uint16_t mon_p2p[ADC_CH_CNT];    // 피크-피크 (max - min)
volatile float    mon_rms[ADC_CH_CNT];    // DC 제거 후 RMS (소리 크기)
volatile uint32_t mon_frame_cnt;          // 계속 증가하면 DMA/콜백이 살아있음
volatile uint32_t mon_drop_cnt;

static void mic_stats(void)
{
	for (uint32_t ch = 0; ch < ADC_CH_CNT; ch++)
	{
		uint32_t sum = 0;
		uint16_t mn = 0xFFFF, mx = 0;

		for (uint32_t i = 0; i < ADC_SAMPLES_PER_HALF; i++)
		{
			uint16_t x = frame[ch][i];
			sum += x;
			if (x < mn) mn = x;
			if (x > mx) mx = x;
		}

		float mean = (float)sum / ADC_SAMPLES_PER_HALF;
		float acc = 0.0f;
		for (uint32_t i = 0; i < ADC_SAMPLES_PER_HALF; i++)
		{
			float d = (float)frame[ch][i] - mean;
			acc += d * d;
		}

		mon_mean[ch] = (uint16_t)mean;
		mon_p2p[ch]  = mx - mn;
		mon_rms[ch]  = sqrtf(acc / ADC_SAMPLES_PER_HALF);
	}
}


void app_init(AppHandle_t* app)
{
	adc_init(app->hadcMstr, app->hadcSlv1, app->hadcSlv2);
	// timer init : TRGO, AWD
	HAL_TIM_Base_Start(app->htimSmp);


	// uart init



}

void app_main(void)
/* 구현 전략
 * 1) 마이크 모듈 파형 테스트
 * 2) ADC-DMA 핑퐁 버퍼링 -> 지연 측정 & 지터 ??
 * 3) DMA 버퍼의 값을 안전하게 복사하고 uint16_t 로 형변환
 * 4) GCC-PHAT
 * 	 - 1) 3-MIC FFT (Generalized Cross-Correlation)
 * 	 - 2) BPF
 * 	 - 3) PHAT (Phase Transform)
 * 	 - 4) IFFT
 * 	 - 5) Find Max (피크)
 * 5) 후처리
 * 	 - 1) 2차 보간 (Fs를 높여주는 효과.. 원리?)
 * 	 - 2) LSE 오차보정
 * 	 - 3) 시간차 -> 각도 변환
 * */
{
	while(1)
	{
		if (adc_get_frame(frame))
		{
			mic_stats();
			mon_frame_cnt++;
		}
		mon_drop_cnt = adc_get_drop_cnt();
	}
}


