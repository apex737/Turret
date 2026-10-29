/*
 * app.c : 모드 선택(APP_MODE)과 메인 루프. 모듈들을 이어 붙이는 곳이다.
 *
 * STREAM 모드(기본)의 한 프레임 흐름 — 프레임 = ADC 반버퍼 1024샘플 × 4채널 = 20.48 ms (MIC4 = 평면 위, Step8e)
 *
 *   [하드웨어, CPU 없이]  TIM2 50 kHz → ADC1·2·3 동시 변환 → DMA가 adc_buffer에 채움
 *   [ISR]                반버퍼가 차면 adc.c가 "이 절반 준비됨 + 번호(seq)"만 기록
 *   [main 루프]          app_main → adc_get_frame()   채널별로 복사          uint16 [4][1024] @ 50 kHz
 *                        on_stream_frame()
 *                          1) 끊김 판정        번호 건너뜀·overrun → FIR 재시작 + RESYNC/GAP
 *                          2) preproc_run()    FIR + ↓4               → int16 [4][256] @ 12.5 kHz
 *                          3) stream_push()    PCM 패킷(2074 B) 큐에 넣기 → UART DMA → PC
 *                          4) doa_push()       4채널 6쌍 블록 FFT 누적, 0.5 s 창이 끝나면 방위·고도각 → stream_push_doa() (0.25 s마다)
 *                          5) CPU 사용률 계산  → 다음 PCM 패킷 헤더에 실림
 *   [ISR]                UART 송신 완료 → stream.c가 다음 패킷 송신 시작
 *
 *   PC 쪽 (이 펌웨어 밖): Tools/board/stream_capture.py 가 패킷을 받아 wav·결과로 저장한다.
 *   드론 판정(CNN14 분류)과 판정·방위 결합(Tools/fusion/combine.py)은 PC에서 한다. 실시간 연결은 Step10 과제.
 *
 * 시간축: 모든 모듈이 ADC 프레임 번호(seq, 1부터)를 공유한다. PCM 샘플 번호 = (seq − 1) × 256 + 프레임 안 위치.
 */

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
_Static_assert(DOA_CH <= PREPROC_CH && DOA_FRAME == PREPROC_OUT, "doa uses the first DOA_CH rows of the PCM block");
_Static_assert(DUMP_CH <= ADC_CH_CNT && DUMP_N == ADC_SAMPLES_PER_HALF, "test modes use the first DUMP_CH rows of the frame");

#define FRAME_CYCLES  3686400u      // 180 MHz × 20.48 ms = 프레임 하나의 처리 마감(사이클). 이걸 넘기면 다음 반버퍼를 놓친다

/* frame : adc_get_frame()이 DMA 버퍼에서 꺼내 채널별로 정리해 둔 프레임 하나 (uint16 [4][1024] = 8 KB).
 *         SNAP·BURST 시험 모드는 앞 3채널(평면 MIC1~3)만 dump_frame_t로 본다.
 *         DMA 버퍼를 직접 쓰지 않고 복사하는 이유: 처리하는 동안 DMA가 그 절반을 다시 덮어쓸 수 있어서.
 *         모든 모드가 같은 버퍼를 쓰고, 다음 프레임이 올 때까지만 유효하다. */
static uint16_t frame[ADC_CH_CNT][ADC_SAMPLES_PER_HALF];

