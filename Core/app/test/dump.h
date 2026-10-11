#ifndef DUMP_H
#define DUMP_H

/*
 * dump : ADC 프레임(원파형)을 UART로 PC에 보내는 "송신 담당" 모듈
 *
 *  - 하는 일 : 프레임 데이터에 헤더와 CRC를 붙여 하나의 "패킷"으로 만들고,
 *              DMA로 UART 송신을 시작한다. (CPU는 송신이 끝나길 기다리지 않는다)
 *  - 모르는 것: "언제" 보낼지는 모른다. 그 판단은 capture 모듈이 하고, dump는 시키면 보내기만 한다.
 *  - 수신측  : Tools/dump_viewer.py 가 이 패킷 형식을 해석한다. (형식을 바꾸면 양쪽을 같이 고쳐야 함)
 */

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
 *
 * 필드 설명
 *  sync : 패킷의 시작 표시. ADC 값은 12비트(최대 0x0FFF)라 payload 안에 FF가 4번 연속 나올 수 없으므로,
 *         PC는 FF FF FF FF 를 만나면 "여기가 패킷 시작"이라고 확신할 수 있다.
 *  seq  : 보낼 때마다 1씩 증가. PC가 번호가 건너뛴 것을 보고 패킷 유실을 알아챈다.
 *  crc16: 전송 중 비트가 깨졌는지 PC가 검사하는 값. 하나라도 틀리면 그 패킷은 버린다.
 *
 * 결과 패킷 (type = 0x02)
 *  같은 20바이트 헤더를 쓰되 ch = 0, n = 0, len = 40. payload는 dump_result_t.
 *  MCU가 계산한 TDOA 결과이며, 같은 frame_seq의 RAW 패킷과 짝이다. (RAW 송신이 끝난 뒤에 나간다)
 *  seq는 종류와 관계없이 보내는 순서대로 1씩 증가한다.
 */

#define DUMP_N            1024u     /* 프레임당 채널별 샘플 수 (50 kHz 기준 20.48 ms) */
#define DUMP_CH           3u        /* 마이크(ADC 채널) 수 */
#define DUMP_MAX_FRAMES   2u        /* 한 패킷에 담을 최대 프레임 수: 직전 프레임 + 트리거 프레임 */

#define DUMP_FLAG_CLIP    0x01u     /* 클리핑 샘플 있음 (ADC가 0 또는 4095 근처에 붙음 = 신호가 너무 큼) */
#define DUMP_FLAG_MANUAL  0x02u     /* 수동 트리거 (버튼 등) */
#define DUMP_FLAG_PRETRIG 0x04u     /* payload 앞 절반 = 트리거 직전 프레임 */
#define DUMP_FLAG_VALID   0x08u     /* (결과 패킷) MCU가 이 결과를 신뢰 가능으로 판정함 */

/* typedef old new; */
typedef uint16_t dump_frame_t[DUMP_CH][DUMP_N];

/* 모듈 초기화. 사용할 UART 핸들을 저장하고 송신 상태/패킷 번호를 0으로 만든다. */
void dump_init(UART_HandleTypeDef *huart);

/* 이전 송신이 아직 진행 중이면 true. 송신 버퍼가 하나뿐이라, true인 동안은 새로 보낼 수 없다. */
bool dump_busy(void);

/* frames[0..nframes-1]을 시간 순서대로 이어붙여 한 패킷으로 송신.
 * 송신 버퍼로 복사한 뒤 DMA를 시작하므로, 반환 후 frames는 바로 재사용해도 된다.
 * 이전 송신이 끝나지 않았거나 nframes가 범위를 벗어나면 false. */
bool dump_send_frames(const dump_frame_t *const frames[], uint8_t nframes,
                      uint32_t frame_seq, uint8_t flags);

/* 프레임 하나만 보낼 때 (위 함수에 프레임 1개짜리 배열을 만들어 넘기는 단축 함수) */
static inline bool dump_send(const dump_frame_t *frame, uint32_t frame_seq, uint8_t flags)
{
    const dump_frame_t *const f[1] = { frame };
    return dump_send_frames(f, 1u, frame_seq, flags);
}

/* HAL_UART_TxCpltCallback 안에서 호출 (DMA 송신이 끝났음을 dump에 알려 busy를 해제시킴) */
void dump_on_tx_cplt(UART_HandleTypeDef *huart);

/* 결과 패킷(type 0x02)의 payload. Tools/dump_viewer.py 의 RESULT_FMT 와 순서/크기가 같아야 한다. */
typedef struct __attribute__((packed)) {
    float    tau[3];      /* tau12, tau13, tau23 [샘플] */
    float    peak[3];     /* 쌍별 상관 피크 높이 */
    float    angle_deg;   /* 방향 [deg] */
    float    norm;        /* 방향 벡터 길이 */
    uint16_t onset;       /* 소리 시작 위치 [샘플] (RAW payload의 채널 안 위치) */
    uint16_t win_start;   /* 분석 구간 시작 위치 [샘플] */
    uint32_t proc_us;     /* 계산에 걸린 시간 [us] */
} dump_result_t;

_Static_assert(sizeof(dump_result_t) == 40, "result payload must be 40 bytes");

/* 결과 패킷을 대기시킨다 (1칸). RAW 송신이 진행 중이어도 호출할 수 있고, 실제 송신은 dump_poll()이 한다.
 * 아직 못 보낸 이전 결과가 있으면 덮어쓴다. main 루프에서만 호출할 것. */
void dump_queue_result(const dump_result_t *res, uint32_t frame_seq, uint8_t flags);

/* main 루프에서 계속 호출. 송신 중이 아니고 대기 중인 결과 패킷이 있으면 보낸다. */
void dump_poll(void);

#endif
