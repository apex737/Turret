/*
 * burst.c : 50 kHz 원본 3채널을 끊김 없는 8프레임(164 ms) 묶음으로 PC에 보낸다 (APP_MODE_BURST, 설명은 burst.h)
 *
 *  흐름: 프레임이 올 때마다 dump 송신 버퍼에 이어 붙인다 → 8개가 차면 송신 시작 → 송신(약 0.53 s) 동안 온 프레임은 버림 → 다시 0부터
 */
#include "burst.h"
#include "capture.h"   /* CLIP_LO, CLIP_HI */
#include <string.h>

static uint32_t s_filled;        /* 지금 burst에 채운 프레임 수 (0 ~ BURST_FRAMES). 다음 프레임이 들어갈 자리이기도 하다 */
static uint32_t s_last_drop;     /* 직전 프레임을 받을 때의 drop 카운터. 이번 값과 다르면 그 사이에 프레임을 놓친 것 */
static uint32_t s_restart;       /* 유실로 버린 burst 수 (디버거로 보는 진단용, burst_get_restart_cnt) */
static uint8_t  s_flags;         /* 이번 burst의 플래그 (클리핑 등). 새 burst를 시작할 때 BURST로 초기화 */

void burst_init(void)
{
    s_filled = 0u;
    s_last_drop = 0u;
    s_restart = 0u;
    s_flags = 0u;
}

uint32_t burst_get_restart_cnt(void) { return s_restart; }

/* main 루프에서 새 ADC 프레임마다 호출 (인자 설명은 burst.h)
 *  frame     : 채널별 50 kHz 원본 uint16[3][1024]
 *  frame_seq : 그 프레임의 번호. burst가 다 차면 패킷의 frame_seq로 쓴다
 *  drop_cnt  : adc_get_drop_cnt() 값. 직전 호출 때와 비교해 중간 유실을 알아낸다 */
void burst_on_frame(
	const dump_frame_t *frame,
	uint32_t frame_seq,
	uint32_t drop_cnt
)
{
    /* dropped : 직전 프레임 이후 ADC 프레임 유실이 있었나. 비교 기준(s_last_drop)은 프레임을 버리는 경우에도 매번 갱신한다
     * 주의: ADC overrun 재시작은 drop이 아니라 ovr 카운터만 올리므로 이 검사로는 잡히지 않는다 */
    const bool dropped = (drop_cnt != s_last_drop);
    s_last_drop = drop_cnt;

    // 예외처리 (Busy, 프레임 누수)
    if (dump_busy()) {               /* 이전 burst를 보내는 중: 버퍼를 건드릴 수 없으니 이 프레임은 버림 */
        s_filled = 0u;
        return;
    }
    if (dropped && s_filled > 0u) {  /* 모으는 도중 프레임을 놓침 → 시간축이 끊겼으니 처음부터 */
        s_filled = 0u;
        s_restart++;
    }
    /* s_filled == 0일 때 유실이 있었다면 버릴 것이 없으니 restart로 세지 않고, 이 프레임을 새 burst의 첫 프레임으로 쓴다 */

    // 새 burst의 첫 프레임: 플래그를 BURST만 남기고 지운다 (지난 burst의 CLIP이 이어지지 않게)
    if (s_filled == 0u) {
        s_flags = DUMP_FLAG_BURST;
    }

    /* payload 배치: ch0[8192] | ch1[8192] | ch2[8192]. 이 프레임은 각 채널 안의 s_filled번째 1024칸
     * pl      : dump 패킷 payload 시작 주소 (dump_busy()가 false일 때만 써도 된다)
     * n_total : 채널당 전체 샘플 수 = BURST_FRAMES × DUMP_N = 8192 */
    uint16_t *pl = dump_payload();
    const uint32_t n_total = BURST_FRAMES * DUMP_N;
    for (uint32_t c = 0; c < DUMP_CH; c++) {
        const uint16_t *src = (*frame)[c];   /* src : 이 프레임의 c번 채널 1024샘플 */
        memcpy(&pl[c * n_total + s_filled * DUMP_N], src, DUMP_N * sizeof(uint16_t));
        /* 클리핑 검사. 이번 burst에서 이미 찾았으면 더 볼 필요가 없어 건너뛴다 (CPU 절약) */
        if (!(s_flags & DUMP_FLAG_CLIP)) {
            for (uint32_t i = 0; i < DUMP_N; i++) {
                if (src[i] <= CLIP_LO || src[i] >= CLIP_HI) {
                	s_flags |= DUMP_FLAG_CLIP;
                	break;
                }
            }
        }
    }

    /* 8프레임이 다 찼으면 헤더·CRC를 붙여 DMA 송신을 시작하고, 다음 burst를 위해 0으로 돌린다.
     * 송신이 끝날 때까지는 위의 dump_busy() 검사로 새 프레임이 버퍼를 덮어쓰지 못한다 */
    if (++s_filled == BURST_FRAMES) {
        (void)dump_send_payload((uint16_t)n_total, frame_seq, s_flags);   /* frame_seq = burst의 마지막 프레임 번호 */
        s_filled = 0u;
    }
}
