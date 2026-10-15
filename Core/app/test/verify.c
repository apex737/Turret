#include "verify.h"
#include "burst.h"     /* BURST_FRAMES */
#include "preproc.h"
#include "stream.h"
#include <string.h>

static enum { COLLECT, WAIT_RAW, SEND_PCM } s_st;
static int16_t  s_pcm[BURST_FRAMES][PREPROC_CH][PREPROC_OUT];   /* 12 KB */
static uint32_t s_seq[BURST_FRAMES];
static uint32_t s_n, s_k;
static uint8_t  s_flags;

void verify_init(void) { s_st = COLLECT; s_n = 0u; s_k = 0u; }

void verify_on_frame(const dump_frame_t *frame, uint32_t frame_seq)
{
	if (s_st != COLLECT || dump_busy() || stream_busy())
		return;
	if (s_n > 0u && frame_seq != s_seq[s_n - 1u] + 1u)
		s_n = 0u;                                   /* 중간에 끊김 → 처음부터 */
	if (s_n == 0u) {
		preproc_reset();                            /* PC 기준과 같은 출발점: 상태 0 */
		s_flags = DUMP_FLAG_BURST | DUMP_FLAG_VERIFY;
	}

	uint16_t *pl = dump_payload();                  /* ch0[8192] | ch1[8192] | ch2[8192] */
	const uint32_t n_total = BURST_FRAMES * DUMP_N;
	for (uint32_t c = 0; c < DUMP_CH; c++)
		memcpy(&pl[c * n_total + s_n * DUMP_N], (*frame)[c], DUMP_N * sizeof(uint16_t));
	if (preproc_run(*frame, s_pcm[s_n]))
		s_flags |= DUMP_FLAG_CLIP;
	s_seq[s_n++] = frame_seq;

	if (s_n == BURST_FRAMES) {
		(void)dump_send_payload((uint16_t)n_total, frame_seq, s_flags);
		s_st = WAIT_RAW;
		s_k = 0u;
	}
}

void verify_poll(void)
{
	if (s_st == WAIT_RAW && !dump_busy())
		s_st = SEND_PCM;
	if (s_st != SEND_PCM)
		return;
	while (s_k < BURST_FRAMES && stream_free() > 0u) {
		const uint8_t fl = STREAM_FLAG_VERIFY | (s_k == 0u ? STREAM_FLAG_RESYNC : 0u);
		(void)stream_push(s_pcm[s_k], s_seq[s_k], fl, 0u, 0u, 0u);
		s_k++;
	}
	if (s_k == BURST_FRAMES && !stream_busy()) {
		s_st = COLLECT;
		s_n = 0u;
	}
}
