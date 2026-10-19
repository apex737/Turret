#ifndef INC_STREAM_H_
#define INC_STREAM_H_

/*
 * stream : 12.5 kHz 3채널 PCM을 프레임(20.48 ms)마다 패킷 하나로 UART DMA 송신 (Step5)
 *
 * PCM 패킷 v3 (little endian, 24 + 1536 + 2 = 1562 B, 초당 약 48.8개 = 76.3 KB/s)
 *
 *  off size field
 *   0   4   sync      FF FF FF FF
 *   4   1   ver       3
 *   5   1   type      0x03 (PCM_12K5)
 *   6   1   ch        3
 *   7   1   flags     STREAM_FLAG_*
 *   8   4   seq       송신 패킷 번호 (송신 큐에서 버려진 것도 번호를 소비 → PC가 빈 번호로 큐 유실을 앎)
 *  12   4   frame_seq ADC 프레임 번호 (adc.c ISR이 매김). 이 블록의 첫 샘플 = (frame_seq − 1) × 256 (12.5 kHz 기준)
 *  16   2   n         채널당 샘플 수 (256, 검증 모드는 같음)
 *  18   2   len       payload 바이트 = ch × n × 2
 *  20   1   drop      ADC 프레임 유실 누계 (mod 256)
 *  21   1   ovr       ADC overrun 누계 (mod 256)
 *  22   1   qdrop     송신 큐 유실 누계 (mod 256)
 *  23   1   cpu       직전 프레임의 전처리+큐 적재 시간 (프레임 주기 20.48 ms 대비 %)
 *  24 len   payload   ch0[n] | ch1[n] | ch2[n]  (int16 LE)
 *  24+len 2 crc16     CRC-16/CCITT-FALSE, 범위 = ver ~ payload 끝
 *
 * PCM에는 FF FF FF FF가 나올 수 있으므로 PC는 sync만 믿지 않고 ver·type·len·CRC가 모두 맞을 때만 받는다.
 *
 * DOA 결과 패킷 (같은 헤더, type 0x04, ch 3, n 1, len 52. 관측 창 하나가 끝날 때마다 = 초당 4개)
 *  seq는 PCM과 따로 매긴다. frame_seq = 창이 끝난 프레임. payload (Tools/board/dump_viewer.py DOA_FMT):
 *   off size field
 *    0   4   s0        관측 창 첫 샘플 번호 (PCM 시간축)
 *    4  12   tau[3]    float, 채널 지연 보정 후 [샘플 @12.5 kHz] (1,2) (1,3) (2,3)
 *   16  12   peak[3]   float
 *   28   4   angle     float [deg]
 *   32   4   norm      float
 *   36   4   snr_db    float (배경이 없으면 0)
 *   40   1   flags     DOA_FLAG_* (doa.h)
 *   41   1   reserved
 *   42   2   proc_us   창 마무리 계산 시간 (상한 65535)
 *   44   4   bg_s0     사용한 배경의 첫 샘플 번호
 *   48   4   bg_n      배경 길이 [샘플] (0 = 배경 없음, D0)
 */

#include "def.h"
#include "preproc.h"
#include "doa.h"

#define STREAM_VER        3u
#define STREAM_TYPE_PCM   0x03u
#define STREAM_TYPE_DOA   0x04u

#define STREAM_FLAG_CLIP   0x01u   /* 이 프레임의 ADC 입력에 클리핑 */
#define STREAM_FLAG_RESYNC 0x02u   /* 이 블록 직전에 FIR 상태를 0으로 초기화 → 첫 PREPROC_TRANSIENT_OUT 샘플은 과도 구간 */
#define STREAM_FLAG_VERIFY 0x04u   /* 검증 모드: 같은 frame_seq의 원본 burst와 짝 */
#define STREAM_FLAG_GAP    0x08u   /* 이 블록 앞에서 샘플이 빠졌음 (ADC 유실, overrun, 큐 유실) */

#define STREAM_SLOTS       4u      /* 송신 큐 칸 수 (1칸 = 1프레임) */
#define STREAM_DOA_SLOTS   4u      /* DOA 결과 큐 칸 수 */

void stream_init(UART_HandleTypeDef *huart);

/* PCM 블록 하나를 큐에 넣고, 송신 중이 아니면 송신을 시작한다. 큐가 가득 차면 버리고 false (qdrop 증가). main에서만 호출. */
bool stream_push(const int16_t pcm[PREPROC_CH][PREPROC_OUT], uint32_t frame_seq, uint8_t flags,
                 uint32_t drop, uint32_t ovr, uint8_t cpu_pct);

/* DOA 결과 하나를 큐에 넣는다. UART가 비면 PCM보다 먼저 나간다. 큐가 가득 차면 버리고 false. main에서만 호출. */
bool stream_push_doa(const doa_result_t *r, uint32_t frame_seq);

/* 송신 중이거나 보낼 것이 남았으면 true */
bool stream_busy(void);

/* 비어 있는 큐 칸 수 */
uint32_t stream_free(void);

/* main 루프에서 계속 호출. UART가 비었는데(예: dump 송신이 막 끝남) 큐에 남은 것이 있으면 송신을 시작한다 */
void stream_poll(void);

uint32_t stream_get_qdrop_cnt(void);

/* HAL_UART_TxCpltCallback에서 호출 */
void stream_on_tx_cplt(UART_HandleTypeDef *huart);

#endif /* INC_STREAM_H_ */
