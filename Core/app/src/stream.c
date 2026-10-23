/*
 * stream.c : 전처리된 PCM 블록과 DOA 결과를 패킷으로 만들어 UART DMA로 PC에 보낸다 (패킷 형식은 stream.h)
 *
 *  큐가 두 개다.
 *    PCM 큐 (s_slot, STREAM_SLOTS칸)    : 프레임(20.48 ms)마다 1562 B 하나. 921600 baud에서 약 16.9 ms 걸림
 *    DOA 큐 (s_doa, STREAM_DOA_SLOTS칸) : 관측 창이 끝날 때마다 78 B 하나 (초당 4개). 약 0.85 ms
 *  UART는 하나뿐이므로 한 번에 패킷 하나만 DMA로 나간다. 다음에 무엇을 보낼지는 kick_locked()가 정하고,
 *  DOA 큐가 비어 있지 않으면 DOA를 먼저 보낸다 (작고, 결과가 늦게 도착하면 쓸모가 줄어서).
 *
 *  누가 무엇을 바꾸나
 *    main 루프 (생산자) : stream_push / stream_push_doa가 head 쪽 칸을 채우고 head를 올린다
 *    UART 완료 ISR (소비자) : stream_on_tx_cplt가 tail을 올려 보낸 칸을 비우고, 다음 송신을 시작한다
 *  head는 main만, tail은 ISR만 쓰므로 생산자 1 · 소비자 1 링버퍼가 된다.
 *  kick_locked()만 양쪽에서 불리므로 인터럽트를 막은 상태에서 부른다.
 */
#include "stream.h"
#include "dump.h"      /* dump_crc16, dump_busy (검증 모드에서 UART를 같이 씀) */
#include <string.h>

/* 패킷 헤더 24 B. PCM 패킷과 DOA 패킷이 같은 헤더를 쓴다 (필드 의미는 stream.h 표).
 * packed: 컴파일러가 필드 사이에 빈 바이트를 넣지 못하게 해서, 메모리 배치가 곧 전송 바이트 배치가 되게 한다.
 * 이 구조체 포인터를 송신 버퍼 위에 씌워(cast) 필드를 채운다. */
typedef struct __attribute__((packed)) {
	uint32_t sync;                 /* 항상 FF FF FF FF. PC가 패킷 시작 후보를 찾는 표시 */
	uint8_t  ver, type, ch, flags; /* ver = STREAM_VER, type = STREAM_TYPE_PCM 또는 _DOA, ch = 채널 수, flags = STREAM_FLAG_* */
	uint32_t seq;                  /* 송신 패킷 번호. PCM과 DOA가 따로 센다 (s_seq, s_dseq) */
	uint32_t frame_seq;            /* 이 패킷이 나온 ADC 프레임 번호 (adc.c가 매긴 번호 그대로) */
	uint16_t n, len;               /* n = 채널당 샘플 수 (PCM 256, DOA 1), len = payload 바이트 수 */
	uint8_t  drop, ovr, qdrop, cpu;/* 유실 누계 3종 (하위 8비트만) + CPU 사용률 [%] */
} stream_hdr_t;

_Static_assert(sizeof(stream_hdr_t) == 24, "header must be 24 bytes");

/* PCM 패킷 크기. payload = 3채널 × 256샘플 × int16(2 B), 끝의 2u = CRC16 */
#define PAYLOAD  (PREPROC_CH * PREPROC_OUT * 2u)                 /* 1536 B */
#define PKT      (sizeof(stream_hdr_t) + PAYLOAD + 2u)           /* 1562 B */

/* DOA 결과 payload 52 B. doa_result_t(doa.h)를 전송용으로 줄인 것 (proc_us를 uint16으로, reserved 추가).
 * 배치는 PC의 Tools/board/dump_viewer.py DOA_FMT와 1바이트도 어긋나면 안 된다. */
typedef struct __attribute__((packed)) {
	uint32_t s0;                   /* 관측 창 첫 샘플 번호 (12.5 kHz PCM 시간축) */
	float    tau[3], peak[3], angle, norm, snr_db;   /* 쌍별 지연 [샘플], 쌍별 상관 피크, 방위각 [deg], 방향 벡터 길이, SNR [dB] */
	uint8_t  flags, reserved;      /* flags = DOA_FLAG_*, reserved = 항상 0 (정렬용 빈칸) */
	uint16_t proc_us;              /* 창 마무리 계산 시간 [us], 65535에서 포화 */
	uint32_t bg_s0, bg_n;          /* 사용한 배경 구간의 첫 샘플 번호와 길이 (bg_n = 0 → 배경 없음) */
} doa_payload_t;

