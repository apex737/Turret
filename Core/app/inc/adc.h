#ifndef INC_ADC_H_
#define INC_ADC_H_

#include "def.h"


#define ADC_CH_CNT 			  ( 3U )
#define ADC_SAMPLES_PER_HALF  ( 1024U )
#define ADC_HALF_LENGTH       (ADC_CH_CNT * ADC_SAMPLES_PER_HALF)
#define ADC_DMA_LENGTH        (2U * ADC_HALF_LENGTH)

//typedef struct {
//	volatile bool XferHalf;
//	volatile bool XferCplt;
//	volatile bool overrun;
//} BufStat_t;

void adc_init(ADC_HandleTypeDef *hadcMstr,
              ADC_HandleTypeDef *hadcSlv1,
              ADC_HandleTypeDef *hadcSlv2);

bool     adc_get_frame(uint16_t out[ADC_CH_CNT][ADC_SAMPLES_PER_HALF]);
uint32_t adc_get_drop_cnt(void);




#endif /* INC_ADC_H_ */
