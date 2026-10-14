#include "burst.h"
#include "capture.h"   /* CLIP_LO, CLIP_HI */
#include <string.h>

static uint32_t s_filled;        /* 지금 burst에 채운 프레임 수 */
static uint32_t s_last_drop;     /* 직전 프레임을 받을 때의 drop 카운터 */
static uint32_t s_restart;       /* 유실로 버린 burst 수 */
static uint8_t  s_flags;         /* 이번 burst의 플래그 (클리핑 등) */

void burst_init(void)
{
    s_filled = 0u;
    s_last_drop = 0u;
    s_restart = 0u;
    s_flags = 0u;
}

uint32_t burst_get_restart_cnt(void) { return s_restart; }

void burst_on_frame(const dump_frame_t *frame, uint32_t frame_seq, uint32_t drop_cnt)
{
    const bool dropped = (drop_cnt != s_last_drop);
    s_last_drop = drop_cnt;

    if (dump_busy()) {               /* 이전 burst를 보내는 중: 버퍼를 건드릴 수 없으니 이 프레임은 버림 */
        s_filled = 0u;
        return;
    }
    if (dropped && s_filled > 0u) {  /* 모으는 도중 프레임을 놓침 → 시간축이 끊겼으니 처음부터 */
        s_filled = 0u;
        s_restart++;
    }
    if (s_filled == 0u) {
        s_flags = DUMP_FLAG_BURST;
    }

    /* payload 배치: ch0[8192] | ch1[8192] | ch2[8192]. 이 프레임은 각 채널 안의 s_filled번째 1024칸 */
    uint16_t *pl = dump_payload();
    const uint32_t n_total = BURST_FRAMES * DUMP_N;
    for (uint32_t c = 0; c < DUMP_CH; c++) {
        const uint16_t *src = (*frame)[c];
        memcpy(&pl[c * n_total + s_filled * DUMP_N], src, DUMP_N * sizeof(uint16_t));
        if (!(s_flags & DUMP_FLAG_CLIP)) {
            for (uint32_t i = 0; i < DUMP_N; i++) {
                if (src[i] <= CLIP_LO || src[i] >= CLIP_HI) { s_flags |= DUMP_FLAG_CLIP; break; }
            }
        }
    }

    if (++s_filled == BURST_FRAMES) {
        (void)dump_send_payload((uint16_t)n_total, frame_seq, s_flags);   /* frame_seq = burst의 마지막 프레임 번호 */
        s_filled = 0u;
    }
}
