#include "stream.h"
#include "dump.h"      /* dump_crc16, dump_busy (검증 모드에서 UART를 같이 씀) */
#include <string.h>

typedef struct __attribute__((packed)) {
	uint32_t sync;
	uint8_t  ver, type, ch, flags;
	uint32_t seq;
	uint32_t frame_seq;
	uint16_t n, len;
	uint8_t  drop, ovr, qdrop, cpu;
} stream_hdr_t;
_Static_assert(sizeof(stream_hdr_t) == 24, "header must be 24 bytes");

#define PAYLOAD  (PREPROC_CH * PREPROC_OUT * 2u)                 /* 1536 B */
#define PKT      (sizeof(stream_hdr_t) + PAYLOAD + 2u)           /* 1562 B */

/* 링버퍼: main이 head에 쓰고, UART 완료 ISR이 tail을 넘긴다 (생산자 1, 소비자 1) */
static uint8_t s_slot[STREAM_SLOTS][PKT] __attribute__((aligned(4)));
static volatile uint32_t s_head, s_tail;    /* 단조 증가 카운터. 칸 = 카운터 % STREAM_SLOTS */
static volatile bool     s_tx;              /* DMA 송신 중 */
static UART_HandleTypeDef *s_huart;
static uint32_t s_seq;
static uint32_t s_qdrop;

void stream_init(UART_HandleTypeDef *huart)
{
	s_huart = huart;
	s_head = s_tail = 0u;
	s_tx = false;
	s_seq = 0u;
	s_qdrop = 0u;
}

uint32_t stream_get_qdrop_cnt(void) { return s_qdrop; }
bool     stream_busy(void)          { return s_tx || (s_head != s_tail); }
uint32_t stream_free(void)          { return STREAM_SLOTS - (s_head - s_tail); }

/* 송신 중이 아니고 보낼 칸이 있으면 시작. main과 ISR 양쪽에서 불리므로 호출자가 인터럽트를 막고 부른다 */
static void kick_locked(void)
{
	if (s_tx || s_head == s_tail || dump_busy())
		return;
	s_tx = true;
	if (HAL_UART_Transmit_DMA(s_huart, s_slot[s_tail % STREAM_SLOTS], (uint16_t)PKT) != HAL_OK)
		s_tx = false;
}

bool stream_push(const int16_t pcm[PREPROC_CH][PREPROC_OUT], uint32_t frame_seq, uint8_t flags,
                 uint32_t drop, uint32_t ovr, uint8_t cpu_pct)
{
	const uint32_t seq = s_seq++;              /* 버려도 번호는 소비 → PC가 빈 번호로 큐 유실을 앎 */
	if (s_head - s_tail >= STREAM_SLOTS) {
		s_qdrop++;
		return false;
	}
	uint8_t *p = s_slot[s_head % STREAM_SLOTS];
	stream_hdr_t *h = (stream_hdr_t *)p;
	h->sync = 0xFFFFFFFFu;
	h->ver = STREAM_VER; h->type = STREAM_TYPE_PCM; h->ch = PREPROC_CH; h->flags = flags;
	h->seq = seq;
	h->frame_seq = frame_seq;
	h->n = PREPROC_OUT; h->len = PAYLOAD;
	h->drop = (uint8_t)drop; h->ovr = (uint8_t)ovr; h->qdrop = (uint8_t)s_qdrop; h->cpu = cpu_pct;
	memcpy(p + sizeof(stream_hdr_t), pcm, PAYLOAD);      /* int16[3][256] → ch0 | ch1 | ch2 */
	const uint16_t crc = dump_crc16(p + 4, sizeof(stream_hdr_t) - 4u + PAYLOAD);
	p[sizeof(stream_hdr_t) + PAYLOAD]      = (uint8_t)(crc & 0xFFu);
	p[sizeof(stream_hdr_t) + PAYLOAD + 1u] = (uint8_t)(crc >> 8);

	__disable_irq();
	s_head++;                                 /* 칸을 다 채운 뒤에 공개 */
	kick_locked();
	__enable_irq();
	return true;
}

void stream_poll(void)
{
	__disable_irq();
	kick_locked();
	__enable_irq();
}

void stream_on_tx_cplt(UART_HandleTypeDef *huart)
{
	if (huart != s_huart || !s_tx)
		return;
	s_tx = false;
	s_tail++;                                 /* 보낸 칸을 비움 */
	kick_locked();                            /* ISR 안이라 다른 인터럽트(같거나 낮은 우선순위)는 끼어들지 않음 */
}
