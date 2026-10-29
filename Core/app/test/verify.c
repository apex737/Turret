/*
 * verify.c : 전처리 PC = MCU 검증 모드 (APP_MODE_VERIFY, 절차는 verify.h)
 *
 *  상태 기계 (s_st)
 *    COLLECT  : 연속 8프레임을 모은다. 원본은 dump 송신 버퍼에, 전처리 결과 PCM은 s_pcm에 쌓는다
 *        │ 8프레임이 다 모이면 원본 burst 패킷 송신 시작
 *    WAIT_RAW : 원본 burst(약 49 KB, 약 0.53 s)가 UART로 나가기를 기다린다. 이 동안 들어온 프레임은 버린다
 *        │ dump 송신 끝
 *    SEND_PCM : 같은 8프레임의 PCM 블록을 stream 큐에 빈 칸이 생기는 대로 넣는다
 *        │ 8블록을 다 넣고 stream 송신까지 끝남
 *    COLLECT  (다음 검증 묶음)
 *
 *  원본과 PCM이 같은 UART를 쓰므로, 원본을 다 보낸 뒤에 PCM을 보낸다 (동시에 보낼 수 없음).
 */
#include "verify.h"
#include "burst.h"     /* BURST_FRAMES */
#include "preproc.h"
#include "stream.h"
#include <string.h>

/* s_st : 지금 단계 (위 상태 기계). verify_on_frame은 COLLECT일 때만, verify_poll은 WAIT_RAW·SEND_PCM일 때만 일한다 */
static enum { COLLECT, WAIT_RAW, SEND_PCM } s_st;
/* s_pcm[f] : 이번 묶음 f번째 프레임의 전처리 결과. 원본 송신이 끝날 때까지 여기에 보관했다가 stream으로 보낸다 */
static int16_t  s_pcm[BURST_FRAMES][PREPROC_CH][PREPROC_OUT];   /* 12 KB */
/* s_seq[f] : f번째 프레임의 ADC 프레임 번호. 연속인지 검사하고, PCM 패킷 헤더의 frame_seq로 넣어 PC가 원본과 짝짓게 한다 */
static uint32_t s_seq[BURST_FRAMES];
/* s_n : COLLECT에서 지금까지 모은 프레임 수 (= 다음 프레임이 들어갈 자리, 0 ~ BURST_FRAMES)
 * s_k : SEND_PCM에서 다음에 stream 큐에 넣을 PCM 블록 번호 (0 ~ BURST_FRAMES) */
static uint32_t s_n, s_k;
/* s_flags : 원본 burst 패킷의 DUMP_FLAG_* (BURST | VERIFY, 클리핑이 있었으면 CLIP 추가) */
static uint8_t  s_flags;

void verify_init(void) { s_st = COLLECT; s_n = 0u; s_k = 0u; }

/* main 루프에서 새 ADC 프레임마다 호출 */
void verify_on_frame(
	const dump_frame_t *frame,	// 채널별 50 kHz 원본 uint16[3][1024]
	uint32_t frame_seq			// 그 프레임의 번호 (adc.c ISR이 1씩 올려 매김)
)
{
	/* 모으는 단계가 아니거나 UART가 아직 쓰이는 중이면 이 프레임은 버린다.
	 * dump_busy()가 true면 dump_payload() 버퍼를 DMA가 읽고 있으므로 덮어쓰면 안 된다. */
	if (s_st != COLLECT || dump_busy() || stream_busy())
		return;
	/* 번호가 1씩 이어지지 않으면 시간축이 끊긴 것 → 모은 것을 버리고 이 프레임부터 다시 모은다.
	 * 주의: ADC overrun 재시작(adc_service)은 frame_seq를 이어서 매기므로 이 검사로는 잡히지 않는다. */
	if (s_n > 0u && frame_seq != s_seq[s_n - 1u] + 1u)
		s_n = 0u;                                   /* 중간에 끊김 → 처음부터 */
	if (s_n == 0u) {
		preproc_reset();                            /* PC 기준과 같은 출발점: 상태 0 */
		s_flags = DUMP_FLAG_BURST | DUMP_FLAG_VERIFY;
	}

	/* 원본을 dump 송신 버퍼에 바로 쌓는다 (따로 버퍼를 두지 않아 RAM 48 KB 절약)
	 * pl      : dump 패킷 payload 시작 주소. 채널마다 n_total칸씩 이어 붙인 배치
	 * n_total : 채널당 전체 샘플 수 = 8프레임 × 1024 = 8192
	 * 이 프레임은 각 채널 구역 안의 s_n번째 1024칸에 들어간다 */
	uint16_t *pl = dump_payload();                  /* ch0[8192] | ch1[8192] | ch2[8192] */
	const uint32_t n_total = BURST_FRAMES * DUMP_N;
	for (uint32_t c = 0; c < DUMP_CH; c++)
		memcpy(&pl[c * n_total + s_n * DUMP_N], (*frame)[c], DUMP_N * sizeof(uint16_t));
	/* 같은 프레임을 MCU 전처리로도 돌린다. FIR 상태는 묶음 안에서 프레임끼리 이어진다 (연속 수음과 같은 조건)
	 * 주의 (Step8e 4채널): frame은 app.c의 uint16[4][1024]를 3채널 모양으로 본 것이다. preproc_run은 4채널을 읽으므로
	 * 실제 버퍼(4행)를 그대로 쓴다. 원본 비교(위 memcpy)는 평면 3채널만 보낸다 */
	if (preproc_run(*frame, s_pcm[s_n]))
		s_flags |= DUMP_FLAG_CLIP;
	s_seq[s_n++] = frame_seq;

	if (s_n == BURST_FRAMES) {
		/* 원본 송신 시작. 패킷의 frame_seq = 묶음의 마지막 프레임 번호 (burst.c와 같은 규칙) */
		(void)dump_send_payload((uint16_t)n_total, frame_seq, s_flags);
		s_st = WAIT_RAW;
		s_k = 0u;
	}
}

/* main 루프에서 계속 호출. 원본 송신이 끝나면 PCM 블록을 stream 큐로 넘기고, 다 나가면 다음 묶음을 시작한다 */
void verify_poll(void)
{
	if (s_st == WAIT_RAW && !dump_busy())
		s_st = SEND_PCM;
	if (s_st != SEND_PCM)
		return;
	/* stream 큐는 4칸뿐이라 8블록을 한 번에 못 넣는다. 빈 칸만큼 넣고, 나머지는 다음 호출에서 넣는다 */
	while (s_k < BURST_FRAMES && stream_free() > 0u) {
		/* fl : PCM 패킷 플래그. 모두 VERIFY(원본과 짝), 첫 블록만 RESYNC(FIR 상태 0에서 시작했음을 PC에 알림) */
		const uint8_t fl = STREAM_FLAG_VERIFY | (s_k == 0u ? STREAM_FLAG_RESYNC : 0u);
		(void)stream_push(s_pcm[s_k], s_seq[s_k], fl, 0u, 0u, 0u);   /* 검증 모드에서 drop·ovr·cpu 칸은 쓰지 않아 0 */
		s_k++;
	}
	/* 8블록을 모두 넣었고 UART도 다 비었으면(stream_busy false) 다음 묶음 수집으로 */
	if (s_k == BURST_FRAMES && !stream_busy()) {
		s_st = COLLECT;
		s_n = 0u;
	}
}
