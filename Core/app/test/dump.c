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
#define MAX_PAYLOAD     (DUMP_CH * DUMP_MAX_FRAMES * FRAME_CH_BYTES)    /* 3채널 x 2프레임 x 2048 = 12288 B */
#define MAX_PKT         (sizeof(dump_hdr_t) + MAX_PAYLOAD + 2u)         /* 헤더 20 + payload + CRC 2 = 12310 B */

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
 * 12 KB 기준 약 2 ms @180 MHz. 트리거 시에만 돌므로 충분
 *
 * CRC란: 데이터 전체를 16비트 "지문"으로 요약한 값. 송신측과 수신측이 각자 계산해서
 * 값이 다르면 전송 중 데이터가 깨진 것이다. 비트 단위로 계산하는 가장 단순한 구현. */
static uint16_t crc16_ccitt(const uint8_t *p, uint32_t n)
{
    uint16_t crc = 0xFFFFu;                              /* 초기값 */
    while (n--) {                                        /* 바이트 n개를 하나씩 */
        crc ^= (uint16_t)(*p++) << 8;                    /* 현재 바이트를 crc 상위 8비트에 섞음 */
        for (int i = 0; i < 8; i++) {                    /* 비트 8개를 하나씩 처리 */
            crc = (crc & 0x8000u) ? (uint16_t)((crc << 1) ^ 0x1021u)  /* 최상위 비트가 1이면 shift 후 다항식 XOR */
                                  : (uint16_t)(crc << 1);             /* 0이면 shift만 */
        }
    }
    return crc;
}

/**
 * @brief  덤프 모듈 초기화
 * @param  huart: 송신에 사용할 UART 핸들 (CubeMX가 이미 초기화해 둔 것)
 */
void dump_init(UART_HandleTypeDef *huart)
{
    s_huart = huart;
    s_busy  = false;   /* 아직 아무것도 안 보내는 중 */
    s_seq   = 0;       /* 패킷 번호는 0부터 */
    s_res_pending = false;
}

// 송신 중인지 확인
bool dump_busy(void) { return s_busy; }

// 프레임들을 한 패킷으로 만들어 UART TxDMA 시작
bool dump_send_frames(
    const dump_frame_t *const frames[],  // 시간순 프레임 포인터 배열 (예: { 직전, 현재 })
    uint8_t nframes,            // 프레임 개수 (1 ~ DUMP_MAX_FRAMES)
    uint32_t frame_seq,         // 마지막 프레임의 ADC 프레임 번호 (헤더에 기록)
    uint8_t flags               // DUMP_FLAG_* 조합 (헤더에 기록)
)
{
    /* 보낼 수 없는 상황이면 즉시 포기: 
    송신 버퍼가 사용 중 / UART 미설정 / 프레임 수가 0이거나 너무 많음 */
    if (s_busy || s_huart == NULL || nframes == 0u || nframes > DUMP_MAX_FRAMES) {
        return false;
    }

    const uint32_t n       = (uint32_t)nframes * DUMP_N;      /* 채널당 샘플 수 (2프레임이면 2048) */
    const uint32_t payload = DUMP_CH * n * 2u;                /* 데이터 바이트 수 = 채널 x 샘플 x 2B */
    const uint32_t pkt     = sizeof(dump_hdr_t) + payload + 2u; /* 패킷 전체 길이 = 헤더 + 데이터 + CRC */

    /* 1) 송신 버퍼 맨 앞을 헤더 구조체로 보고 필드를 채움 */
    dump_hdr_t *h = (dump_hdr_t *)tx_buf;
    h->sync      = DUMP_SYNC;
    h->ver       = DUMP_VER;
    h->type      = DUMP_TYPE_RAW;
    h->ch        = DUMP_CH;
    h->flags     = flags;
    h->seq       = s_seq++;          /* 현재 번호를 쓰고 다음을 위해 1 증가 */
    h->frame_seq = frame_seq;
    h->n         = (uint16_t)n;
    h->len       = (uint16_t)payload;

    /* 2) 헤더 뒤에 데이터를 채움.
     *    채널별로 프레임을 시간 순서대로 이어붙임: ch0[f0 f1] ch1[f0 f1] ch2[f0 f1]
     *    (PC가 채널 하나를 연속된 파형으로 바로 읽을 수 있도록 채널이 바깥 루프)
     *    memcpy로 "복사"해 두므로, 반환 후 호출자는 frames를 바로 덮어써도 안전하다. */
    uint8_t *dst = &tx_buf[sizeof(dump_hdr_t)];                  /* 데이터가 들어갈 시작 위치 */
    for (uint32_t c = 0; c < DUMP_CH; c++) {                     /* 채널 */
        for (uint32_t f = 0; f < nframes; f++) {                 /* 시간 순서대로 프레임 */
            memcpy(dst, (*frames[f])[c], FRAME_CH_BYTES);        /* 해당 프레임의 채널 c 샘플 1024개 복사 */
            dst += FRAME_CH_BYTES;                               /* 쓰기 위치 전진 */
        }
    }

    /* 3) CRC 계산. 범위는 ver(4번째 바이트)부터 payload 끝까지 (sync 제외).
     *    루프가 끝난 시점의 dst는 payload 바로 다음 = CRC를 쓸 자리이다. */
    uint16_t crc = crc16_ccitt(&tx_buf[4], sizeof(dump_hdr_t) - 4u + payload);
    dst[0] = (uint8_t)(crc & 0xFFu);   /* little endian: 하위 바이트 먼저 */
    dst[1] = (uint8_t)(crc >> 8);

    /* 4) DMA 송신 시작. busy를 먼저 true로 해 두고, 시작에 실패하면 되돌림.
     *    (시작 직후 DMA 완료 인터럽트가 올 수도 있으므로 순서가 반대면 안 됨) */
    s_busy = true;
    if (HAL_UART_Transmit_DMA(s_huart, tx_buf, (uint16_t)pkt) != HAL_OK) {
        s_busy = false;
        return false;
    }

    // true: 송신 시작됨
    // false: 못 보냄 (송신 중 / 초기화 안 됨 / 프레임 수 이상 / DMA 시작 실패)
    /* 전송은 DMA가 알아서 진행. 완료는 dump_on_tx_cplt()로 알게 됨 */
    return true;   
}

/**
 * @brief  UART DMA 송신 완료 알림 (HAL_UART_TxCpltCallback에서 호출)
 * @param  huart: 송신이 끝난 UART
 */
void dump_on_tx_cplt(UART_HandleTypeDef *huart)
{
    if (huart == s_huart) {   /* 다른 UART의 완료 이벤트는 무시 */
        s_busy = false;       /* 송신 버퍼를 다시 쓸 수 있음 */
    }
}

// 결과 패킷을 대기시킴. seq와 CRC는 실제로 보낼 때(dump_poll) 채운다
void dump_queue_result(const dump_result_t *res, uint32_t frame_seq, uint8_t flags)
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
