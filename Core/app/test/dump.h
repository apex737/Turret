#ifndef DUMP_H
#define DUMP_H

#include "main.h"      /* UART_HandleTypeDef */
#include <stdint.h>
#include <stdbool.h>

/*
 * 프레임 덤프 패킷 v2 (little endian)
 *
 *  off  size  field
 *   0    4    sync       = FF FF FF FF
 *   4    1    ver        = 2
 *   5    1    type       = 0x01 (RAW_ADC)
 *   6    1    ch         = 3
 *   7    1    flags      DUMP_FLAG_*
 *   8    4    seq        송신 패킷 번호 (누락 검출)
 *  12    4    frame_seq  마지막 프레임의 ADC 프레임 번호 (MCU 결과 패킷과 짝짓기용)
 *  16    2    n          채널당 샘플 수 = nframes * 1024
 *  18    2    len        payload 바이트 수 = ch * n * 2
 *  20  len    payload    ch0[n] | ch1[n] | ch2[n]  (uint16 LE, 각 채널 안에서 프레임 순서대로 이어붙임)
 * 20+len 2    crc16      CRC-16/CCITT-FALSE, 범위 = ver ~ payload 끝 (sync 제외)
 */

#define DUMP_N            1024u     /* 프레임당 샘플 수 */
#define DUMP_CH           3u
#define DUMP_MAX_FRAMES   2u        /* 직전 프레임 + 트리거 프레임 */

#define DUMP_FLAG_CLIP    0x01u     /* 클리핑 샘플 있음 */
#define DUMP_FLAG_MANUAL  0x02u     /* 수동 트리거 (버튼 등) */
#define DUMP_FLAG_PRETRIG 0x04u     /* payload 앞 절반 = 트리거 직전 프레임 */

typedef uint16_t dump_frame_t[DUMP_CH][DUMP_N];

void dump_init(UART_HandleTypeDef *huart);
bool dump_busy(void);

/* frames[0..nframes-1]을 시간 순서대로 이어붙여 한 패킷으로 송신.
 * 송신 버퍼로 복사한 뒤 DMA를 시작하므로, 반환 후 frames는 바로 재사용해도 된다.
 * 이전 송신이 끝나지 않았거나 nframes가 범위를 벗어나면 false. */
bool dump_send_frames(const dump_frame_t *const frames[], uint8_t nframes,
                      uint32_t frame_seq, uint8_t flags);

/* 프레임 하나만 보낼 때 */
static inline bool dump_send(const dump_frame_t *frame, uint32_t frame_seq, uint8_t flags)
{
    const dump_frame_t *const f[1] = { frame };
    return dump_send_frames(f, 1u, frame_seq, flags);
}

/* HAL_UART_TxCpltCallback 안에서 호출 */
void dump_on_tx_cplt(UART_HandleTypeDef *huart);

#endif
