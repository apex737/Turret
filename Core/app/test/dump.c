#include "dump.h"
#include <string.h>

#define DUMP_SYNC       0xFFFFFFFFu
#define DUMP_VER        2u
#define DUMP_TYPE_RAW   0x01u

typedef struct __attribute__((packed)) {
    uint32_t sync;
    uint8_t  ver;
    uint8_t  type;
    uint8_t  ch;
    uint8_t  flags;
    uint32_t seq;
    uint32_t frame_seq;
    uint16_t n;
    uint16_t len;
} dump_hdr_t;

_Static_assert(sizeof(dump_hdr_t) == 20, "header must be 20 bytes");

#define FRAME_CH_BYTES  (DUMP_N * 2u)                                  /* 2048 B */
#define MAX_PAYLOAD     (DUMP_CH * DUMP_MAX_FRAMES * FRAME_CH_BYTES)    /* 12288 B */
#define MAX_PKT         (sizeof(dump_hdr_t) + MAX_PAYLOAD + 2u)         /* 12310 B */

/* DMA가 읽는 동안 건드리면 안 되므로 스택이 아닌 정적 버퍼 */
static uint8_t tx_buf[MAX_PKT] __attribute__((aligned(4)));

static UART_HandleTypeDef *s_huart;
static volatile bool       s_busy;
static uint32_t            s_seq;

/* CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF)
 * Python: binascii.crc_hqx(data, 0xFFFF) 와 같은 값
 * 12 KB 기준 약 2 ms @180 MHz. 트리거 시에만 돌므로 충분 */
static uint16_t crc16_ccitt(const uint8_t *p, uint32_t n)
{
    uint16_t crc = 0xFFFFu;
    while (n--) {
        crc ^= (uint16_t)(*p++) << 8;
        for (int i = 0; i < 8; i++) {
            crc = (crc & 0x8000u) ? (uint16_t)((crc << 1) ^ 0x1021u)
                                  : (uint16_t)(crc << 1);
        }
    }
    return crc;
}

void dump_init(UART_HandleTypeDef *huart)
{
    s_huart = huart;
    s_busy  = false;
    s_seq   = 0;
}

bool dump_busy(void)
{
    return s_busy;
}

bool dump_send_frames(const dump_frame_t *const frames[], uint8_t nframes,
                      uint32_t frame_seq, uint8_t flags)
{
    if (s_busy || s_huart == NULL || nframes == 0u || nframes > DUMP_MAX_FRAMES) {
        return false;
    }

    const uint32_t n       = (uint32_t)nframes * DUMP_N;
    const uint32_t payload = DUMP_CH * n * 2u;
    const uint32_t pkt     = sizeof(dump_hdr_t) + payload + 2u;

    dump_hdr_t *h = (dump_hdr_t *)tx_buf;
    h->sync      = DUMP_SYNC;
    h->ver       = DUMP_VER;
    h->type      = DUMP_TYPE_RAW;
    h->ch        = DUMP_CH;
    h->flags     = flags;
    h->seq       = s_seq++;
    h->frame_seq = frame_seq;
    h->n         = (uint16_t)n;
    h->len       = (uint16_t)payload;

    /* 채널별로 프레임을 시간 순서대로 이어붙임: ch0[f0 f1] ch1[f0 f1] ch2[f0 f1] */
    uint8_t *dst = &tx_buf[sizeof(dump_hdr_t)];
    for (uint32_t c = 0; c < DUMP_CH; c++) {
        for (uint32_t f = 0; f < nframes; f++) {
            memcpy(dst, (*frames[f])[c], FRAME_CH_BYTES);
            dst += FRAME_CH_BYTES;
        }
    }

    uint16_t crc = crc16_ccitt(&tx_buf[4], sizeof(dump_hdr_t) - 4u + payload);
    dst[0] = (uint8_t)(crc & 0xFFu);
    dst[1] = (uint8_t)(crc >> 8);

    s_busy = true;
    if (HAL_UART_Transmit_DMA(s_huart, tx_buf, (uint16_t)pkt) != HAL_OK) {
        s_busy = false;
        return false;
    }
    return true;
}

void dump_on_tx_cplt(UART_HandleTypeDef *huart)
{
    if (huart == s_huart) {
        s_busy = false;
    }
}
