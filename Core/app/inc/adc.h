#ifndef INC_ADC_H_
#define INC_ADC_H_

#include "def.h"

/*
 * adc : ADC 3개 동시 변환 (TIM2 트리거 50 kHz) + DMA 핑퐁 버퍼. 반버퍼 = 1024샘플 x 3ch = 20.48 ms
 *
 *  - 프레임 번호(seq)는 DMA 반버퍼 콜백(ISR)이 매긴다. 받은 횟수가 아니라 "만들어진" 순서라서,
 *    main이 늦어 놓친 프레임은 번호가 건너뛰는 것으로 드러난다.
 *  - 유실의 종류를 구분해 센다
 *      drop : 반버퍼를 다음 덮어쓰기 전에 가져가지 못함 (main이 늦음) 또는 복사 중 덮어써짐
 *      ovr  : ADC 하드웨어 overrun (DMA가 ADC 데이터를 제때 못 읽음) → DMA가 멈추므로 adc_service()가 재시작
 */

#define ADC_CH_CNT 			  ( 3U )
#define ADC_SAMPLES_PER_HALF  ( 1024U )
#define ADC_HALF_LENGTH       (ADC_CH_CNT * ADC_SAMPLES_PER_HALF)
#define ADC_DMA_LENGTH        (2U * ADC_HALF_LENGTH)

/* 슬레이브 → 마스터(DMA) → 타이머 순으로 시작한다. 타이머를 마지막에 켜야 buffer[0] = ADC1이 보장된다 */
void adc_init(ADC_HandleTypeDef *hadcMstr,
              ADC_HandleTypeDef *hadcSlv1,
              ADC_HandleTypeDef *hadcSlv2,
              TIM_HandleTypeDef *htim);

/* 준비된 반버퍼를 채널별로 복사한다. 성공하면 true와 함께 그 반버퍼의 번호를 *seq에 돌려준다.
 * 번호는 데이터와 같은 임계 구역에서 읽으므로 다른 프레임의 번호와 짝지어지지 않는다. */
bool     adc_get_frame(uint16_t out[ADC_CH_CNT][ADC_SAMPLES_PER_HALF], uint32_t *seq);

/* main 루프에서 계속 호출. ADC overrun이 났으면 타이머·ADC·DMA를 멈췄다가 처음 순서대로 다시 시작한다. */
void     adc_service(void);

uint32_t adc_get_drop_cnt(void);
uint32_t adc_get_ovr_cnt(void);

#endif /* INC_ADC_H_ */
