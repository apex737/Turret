#ifndef BURST_H
#define BURST_H

/*
 * burst : 50 kHz 3채널을 끊김 없이 BURST_FRAMES 프레임(8 x 20.48 ms = 164 ms)씩 모아 PC로 보낸다. (Step5)
 *
 *  - 트리거 없이 계속 반복한다: 모음(164 ms) → 송신(약 0.53 s, 이 동안 들어온 프레임은 버림) → 다시 모음
 *  - 프레임은 dump의 송신 버퍼(payload 영역)에 바로 채운다. 따로 모아 둘 버퍼가 없어 RAM 48 KB를 아낀다
 *  - 모으는 도중 ADC 프레임 유실(drop)이 생기면 그 burst를 버리고 처음부터 다시 모은다 → 받은 burst는 항상 연속
 *  - 패킷 형식은 RAW(type 0x01) 그대로, n = 8192, flags에 DUMP_FLAG_BURST. 수신: Tools/burst_rx.py
 */

#include "dump.h"

#define BURST_FRAMES  8u      /* burst 하나의 프레임 수 (DUMP_MAX_FRAMES 이하) */

_Static_assert(BURST_FRAMES <= DUMP_MAX_FRAMES, "burst must fit in the dump buffer");

void burst_init(void);

/* main 루프에서 새 프레임을 받을 때마다 호출.
 * frame_seq: 받은 프레임 번호 (1씩 증가), drop_cnt: adc_get_drop_cnt() 값 (바뀌었으면 중간에 프레임을 놓친 것) */
void burst_on_frame(const dump_frame_t *frame, uint32_t frame_seq, uint32_t drop_cnt);

/* 지금까지 버린 burst 수 (중간 유실 때문에) */
uint32_t burst_get_restart_cnt(void);

#endif