_Static_assert(sizeof(doa_payload_t) == 52, "DOA payload must be 52 bytes");
#define DOA_PKT  (sizeof(stream_hdr_t) + sizeof(doa_payload_t) + 2u)   /* 78 B */

/* 링버퍼: main이 head에 쓰고, UART 완료 ISR이 tail을 넘긴다 (생산자 1, 소비자 1)
 * s_slot[칸][바이트] : PCM 패킷 STREAM_SLOTS개를 완성된 모양(헤더 + payload + CRC) 그대로 담아 두는 송신 버퍼.
 *                     DMA가 이 메모리를 직접 읽어 UART로 내보내므로, 송신이 끝날 때까지 그 칸은 고치면 안 된다.
 * aligned(4)는 배열 시작만 4바이트에 맞춘다. PKT(1562)가 4의 배수가 아니라 1·3번 칸의 시작은 2바이트 어긋나지만,
 * 헤더가 packed 구조체라 컴파일러가 정렬을 가정하지 않고, Cortex-M4는 일반 LDR/STR의 비정렬 접근도 허용한다. */
static uint8_t s_slot[STREAM_SLOTS][PKT] __attribute__((aligned(4)));

/* s_head : 지금까지 채운 PCM 패킷 수. 다음에 채울 칸 = s_head % STREAM_SLOTS (main만 증가)
 * s_tail : 지금까지 다 보낸 PCM 패킷 수. 다음에 보낼 칸 = s_tail % STREAM_SLOTS (ISR만 증가)
 * s_head - s_tail = 큐에 쌓인 패킷 수 (0 ~ STREAM_SLOTS). 부호 없는 뺄셈이라 2^32에서 넘쳐 0으로 돌아가도 차이는 맞고,
 * STREAM_SLOTS(4)가 2^32의 약수라 % 결과도 넘침 앞뒤로 이어진다.
 * volatile: 한쪽이 ISR에서 바뀌므로 컴파일러가 레지스터에 캐시해 두지 말고 매번 메모리에서 읽게 한다. */
static volatile uint32_t s_head, s_tail;    /* 단조 증가 카운터. 칸 = 카운터 % STREAM_SLOTS */
static volatile bool     s_tx;              /* DMA 송신 중 (PCM이든 DOA든). true인 동안 새 송신을 시작하지 않는다 */
static UART_HandleTypeDef *s_huart;         /* 송신에 쓰는 UART (main.c의 huart2). 완료 콜백이 우리 UART인지 비교할 때도 씀 */
static uint32_t s_seq;                      /* 다음 PCM 패킷에 붙일 송신 번호. 큐가 가득 차 버린 패킷도 번호를 하나 소비한다 */
static uint32_t s_qdrop;                    /* PCM 큐가 가득 차 버린 패킷 누계. 헤더 qdrop(하위 8비트)과 app.c의 GAP 판정에 쓰임 */

/* DOA 결과 큐. 구조와 규칙은 PCM 큐와 같고, 칸 크기만 DOA_PKT(78 B)다.
 * s_dhead / s_dtail : DOA 패킷의 채운 수 / 보낸 수 (s_head / s_tail과 같은 방식)
 * s_dseq           : 다음 DOA 패킷의 송신 번호. PCM의 s_seq와 별개로 센다 */
static uint8_t s_doa[STREAM_DOA_SLOTS][DOA_PKT] __attribute__((aligned(4)));
static volatile uint32_t s_dhead, s_dtail;
static volatile bool     s_tx_doa;          /* 지금 나가는 것이 DOA 패킷. 완료 콜백이 어느 큐의 tail을 올릴지 이것으로 정한다 */
static uint32_t s_dseq;

/* 부팅 시 한 번. 송신할 UART를 기억하고 두 큐와 번호를 모두 비운다 */
void stream_init(
	UART_HandleTypeDef *huart	// 송신에 쓸 UART (main.c의 huart2, app_init이 넘겨줌)
)
{
	s_huart = huart;
	s_head = s_tail = 0u;
	s_tx = false;
	s_seq = 0u;
	s_qdrop = 0u;
	s_dhead = s_dtail = 0u;
	s_tx_doa = false;
	s_dseq = 0u;
}

uint32_t stream_get_qdrop_cnt(void) { return s_qdrop; }
/* 송신 중이거나, 두 큐 중 하나라도 보낼 것이 남아 있으면 true (verify.c가 UART가 완전히 빌 때를 기다릴 때 씀) */
bool     stream_busy(void)          { return s_tx || (s_head != s_tail) || (s_dhead != s_dtail); }
/* PCM 큐의 빈 칸 수 (DOA 큐는 세지 않는다) */
uint32_t stream_free(void)          { return STREAM_SLOTS - (s_head - s_tail); }

