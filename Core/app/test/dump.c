#include "dump.h"
#include <string.h>

#define DUMP_SYNC       0xFFFFFFFFu     /* 패킷 시작 표시 (바이트로는 FF FF FF FF) */
#define DUMP_VER        2u              /* 패킷 형식 버전. 형식을 바꾸면 올려서 PC가 구분하게 함 */
#define DUMP_TYPE_RAW   0x01u           /* 패킷 종류: 가공 안 한 ADC 원본 */
#define DUMP_TYPE_RESULT 0x02u          /* 패킷 종류: MCU가 계산한 TDOA 결과 */

/* 패킷 맨 앞 20바이트 헤더. 필드 순서/크기가 dump.h의 표와 정확히 같아야 한다.
 * packed : 컴파일러가 정렬용 빈칸(패딩)을 끼워넣지 못하게 해서 전송 바이트 배치와 구조체를 1:1로 맞춤 */
typedef struct __attribute__((packed)) {
    uint32_t sync;        /* FF FF FF FF */
    uint8_t  ver;         /* 형식 버전 */
    uint8_t  type;        /* 패킷 종류 */
    uint8_t  ch;          /* 채널 수 */
    uint8_t  flags;       /* DUMP_FLAG_* */
    uint32_t seq;         /* 송신 패킷 번호 */
    uint32_t frame_seq;   /* 마지막 프레임의 ADC 프레임 번호 */
    uint16_t n;           /* 채널당 샘플 수 */
    uint16_t len;         /* payload 바이트 수 */
} dump_hdr_t;

/* 헤더 크기가 20이 아니면 컴파일 단계에서 에러 (필드를 고치다 PC와 형식이 어긋나는 사고 방지) */
_Static_assert(sizeof(dump_hdr_t) == 20, "header must be 20 bytes");

#define FRAME_CH_BYTES  (DUMP_N * 2u)                                  /* 한 프레임의 한 채널 = 1024샘플 x 2B = 2048 B */
#define MAX_PAYLOAD     (DUMP_CH * DUMP_MAX_FRAMES * FRAME_CH_BYTES)    /* 3채널 x 8프레임 x 2048 = 49152 B */
#define MAX_PKT         (sizeof(dump_hdr_t) + MAX_PAYLOAD + 2u)         /* 헤더 20 + payload + CRC 2 = 49174 B */

_Static_assert(MAX_PKT <= 0xFFFFu, "HAL_UART_Transmit_DMA length is 16-bit");

/* DMA가 읽는 동안 건드리면 안 되므로 static 버퍼 사용
 * (함수 지역변수는 함수가 끝나면 사라지는데, DMA 송신은 함수가 끝난 뒤에도 계속 이 메모리를 읽는다) */
static uint8_t tx_buf[MAX_PKT] __attribute__((aligned(4)));

/* 결과 패킷은 RAW 송신 중에도 만들어 둘 수 있어야 하므로 버퍼를 따로 둔다 (헤더 20 + 40 + CRC 2 = 62 B) */
#define RES_PKT         (sizeof(dump_hdr_t) + sizeof(dump_result_t) + 2u)
static uint8_t res_buf[RES_PKT] __attribute__((aligned(4)));
static bool    s_res_pending;         /* 보낼 결과 패킷이 대기 중인지 (main 루프에서만 접근) */

static UART_HandleTypeDef *s_huart;   /* 송신에 쓸 UART */
static volatile bool       s_busy;    /* DMA 송신 진행 중 여부. 인터럽트에서도 바뀌므로 volatile */
static uint32_t            s_seq;     /* 다음에 보낼 패킷 번호 */

/* CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF)
 * Python: bin_ascii.crc_hqx(data, 0xFFFF) 와 같은 값
 *
 * CRC란: 데이터 전체를 16비트 "지문"으로 요약한 값. 송신측과 수신측이 각자 계산해서
 * 값이 다르면 전송 중 데이터가 깨진 것이다.
 * 표 방식 (2026-11-02): 바이트 하나가 CRC에 주는 영향 256가지를 미리 계산해 둔 표(crc_table, flash 512 B)를 찾아 쓴다.
 * 비트 8개를 하나씩 처리하던 방식(바이트당 약 40사이클)과 결과가 같고, 바이트당 약 6사이클 (추정).
 * STREAM 패킷 2074 B가 프레임마다 지나가서 그 차이가 CPU 약 2 %p다.
 * 표 만드는 법: 바이트 b에 대해 c = b << 8 을 비트 방식으로 8번 돌린 값 = crc_table[b] */
