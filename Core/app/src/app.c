// 공통 Include
#include "def.h"
#include "app.h"
#include "adc.h"
#include "tdoa.h"
// UART 파형 디버깅
#include "dump.h"
#include "capture.h"

_Static_assert(TDOA_CH == DUMP_CH && TDOA_FRAME == DUMP_N, "tdoa and dump frame shapes must match");

static uint16_t frame[ADC_CH_CNT][ADC_SAMPLES_PER_HALF];

static uint32_t frame_cnt;   // capture에 넘기는 프레임 번호 (받은 프레임마다 +1)


// 캡처 직후 호출됨: 같은 캡처로 MCU에서 방향을 계산해 결과 패킷으로 보낸다.
// CAPTURE_SEND_RAW 1 : 원파형도 같이 나가므로 PC(doa_live.py)가 같은 frame_seq로 계산해 비교한다.
// CAPTURE_SEND_RAW 0 : 이 결과 패킷만 나간다. (capture.h 에서 선택)
static void on_capture(const dump_frame_t *prev, const dump_frame_t *cur,
                       uint32_t frame_seq, uint8_t flags)
{
	const tdoa_frame_t frames[2] = { prev ? *prev : *cur, *cur };   // 직전 프레임이 없으면 cur만 사용
	tdoa_result_t r;

	const uint32_t t0 = DWT->CYCCNT;
	if (prev)
		tdoa_process(frames, 2u, &r);
	else
		tdoa_process(&frames[1], 1u, &r);
	const uint32_t cycles = DWT->CYCCNT - t0;

	dump_result_t out = {
		.tau       = { r.tau[0], r.tau[1], r.tau[2] },
		.peak      = { r.peak[0], r.peak[1], r.peak[2] },
		.angle_deg = r.angle_deg,
		.norm      = r.norm,
		.onset     = r.onset,
		.win_start = r.win_start,
		.proc_us   = cycles / (SystemCoreClock / 1000000u),
	};
	if (r.valid)
		flags |= DUMP_FLAG_VALID;   // MCU의 신뢰 판정을 PC에 알림. 터렛 제어도 r.valid일 때만 r.angle_deg를 써야 한다
	dump_queue_result(&out, frame_seq, flags);
}


void app_init(AppHandle_t* app)
{
	// 처리 시간 측정용 사이클 카운터(DWT) 켜기
	CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
	DWT->CYCCNT = 0;
	DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;

	tdoa_init();

	 // UART 핸들 등록
	dump_init(app->huart);
	capture_init(NULL);         // 기본값: k_on 4, 잡음 학습 0.5초, holdoff는 모드에 따라 1초 / 0.2초
	capture_set_trigger_cb(on_capture);

	adc_init(app->hadcMstr, app->hadcSlv1, app->hadcSlv2);
	// timer init : TRGO, AWD
	HAL_TIM_Base_Start(app->htimSmp);
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
			frame_cnt++;
			capture_on_frame((const dump_frame_t *)&frame, frame_cnt);
		}
		dump_poll();   // 대기 중인 결과 패킷 송신 (원파형을 보내는 중이면 끝난 뒤에)
	}
}


void HAL_UART_TxCpltCallback(UART_HandleTypeDef *huart)
{
	dump_on_tx_cplt(huart);
}


/* 선택: B1 버튼으로 수동 캡처 */
void HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin)
{
	if (GPIO_Pin == B1_Pin)
		capture_request_manual();
}










