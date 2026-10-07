#ifndef INC_APP_H_
#define INC_APP_H_

typedef struct {
	ADC_HandleTypeDef* hadcMstr;
	ADC_HandleTypeDef* hadcSlv1;
	ADC_HandleTypeDef* hadcSlv2;
	TIM_HandleTypeDef* htimSmp;
	TIM_HandleTypeDef* htimAwd;
	UART_HandleTypeDef* huart;
} AppHandle_t;
void app_init(AppHandle_t* app);
void app_main(void);



#endif /* INC_APP_H_ */
