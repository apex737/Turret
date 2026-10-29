#ifndef INC_STREAM_H_
#define INC_STREAM_H_

#include "def.h"
#include "preproc.h"
#include "doa.h"

#define STREAM_VER        3u      /* PCM 패킷 */
#define STREAM_DOA_VER    4u      /* DOA 결과 패킷: 4채널 (6쌍 + 고도각, 84 B payload). 3 = 예전 3채널 */
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
