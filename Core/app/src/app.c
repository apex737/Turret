// 공통 Include
#include "def.h"
#include "app.h"
#include "adc.h"
#include "tdoa.h"
#include "preproc.h"
#include "stream.h"
#include "doa.h"

// UART 디버깅·녹음 모드
#include "dump.h"
#include "capture.h"
#include "burst.h"
#include "verify.h"

/* 동작 모드 (컴파일 시 하나 선택)
 *  APP_MODE_SNAP   : 기존 스냅 모드. 소리 트리거 → TDOA → 결과/원파형 송신           수신: Tools/doa_live.py
 *  APP_MODE_BURST  : 트리거 없이 164 ms 연속 원파형(50 kHz)을 반복 송신 (Step5 재생 녹음) 수신: Tools/burst_rx.py
 *  APP_MODE_STREAM : 50 kHz → FIR·↓4 → 12.5 kHz int16 PCM 연속 송신 (Step5 연속 수음)  수신: Tools/stream_capture.py
 *                    + 같은 PCM으로 방위 추정(D1, doa.c), 0.25 s마다 결과 패킷. B1 버튼 = 배경 다시 배우기
 *  APP_MODE_VERIFY : 같은 8프레임의 원본과 PCM을 함께 송신 → PC/MCU 전처리 비교       수신: Tools/verify_preproc.py */
#define APP_MODE_SNAP   0
#define APP_MODE_BURST  1
#define APP_MODE_STREAM 2
#define APP_MODE_VERIFY 3
#ifndef APP_MODE
#define APP_MODE APP_MODE_STREAM
#endif

_Static_assert(TDOA_CH == DUMP_CH && TDOA_FRAME == DUMP_N, "tdoa and dump frame shapes must match");
_Static_assert(PREPROC_CH == ADC_CH_CNT && PREPROC_IN == ADC_SAMPLES_PER_HALF, "preproc and adc frame shapes must match");

#define FRAME_CYCLES  3686400u      // 180 MHz × 20.48 ms

static uint16_t frame[ADC_CH_CNT][ADC_SAMPLES_PER_HALF];