static const uint16_t crc_table[256] = {
    0x0000u, 0x1021u, 0x2042u, 0x3063u, 0x4084u, 0x50A5u, 0x60C6u, 0x70E7u,
    0x8108u, 0x9129u, 0xA14Au, 0xB16Bu, 0xC18Cu, 0xD1ADu, 0xE1CEu, 0xF1EFu,
    0x1231u, 0x0210u, 0x3273u, 0x2252u, 0x52B5u, 0x4294u, 0x72F7u, 0x62D6u,
    0x9339u, 0x8318u, 0xB37Bu, 0xA35Au, 0xD3BDu, 0xC39Cu, 0xF3FFu, 0xE3DEu,
    0x2462u, 0x3443u, 0x0420u, 0x1401u, 0x64E6u, 0x74C7u, 0x44A4u, 0x5485u,
    0xA56Au, 0xB54Bu, 0x8528u, 0x9509u, 0xE5EEu, 0xF5CFu, 0xC5ACu, 0xD58Du,
    0x3653u, 0x2672u, 0x1611u, 0x0630u, 0x76D7u, 0x66F6u, 0x5695u, 0x46B4u,
    0xB75Bu, 0xA77Au, 0x9719u, 0x8738u, 0xF7DFu, 0xE7FEu, 0xD79Du, 0xC7BCu,
    0x48C4u, 0x58E5u, 0x6886u, 0x78A7u, 0x0840u, 0x1861u, 0x2802u, 0x3823u,
    0xC9CCu, 0xD9EDu, 0xE98Eu, 0xF9AFu, 0x8948u, 0x9969u, 0xA90Au, 0xB92Bu,
    0x5AF5u, 0x4AD4u, 0x7AB7u, 0x6A96u, 0x1A71u, 0x0A50u, 0x3A33u, 0x2A12u,
    0xDBFDu, 0xCBDCu, 0xFBBFu, 0xEB9Eu, 0x9B79u, 0x8B58u, 0xBB3Bu, 0xAB1Au,
    0x6CA6u, 0x7C87u, 0x4CE4u, 0x5CC5u, 0x2C22u, 0x3C03u, 0x0C60u, 0x1C41u,
    0xEDAEu, 0xFD8Fu, 0xCDECu, 0xDDCDu, 0xAD2Au, 0xBD0Bu, 0x8D68u, 0x9D49u,
    0x7E97u, 0x6EB6u, 0x5ED5u, 0x4EF4u, 0x3E13u, 0x2E32u, 0x1E51u, 0x0E70u,
    0xFF9Fu, 0xEFBEu, 0xDFDDu, 0xCFFCu, 0xBF1Bu, 0xAF3Au, 0x9F59u, 0x8F78u,
    0x9188u, 0x81A9u, 0xB1CAu, 0xA1EBu, 0xD10Cu, 0xC12Du, 0xF14Eu, 0xE16Fu,
    0x1080u, 0x00A1u, 0x30C2u, 0x20E3u, 0x5004u, 0x4025u, 0x7046u, 0x6067u,
    0x83B9u, 0x9398u, 0xA3FBu, 0xB3DAu, 0xC33Du, 0xD31Cu, 0xE37Fu, 0xF35Eu,
    0x02B1u, 0x1290u, 0x22F3u, 0x32D2u, 0x4235u, 0x5214u, 0x6277u, 0x7256u,
    0xB5EAu, 0xA5CBu, 0x95A8u, 0x8589u, 0xF56Eu, 0xE54Fu, 0xD52Cu, 0xC50Du,
    0x34E2u, 0x24C3u, 0x14A0u, 0x0481u, 0x7466u, 0x6447u, 0x5424u, 0x4405u,
    0xA7DBu, 0xB7FAu, 0x8799u, 0x97B8u, 0xE75Fu, 0xF77Eu, 0xC71Du, 0xD73Cu,
    0x26D3u, 0x36F2u, 0x0691u, 0x16B0u, 0x6657u, 0x7676u, 0x4615u, 0x5634u,
    0xD94Cu, 0xC96Du, 0xF90Eu, 0xE92Fu, 0x99C8u, 0x89E9u, 0xB98Au, 0xA9ABu,
    0x5844u, 0x4865u, 0x7806u, 0x6827u, 0x18C0u, 0x08E1u, 0x3882u, 0x28A3u,
    0xCB7Du, 0xDB5Cu, 0xEB3Fu, 0xFB1Eu, 0x8BF9u, 0x9BD8u, 0xABBBu, 0xBB9Au,
    0x4A75u, 0x5A54u, 0x6A37u, 0x7A16u, 0x0AF1u, 0x1AD0u, 0x2AB3u, 0x3A92u,
    0xFD2Eu, 0xED0Fu, 0xDD6Cu, 0xCD4Du, 0xBDAAu, 0xAD8Bu, 0x9DE8u, 0x8DC9u,
    0x7C26u, 0x6C07u, 0x5C64u, 0x4C45u, 0x3CA2u, 0x2C83u, 0x1CE0u, 0x0CC1u,
    0xEF1Fu, 0xFF3Eu, 0xCF5Du, 0xDF7Cu, 0xAF9Bu, 0xBFBAu, 0x8FD9u, 0x9FF8u,
    0x6E17u, 0x7E36u, 0x4E55u, 0x5E74u, 0x2E93u, 0x3EB2u, 0x0ED1u, 0x1EF0u
};
static uint16_t crc16_ccitt(
	const uint8_t *p,	// 계산할 바이트열 시작 (패킷의 ver 칸, sync 다음)
	uint32_t n			// 바이트 수 (헤더 − sync 4 B + payload)
)
{
    uint16_t crc = 0xFFFFu;                              /* 초기값 */
    while (n--)                                          /* 바이트 n개를 하나씩: 상위 8비트와 새 바이트로 표를 찾고, 나머지는 8비트 밀어 섞음 */
        crc = (uint16_t)((crc << 8) ^ crc_table[((crc >> 8) ^ *p++) & 0xFFu]);
    return crc;
}