/* 송신 중이 아니고 보낼 칸이 있으면 시작. main과 ISR 양쪽에서 불리므로 호출자가 인터럽트를 막고 부른다
 *  - dump_busy(): dump.c(원파형·결과 패킷)도 같은 UART를 쓴다. dump가 보내는 중이면 기다렸다가
 *    main 루프의 stream_poll()이 다시 부를 때 시작한다.
 *  - HAL_UART_Transmit_DMA가 실패하면(HAL_BUSY 등) 송신 중 표시를 되돌린다. 칸은 큐에 그대로 있으므로 다음 호출에서 다시 시도한다. */

// 인터럽트를 막은 상태 (lock)에서 UART_TxDMA 전송
static void kick_locked(void)
{
	if (s_tx || dump_busy())
		return;
	if (s_dhead != s_dtail) {                 /* 작은 결과 패킷을 먼저 (78 B ≈ 0.85 ms) */
		s_tx = s_tx_doa = true;
		if (HAL_UART_Transmit_DMA(s_huart, s_doa[s_dtail % STREAM_DOA_SLOTS], (uint16_t)DOA_PKT) != HAL_OK)
			s_tx = s_tx_doa = false;
		return;
	}
	if (s_head == s_tail)                     /* PCM 큐도 비었음: 보낼 것이 없다 */
		return;
	s_tx = true;
	s_tx_doa = false;
	if (HAL_UART_Transmit_DMA(s_huart, s_slot[s_tail % STREAM_SLOTS], (uint16_t)PKT) != HAL_OK)
		s_tx = false;
}


// [STREAM HEADER] + [PAYLOAD] + [CRC] 로 패킷을 구성해서 UART_TxDMA 전송
bool stream_push(
	const int16_t pcm[PREPROC_CH][PREPROC_OUT],	// PCM 블럭 int16[3][256] (12.5 kHz, 프레임 하나). payload로 복사된다
	uint32_t frame_seq,	// 이 블록을 만든 ADC 프레임 번호 → 헤더 frame_seq. PC는 (frame_seq − 1) × 256으로 시각을 안다
	uint8_t flags,		// STREAM_FLAG_* (CLIP / RESYNC / VERIFY / GAP). app.c·verify.c가 정해서 넘긴다 → 헤더 flags
	uint32_t drop,		// adc.c의 프레임 유실 누계 → 헤더 drop (하위 8비트만. PC는 값이 바뀌었는지만 본다)
	uint32_t ovr,		// adc.c의 overrun 누계 → 헤더 ovr (하위 8비트만)
	uint8_t cpu_pct		// 직전 프레임의 처리 시간 / 20.48 ms [%] (app.c가 계산) → 헤더 cpu
)
{
	const uint32_t seq = s_seq++;              /* 버려도 번호는 소비 → PC가 빈 번호로 큐 유실을 앎 */
	if (s_head - s_tail >= STREAM_SLOTS) {    /* 4칸이 모두 송신 대기 중: UART가 생산 속도를 못 따라감 */
		s_qdrop++;
		return false;
	}
	/* 비어 있는 다음 칸. ISR은 tail 쪽 칸만 읽으므로, 아직 공개하지 않은(head를 올리기 전) 이 칸은
	 * 인터럽트를 막지 않고 채워도 안전하다 */
	uint8_t *p = s_slot[s_head % STREAM_SLOTS];
	stream_hdr_t *h = (stream_hdr_t *)p;      /* 칸의 앞 24 B를 헤더 구조체로 본다 */
	h->sync = 0xFFFFFFFFu;
	h->ver = STREAM_VER; h->type = STREAM_TYPE_PCM; h->ch = PREPROC_CH; h->flags = flags;
	h->seq = seq;
	h->frame_seq = frame_seq;
	h->n = PREPROC_OUT; h->len = PAYLOAD;
	h->drop = (uint8_t)drop; h->ovr = (uint8_t)ovr; h->qdrop = (uint8_t)s_qdrop; h->cpu = cpu_pct;

	memcpy(p + sizeof(stream_hdr_t), pcm, PAYLOAD);      // 헤더에 PAYLOAD 붙임

	const uint16_t crc = dump_crc16(p + 4, sizeof(stream_hdr_t) - 4u + PAYLOAD);	// PAYLOAD 뒤에 CRC 붙임
	/* CRC는 little endian (하위 바이트 먼저) */
	p[sizeof(stream_hdr_t) + PAYLOAD]      = (uint8_t)(crc & 0xFFu);
	p[sizeof(stream_hdr_t) + PAYLOAD + 1u] = (uint8_t)(crc >> 8);

	/* head를 올리는 것과 송신 시작 판단을 ISR과 겹치지 않게 묶는다 */
	__disable_irq();
	s_head++;
	kick_locked();
	__enable_irq();
	return true;
}

