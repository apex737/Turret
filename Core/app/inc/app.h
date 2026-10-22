#ifndef INC_APP_H_
#define INC_APP_H_

/* 앱이 쓰는 주변장치 핸들 묶음. CubeMX가 main.c에 만든 전역 핸들(hadc1 등)의 주소를 main.c가 채워 app_init에 넘긴다.
 * 앱 코드가 main.c의 전역 변수 이름에 직접 기대지 않게 하려는 것. */
typedef struct {
	ADC_HandleTypeDef* hadcMstr;    /* ADC1: 삼중 동시 변환의 마스터. 다중 모드 DMA를 이 핸들로 시작한다 (main.c: &hadc1) */
	ADC_HandleTypeDef* hadcSlv1;    /* ADC2: 슬레이브 1. 마스터와 같은 순간에 두 번째 마이크를 변환 (&hadc2) */
	ADC_HandleTypeDef* hadcSlv2;    /* ADC3: 슬레이브 2. 세 번째 마이크 (&hadc3) */
	TIM_HandleTypeDef* htimSmp;     /* TIM2: 샘플링 타이머. 갱신 이벤트(90 MHz / 1800 = 50 kHz)가 TRGO로 ADC 변환을 트리거한다 (&htim2) */
	TIM_HandleTypeDef* htimAwd;     /* 현재 쓰지 않음. main.c가 채우지 않으므로 NULL이다 */
	UART_HandleTypeDef* huart;      /* USART2 (921600 baud, TX DMA): PC로 가는 유일한 출력. dump와 stream이 같이 쓴다 (&huart2) */
} AppHandle_t;

/* 부팅 시 한 번: DWT 사이클 카운터를 켜고, APP_MODE(app.c)에 맞는 모듈을 초기화한 뒤 ADC 수집을 시작한다 */
void app_init(AppHandle_t* app);
/* 메인 루프 (돌아오지 않음): ADC 프레임을 받아 모드별로 처리하고, UART 송신을 이어 준다 */
void app_main(void);



#endif /* INC_APP_H_ */