uint16_t dump_crc16(const uint8_t *p, uint32_t n) { return crc16_ccitt(p, n); }

/* 덤프 모듈 초기화 */
void dump_init(
	UART_HandleTypeDef *huart	// 송신에 사용할 UART 핸들 (CubeMX가 이미 초기화해 둔 것)
)
{
    s_huart = huart;
    s_busy  = false;   /* 아직 아무것도 안 보내는 중 */
    s_seq   = 0;       /* 패킷 번호는 0부터 */
    s_res_pending = false;
}

// 송신 중인지 확인
bool dump_busy(void) { return s_busy; }

uint16_t *dump_payload(void) { return (uint16_t *)&tx_buf[sizeof(dump_hdr_t)]; }

// 이미 채워진 payload(채널당 n샘플)에 헤더와 CRC를 붙여 UART TxDMA 시작
bool dump_send_payload(
	uint16_t n,			// 채널당 샘플 수 (dump_payload()에 이미 채워 둔 양)
	uint32_t frame_seq,	// 헤더에 기록할 ADC 프레임 번호
	uint8_t flags		// DUMP_FLAG_* 조합 (헤더에 기록)
)
{
    const uint32_t payload = DUMP_CH * (uint32_t)n * 2u;               /* 데이터 바이트 수 = 채널 x 샘플 x 2B */
    const uint32_t pkt     = sizeof(dump_hdr_t) + payload + 2u;        /* 패킷 전체 길이 = 헤더 + 데이터 + CRC */
    if (s_busy || s_huart == NULL || n == 0u || payload > MAX_PAYLOAD) {
        return false;
    }

    /* 1) 송신 버퍼 맨 앞을 헤더 구조체로 보고 필드를 채움 */
    dump_hdr_t *h = (dump_hdr_t *)tx_buf;
    h->sync      = DUMP_SYNC;
    h->ver       = DUMP_VER;
    h->type      = DUMP_TYPE_RAW;
    h->ch        = DUMP_CH;
    h->flags     = flags;
    h->seq       = s_seq++;          /* 현재 번호를 쓰고 다음을 위해 1 증가 */
    h->frame_seq = frame_seq;
    h->n         = n;
    h->len       = (uint16_t)payload;

    /* 2) CRC 계산. 범위는 ver(4번째 바이트)부터 payload 끝까지 (sync 제외). 48 KB면 약 8 ms */
    uint8_t *crc_at = &tx_buf[sizeof(dump_hdr_t) + payload];
    uint16_t crc = crc16_ccitt(&tx_buf[4], sizeof(dump_hdr_t) - 4u + payload);
    crc_at[0] = (uint8_t)(crc & 0xFFu);   /* little endian: 하위 바이트 먼저 */
    crc_at[1] = (uint8_t)(crc >> 8);

    /* 3) DMA 송신 시작. busy를 먼저 true로 해 두고, 시작에 실패하면 되돌림.
     *    (시작 직후 DMA 완료 인터럽트가 올 수도 있으므로 순서가 반대면 안 됨) */
    s_busy = true;
    if (HAL_UART_Transmit_DMA(s_huart, tx_buf, (uint16_t)pkt) != HAL_OK) {
        s_busy = false;
        return false;
    }
    return true;   /* 전송은 DMA가 알아서 진행. 완료는 dump_on_tx_cplt()로 알게 됨 */
}

