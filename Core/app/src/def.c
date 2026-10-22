/*
 * def.c
 *
 *  Created on: Oct 7, 2026
 *      Author: user
 */

#include "def.h"

/* 복구할 수 없는 오류에서 부르는 정지 함수 (HAL 시작 실패, CMSIS 초기화 실패 등 = 대개 설정·코드 버그)
 *  - 모든 인터럽트를 끈다: DMA·UART·ADC 콜백이 더 돌지 않게 해서, 멈춘 순간의 변수 값이 그대로 남는다
 *  - 무한 루프에서 멈춘다: 디버거를 붙여 Pause 하면 여기서 서 있고, 콜 스택으로 누가 불렀는지 볼 수 있다
 *  워치독을 쓰지 않으므로 리셋 버튼을 누를 때까지 이 상태로 있다. 호스트 테스트(Tools/.../hosttest)는 이 함수를
 *  "error 출력 후 exit(1)"로 바꿔 끼운다. */
void error_handle(void) {
	__disable_irq();
	while(1) {

	}
}