/* DOA 결과 하나를 패킷으로 만들어 DOA 큐에 넣는다 (main에서만 호출)
 *  반환: 큐가 가득 차면 false. PCM과 달리 유실 카운터와 번호 소비는 없다 (초당 4개라 4칸이 찰 일이 거의 없음) */
bool stream_push_doa(
	const doa_result_t *r,	// doa_push()가 돌려준 결과 → 전송용 doa_payload_t로 옮겨 담는다
	uint32_t frame_seq		// 관측 창이 끝난 ADC 프레임 번호 → 헤더 frame_seq (창 시작은 payload의 s0)
)
{
	if (s_dhead - s_dtail >= STREAM_DOA_SLOTS)
		return false;
	uint8_t *p = s_doa[s_dhead % STREAM_DOA_SLOTS];
	stream_hdr_t *h = (stream_hdr_t *)p;
	h->sync = 0xFFFFFFFFu;
	h->ver = STREAM_VER; h->type = STREAM_TYPE_DOA; h->ch = DOA_CH; h->flags = 0u;
	h->seq = s_dseq++;
	h->frame_seq = frame_seq;
	h->n = 1u; h->len = (uint16_t)sizeof(doa_payload_t);
	h->drop = 0u; h->ovr = 0u; h->qdrop = (uint8_t)s_qdrop; h->cpu = 0u;   /* DOA 패킷에서 유실·CPU 칸은 쓰지 않음 (qdrop만 참고용) */
	/* d : 전송 형식으로 옮겨 담은 결과. 지역 변수로 다 채운 뒤 송신 칸에 한 번에 복사한다 */
	doa_payload_t d = {
		.s0 = r->s0,
		.tau = { r->tau[0], r->tau[1], r->tau[2] },
		.peak = { r->peak[0], r->peak[1], r->peak[2] },
		.angle = r->angle_deg, .norm = r->norm, .snr_db = r->snr_db,
		.flags = r->flags, .reserved = 0u,
		.proc_us = (uint16_t)(r->proc_us > 0xFFFFu ? 0xFFFFu : r->proc_us),   /* uint32 → uint16, 넘치면 65535로 포화 */
		.bg_s0 = r->bg_s0, .bg_n = r->bg_n,
	};
	memcpy(p + sizeof(stream_hdr_t), &d, sizeof(d));
	const uint16_t crc = dump_crc16(p + 4, sizeof(stream_hdr_t) - 4u + sizeof(d));
	p[sizeof(stream_hdr_t) + sizeof(d)]      = (uint8_t)(crc & 0xFFu);
	p[sizeof(stream_hdr_t) + sizeof(d) + 1u] = (uint8_t)(crc >> 8);

	__disable_irq();
	s_dhead++;                                /* 칸을 다 채운 뒤에 공개 */
	kick_locked();
	__enable_irq();
	return true;
}

/* main 루프에서 계속 호출. 송신이 멈춰 있는데 큐에 남은 것이 있을 때(dump 송신이 막 끝났거나 DMA 시작이 실패했을 때) 다시 시작한다 */
void stream_poll(void)
{
	__disable_irq();
	kick_locked();
	__enable_irq();
}

/* UART 송신 완료 ISR(HAL_UART_TxCpltCallback, app.c)에서 호출
 *  - 다른 UART이거나 우리가 시작한 송신이 아니면(!s_tx → dump가 보낸 것) 무시한다.
 *  - 방금 끝난 것이 DOA인지 PCM인지(s_tx_doa) 보고 그 큐의 tail을 올린 뒤, 곧바로 다음 패킷을 시작한다. */
void stream_on_tx_cplt(
	UART_HandleTypeDef *huart	// 송신이 끝난 UART. HAL이 넘겨준다 (우리 UART인지 s_huart와 비교)
)
{
	if (huart != s_huart || !s_tx)
		return;
	s_tx = false;
	if (s_tx_doa) {
		s_tx_doa = false;
		s_dtail++;                            /* 보낸 DOA 칸을 비움 */
	} else {
		s_tail++;                             /* 보낸 칸을 비움 */
	}
	kick_locked();                            /* ISR 안이라 다른 인터럽트(같거나 낮은 우선순위)는 끼어들지 않음 */
}