#if APP_MODE == APP_MODE_SNAP
// 캡처 직후 호출됨: 같은 캡처로 MCU에서 방향을 계산해 결과 패킷으로 보낸다.
// CAPTURE_SEND_RAW 1 : 원파형도 같이 나가므로 PC(doa_live.py)가 같은 frame_seq로 계산해 비교한다.
// CAPTURE_SEND_RAW 0 : 이 결과 패킷만 나간다. (capture.h 에서 선택)
static void on_capture(
	const dump_frame_t *prev,	// 트리거 직전 프레임 (없으면 NULL → cur 하나만 쓴다)
	const dump_frame_t *cur,	// 트리거가 걸린 프레임
	uint32_t frame_seq,			// cur의 ADC 프레임 번호 → 결과 패킷의 frame_seq (같은 번호의 원파형과 짝)
	uint8_t flags				// capture.c가 붙인 DUMP_FLAG_* (MANUAL, PRETRIG, CLIP). 여기서 VALID를 더한다
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
static void on_stream_frame(
	uint32_t seq	// adc_get_frame이 돌려준 이번 프레임 번호 (1부터, ISR이 매김). 데이터는 전역 frame에 있다
)
{
	// 정적변수 선언
	static bool     first = true;	// 부팅 후 첫 프레임
	static uint32_t last_seq; 		// 직전 프레임 번호. seq가 last_seq + 1이 아니면 프레임을 놓친 것
	static uint32_t last_ovr; 		// 직전의 overrun 누계. ADC가 멈추면 seq1 -> [ADC 재시작 시간] -> seq2 사이에 유실된 프레임 수를 감지
	static uint32_t last_qdrop;		// 직전의 송신 큐 유실 누계. 늘었으면 PC가 받을 샘플이 빠진 것 ??
	static uint8_t  cpu_pct;		// 직전 프레임의 처리 시간 [%]
	static int16_t  pcm[PREPROC_CH][PREPROC_OUT]; // 전처리 출력 int16 [4][256]. stream_push가 패킷으로 복사하고 doa_push가 링버퍼로 복사한다

	const uint32_t t0 = DWT->CYCCNT;
	/* ---------------------------------- 처리 시간 측정 시작 (180 MHz 사이클) ---------------------------------- */

	const uint32_t ovr = adc_get_ovr_cnt();
	const uint32_t qdrop = stream_get_qdrop_cnt();
	uint8_t flags = 0u;                       // 이 PCM 패킷에 붙일 STREAM_FLAG_* (stream.h)

	/* 1) 끊김 판정. MCU 입력 자체가 끊겼으면(번호 건너뜀·overrun) FIR 상태를 0으로 지운다.
	 *    지우지 않으면 끊긴 앞뒤 파형을 FIR이 이어 붙여 실제로 없던 파형이 만들어진다 (I1) */
	if (first || seq != last_seq + 1u || ovr != last_ovr) {
		preproc_reset();
		flags |= STREAM_FLAG_RESYNC | (first ? 0u : STREAM_FLAG_GAP);
	}
	/* 송신 큐 유실: MCU의 입력·FIR은 연속이지만 PC 쪽에서 샘플이 빠졌다 → GAP만 (FIR은 그대로 둔다) */
	if (qdrop != last_qdrop)
		flags |= STREAM_FLAG_GAP;
	first = false; last_seq = seq; last_ovr = ovr; last_qdrop = qdrop;

	/* 2) 전처리: 50 kHz uint16 [4][1024] → 12.5 kHz int16 [4][256]. 클리핑 샘플이 있었으면 표시만 한다 */
	if (preproc_run((const uint16_t (*)[PREPROC_IN])frame, pcm))
		flags |= STREAM_FLAG_CLIP;
	/* 3) PCM 패킷을 송신 큐에 넣는다. 큐(4칸)가 가득 차면 버려지고 qdrop이 올라간다 (다음 프레임에서 GAP으로 표시됨) */
	(void)stream_push(pcm, seq, flags, adc_get_drop_cnt(), ovr, cpu_pct);

	/* 4) 방향 추정: 같은 PCM 4채널을 doa.c에 넣는다 (방위 + 고도각, Step8e). 0.5 s 창이 끝나는 프레임(약 12프레임마다)에만 결과가 나온다.
	 *    송신 큐 유실(GAP만)은 MCU 입력과 무관하므로 전처리를 다시 시작했을 때(RESYNC)만 끊김으로 본다 */
	doa_result_t r;
	if (doa_push((const int16_t (*)[DOA_FRAME])pcm, seq, (flags & STREAM_FLAG_RESYNC) != 0u, &r))
		(void)stream_push_doa(&r, seq);



	/* ---------------------------------- 처리 시간 측정 종료 ---------------------------------- */
	const uint32_t cyc = DWT->CYCCNT - t0;   // 이번 프레임의 전처리 + 큐 적재 + 방위 추정. 다음 패킷에 실림


	/* 5) CPU 사용률 = 이번 프레임 처리 사이클 / 프레임 마감 사이클, 올림. 100%를 넘으면 다음 반버퍼를 놓치기 시작한다.
		 *    판정은 평균이 아니라 가장 무거운 프레임(창이 끝나는 프레임)으로 한다 */
	cpu_pct = (uint8_t)((cyc * 100u + FRAME_CYCLES - 1u) / FRAME_CYCLES);
}
#endif

// doa.c의 계산 시간 측정용
uint32_t doa_now_cycles(void)
{
	return DWT->CYCCNT;
}


void app_init(
	AppHandle_t* app	// main.c가 채운 주변장치 핸들 묶음 (ADC 3개, TIM2, UART2. app.h)
)
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


/* 메인 루프: 인터럽트가 "준비됐다"고 표시해 둔 일을 여기서 처리한다 (ISR은 짧게, 무거운 계산은 main에서).
 * 한 바퀴가 아주 짧아서, 새 프레임이 없을 때는 송신 이어 주기와 overrun 확인만 계속 돈다. */
void app_main(void)
{
	uint32_t seq;   // adc_get_frame이 돌려주는 프레임 번호 (1부터, ISR이 매김)
	while(1)
	{
		if (adc_get_frame(frame, &seq))   // 새 반버퍼가 있으면 frame에 복사하고 true
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


/* UART 송신 완료 ISR. dump와 stream이 같은 UART를 쓰므로 둘 다에 알리고, 각자 자기 송신인지 판단한다 */
void HAL_UART_TxCpltCallback(
	UART_HandleTypeDef *huart	// 송신이 끝난 UART. HAL이 넘겨준다
)
{
	dump_on_tx_cplt(huart);
	stream_on_tx_cplt(huart);
}


/* B1 버튼: 스냅 모드 = 수동 캡처, 연속 모드 = 방위 추정 배경 다시 배우기 */
void HAL_GPIO_EXTI_Callback(
	uint16_t GPIO_Pin	// 인터럽트를 낸 핀. B1_Pin(파란 버튼)일 때만 반응한다
)
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