// 프레임들을 한 패킷으로 만들어 UART TxDMA 시작
bool dump_send_frames(
    const dump_frame_t *const frames[],  // 시간순 프레임 포인터 배열 (예: { 직전, 현재 })
    uint8_t nframes,            // 프레임 개수 (1 ~ DUMP_MAX_FRAMES)
    uint32_t frame_seq,         // 마지막 프레임의 ADC 프레임 번호 (헤더에 기록)
    uint8_t flags               // DUMP_FLAG_* 조합 (헤더에 기록)
)
{
    if (s_busy || s_huart == NULL || nframes == 0u || nframes > DUMP_MAX_FRAMES) {
        return false;
    }
    const uint32_t n = (uint32_t)nframes * DUMP_N;      /* 채널당 샘플 수 (2프레임이면 2048) */

    /* 채널별로 프레임을 시간 순서대로 이어붙임: ch0[f0 f1] ch1[f0 f1] ch2[f0 f1]
     * (PC가 채널 하나를 연속된 파형으로 바로 읽을 수 있도록 채널이 바깥 루프)
     * memcpy로 "복사"해 두므로, 반환 후 호출자는 frames를 바로 덮어써도 안전하다. */
    uint8_t *dst = (uint8_t *)dump_payload();
    for (uint32_t c = 0; c < DUMP_CH; c++) {
        for (uint32_t f = 0; f < nframes; f++) {
            memcpy(dst, (*frames[f])[c], FRAME_CH_BYTES);
            dst += FRAME_CH_BYTES;
        }
    }
    return dump_send_payload((uint16_t)n, frame_seq, flags);
}

/* UART DMA 송신 완료 알림 (HAL_UART_TxCpltCallback에서 호출) */
void dump_on_tx_cplt(
	UART_HandleTypeDef *huart	// 송신이 끝난 UART
)
{
    if (huart == s_huart) {   /* 다른 UART의 완료 이벤트는 무시 */
        s_busy = false;       /* 송신 버퍼를 다시 쓸 수 있음 */
    }
}

// 결과 패킷을 대기시킴. seq와 CRC는 실제로 보낼 때(dump_poll) 채운다
void dump_queue_result(
	const dump_result_t *res,	// 보낼 TDOA 결과 (app.c on_capture가 채움)
	uint32_t frame_seq,			// 결과를 낸 ADC 프레임 번호 (같은 번호의 원파형 패킷과 짝)
	uint8_t flags				// DUMP_FLAG_* 조합 (VALID 등)
)
{
    dump_hdr_t *h = (dump_hdr_t *)res_buf;
    h->sync      = DUMP_SYNC;
    h->ver       = DUMP_VER;
    h->type      = DUMP_TYPE_RESULT;
    h->ch        = 0u;                /* 샘플 데이터가 아니므로 ch, n은 0 */
    h->flags     = flags;
    h->frame_seq = frame_seq;         /* 짝이 되는 RAW 패킷과 같은 번호 */
    h->n         = 0u;
    h->len       = (uint16_t)sizeof(dump_result_t);
    memcpy(&res_buf[sizeof(dump_hdr_t)], res, sizeof(dump_result_t));
    s_res_pending = true;
}

// 대기 중인 결과 패킷이 있고 송신 중이 아니면 보냄 (main 루프에서 계속 호출)
void dump_poll(void)
{
    if (!s_res_pending || s_busy || s_huart == NULL) {
        return;
    }

    dump_hdr_t *h = (dump_hdr_t *)res_buf;
    h->seq = s_seq++;                 /* 보내는 순서대로 번호를 매기기 위해 여기서 채움 */

    const uint32_t body = sizeof(dump_hdr_t) + sizeof(dump_result_t);
    uint16_t crc = crc16_ccitt(&res_buf[4], body - 4u);
    res_buf[body]      = (uint8_t)(crc & 0xFFu);
    res_buf[body + 1u] = (uint8_t)(crc >> 8);

    s_res_pending = false;
    s_busy = true;
    if (HAL_UART_Transmit_DMA(s_huart, res_buf, (uint16_t)RES_PKT) != HAL_OK) {
        s_busy = false;
    }
}
