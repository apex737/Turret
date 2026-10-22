#ifndef INC_DEF_H_
#define INC_DEF_H_
/* 공통 헤더: 앱 코드(Core/app) 전체가 가장 먼저 include 한다.
 *  stm32f4xx.h : 레지스터 정의, __disable_irq 같은 CMSIS 코어 함수, HAL 핸들 타입 (stm32f4xx_hal_conf.h 경유)
 *  stdint.h / stdbool.h : uint32_t, bool
 * 호스트(PC) 테스트 빌드에서는 STM32 헤더가 없으므로 Tools/.../hosttest/def.h가 이 파일 대신 쓰인다. */
#include "stm32f4xx.h"
#include <stdint.h>
#include <stdbool.h>

/* 복구할 수 없는 오류: 인터럽트를 끄고 무한 루프에서 멈춘다 (def.c) */
void error_handle(void);




#endif /* INC_DEF_H_ */
