#ifndef VERIFY_H
#define VERIFY_H

/*
 * verify : 전처리 PC = MCU 검증 모드 (Step5 통과 기준 "동일 입력 최종 PCM 최대 차이 ≤ 2 LSB")
 *
 *  1) 연속 8프레임(164 ms)을 모으면서, 같은 프레임을 FIR 상태 0에서 시작해 PCM으로도 만든다
 *  2) 원본 50 kHz는 burst 패킷(type 0x01, DUMP_FLAG_BURST | DUMP_FLAG_VERIFY)으로 먼저 보내고
 *  3) 끝나면 같은 프레임의 PCM 8블록(type 0x03, STREAM_FLAG_VERIFY, 첫 블록 RESYNC)을 보낸다
 *  PC(Tools/verify_preproc.py)는 원본에 같은 계수·같은 규약의 FIR을 돌려 PCM과 비교한다.
 */

#include "dump.h"

void verify_init(void);
void verify_on_frame(const dump_frame_t *frame, uint32_t frame_seq);
void verify_poll(void);    /* main 루프에서 계속 호출 (원본 송신이 끝나면 PCM을 큐에 넣음) */

#endif