#if APP_MODE == APP_MODE_SNAP
// 캡처 직후 호출됨: 같은 캡처로 MCU에서 방향을 계산해 결과 패킷으로 보낸다.
// CAPTURE_SEND_RAW 1 : 원파형도 같이 나가므로 PC(doa_live.py)가 같은 frame_seq로 계산해 비교한다.
// CAPTURE_SEND_RAW 0 : 이 결과 패킷만 나간다. (capture.h 에서 선택)
static void on_capture(
	const dump_frame_t *prev,
	const dump_frame_t *cur,
	uint32_t frame_seq,
	uint8_t flags
)
{
	const tdoa_frame_t frames[2] = { prev ? *prev : *cur, *cur };   // 직전 프레임이 없으면 cur만 사용
	tdoa_result_t r;

	const uint32_t t0 = DWT->CYCCNT;			// 사이클 측정 시작

	if (prev)
		tdoa_process(frames, 2u, &r);
	else
		tdoa_process(&frames[1], 1u, &r);

	const uint32_t cycles = DWT->CYCCNT - t0;  // 사이클 측정 종료

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
#endif

#if APP_MODE == APP_MODE_STREAM
/* 연속 수음: 프레임 하나 → PCM 한 블록. 끊김이 있으면 FIR 상태를 지우고 표시한다.
 *  - ADC 번호가 건너뜀 / overrun → 샘플이 빠졌고 FIR 상태도 끊긴 입력을 이어 붙이면 안 됨 → RESYNC | GAP
 *  - 송신 큐 유실 → MCU의 FIR은 연속이지만 PC가 받은 샘플이 빠짐 → GAP만 */
static void on_stream_frame(uint32_t seq)
{
	static bool     first = true;
	static uint32_t last_seq, last_ovr, last_qdrop;
	static uint8_t  cpu_pct;
	static int16_t  pcm[PREPROC_CH][PREPROC_OUT];

	const uint32_t t0 = DWT->CYCCNT;
	const uint32_t ovr = adc_get_ovr_cnt(), qdrop = stream_get_qdrop_cnt();
	uint8_t flags = 0u;
	if (first || seq != last_seq + 1u || ovr != last_ovr) {
		preproc_reset();
		flags |= STREAM_FLAG_RESYNC | (first ? 0u : STREAM_FLAG_GAP);
	}
	if (qdrop != last_qdrop)
		flags |= STREAM_FLAG_GAP;
	first = false; last_seq = seq; last_ovr = ovr; last_qdrop = qdrop;

	if (preproc_run((const uint16_t (*)[PREPROC_IN])frame, pcm))
		flags |= STREAM_FLAG_CLIP;
	(void)stream_push(pcm, seq, flags, adc_get_drop_cnt(), ovr, cpu_pct);

	// 방위 추정: 송신 큐 유실(GAP만)은 MCU 입력과 무관하므로 전처리를 다시 시작했을 때만 끊김으로 본다
	doa_result_t r;
	if (doa_push((const int16_t (*)[DOA_FRAME])pcm, seq, (flags & STREAM_FLAG_RESYNC) != 0u, &r))
		(void)stream_push_doa(&r, seq);

	const uint32_t cyc = DWT->CYCCNT - t0;   // 이번 프레임의 전처리 + 큐 적재 + 방위 추정. 다음 패킷에 실림
	cpu_pct = (uint8_t)((cyc * 100u + FRAME_CYCLES - 1u) / FRAME_CYCLES);
}
#endif

// doa.c의 계산 시간 측정용
uint32_t doa_now_cycles(void)
{
	return DWT->CYCCNT;
}


void app_init(AppHandle_t* app)
{
	// 처리 시간 측정용 사이클 카운터(DWT) 켜기
	CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
	DWT->CYCCNT = 0;
	DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;

	dump_init(app->huart);
	stream_init(app->huart);
	preproc_reset();
#if APP_MODE == APP_MODE_SNAP
	tdoa_init();
	capture_init(NULL);         // 기본값: k_on 4, 잡음 학습 0.5초, holdoff는 모드에 따라 1초 / 0.2초
	capture_set_trigger_cb(on_capture);
#elif APP_MODE == APP_MODE_BURST
	burst_init();
#elif APP_MODE == APP_MODE_STREAM
	doa_init();
#elif APP_MODE == APP_MODE_VERIFY
	verify_init();
#endif

	adc_init(app->hadcMstr, app->hadcSlv1, app->hadcSlv2, app->htimSmp);   // 타이머는 adc_init이 마지막에 켠다
}


void app_main(void)
{
	uint32_t seq;
	while(1)
	{
		if (adc_get_frame(frame, &seq))
		{
#if APP_MODE == APP_MODE_SNAP
			capture_on_frame((const dump_frame_t *)&frame, seq);
#elif APP_MODE == APP_MODE_BURST
			burst_on_frame((const dump_frame_t *)&frame, seq, adc_get_drop_cnt());
#elif APP_MODE == APP_MODE_STREAM
			on_stream_frame(seq);
#elif APP_MODE == APP_MODE_VERIFY
			verify_on_frame((const dump_frame_t *)&frame, seq);
#endif
		}
		adc_service();    // ADC overrun이 났으면 재시작
#if APP_MODE == APP_MODE_VERIFY
		verify_poll();
#endif
		stream_poll();    // UART가 비면 대기 중인 PCM 송신
		dump_poll();      // 대기 중인 결과 패킷 송신 (스냅 모드)
	}
}


void HAL_UART_TxCpltCallback(UART_HandleTypeDef *huart)
{
	dump_on_tx_cplt(huart);
	stream_on_tx_cplt(huart);
}


/* B1 버튼: 스냅 모드 = 수동 캡처, 연속 모드 = 방위 추정 배경 다시 배우기 */
void HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin)
{
#if APP_MODE == APP_MODE_SNAP
	if (GPIO_Pin == B1_Pin)
		capture_request_manual();
#elif APP_MODE == APP_MODE_STREAM
	if (GPIO_Pin == B1_Pin)
		doa_request_bg();
#else
	(void)GPIO_Pin;
#endif
}
