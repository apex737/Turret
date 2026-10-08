#ifndef CAPTURE_H
#define CAPTURE_H

/*
 * capture : 소리가 나면 자동으로 프레임을 얼려서 dump로 보내는 디버그 블럭
 *
 *  - 매 프레임 채널별 AC RMS를 계산하고, 조용할 때의 RMS를 잡음 바닥으로 학습(EMA)
 *  - max(rms) > k_on × 잡음바닥  이고  > min_rms  이면 트리거
 *  - 트리거 시 [직전 프레임 | 트리거 프레임] 2개를 한 패킷으로 송신 → 소리 시작점이 항상 포함됨
 *  - 트리거 후 holdoff 동안은 재트리거 금지 (잔향, 송신 시간 보호)
 *
 * 사용: 메인 루프에서 adc_get_frame() 직후 capture_on_frame() 호출
 */

#include "dump.h"
#include <stdint.h>
#include <stdbool.h>

typedef struct {
    float    k_on;            /* 잡음 바닥 대비 배수. 4.0 ≈ +12 dB */
    float    min_rms;         /* 절대 하한 [LSB]. 잡음 바닥이 아주 낮을 때 오트리거 방지 */
    uint16_t learn_frames;    /* 부팅 직후 잡음 학습 프레임 수 (트리거 안 함) */
    uint16_t holdoff_frames;  /* 트리거 후 재트리거 금지 프레임 수 */
    float    floor_alpha;     /* 잡음 바닥 EMA 계수 (0~1, 클수록 빨리 따라감) */
} capture_cfg_t;

/* CubeMonitor에서 보기 위한 상태 (읽기 전용으로 사용) */
typedef struct {
    float    rms[DUMP_CH];    /* 이번 프레임 AC RMS [LSB] */
    uint16_t clip[DUMP_CH];   /* 이번 프레임 클리핑 샘플 수 (≤8 또는 ≥4087) */
    float    floor;           /* 학습된 잡음 바닥 [LSB] */
    float    threshold;       /* 현재 트리거 임계값 [LSB] */
    uint32_t trig_cnt;        /* 송신한 캡처 수 */
    uint32_t skip_busy;       /* 트리거됐지만 이전 송신 중이라 버린 수 */
} capture_status_t;

extern volatile capture_status_t g_capture;

/* cfg == NULL 이면 기본값: k_on 4, min_rms 20, learn 25(≈0.5 s), holdoff 50(≈1 s), alpha 0.05 */
void capture_init(const capture_cfg_t *cfg);

/* 매 프레임 호출. 이번 프레임에서 패킷을 보냈으면 true.
 * 비용: RMS 계산 + 6 KB 복사 ≈ 수십 µs, 트리거 시 CRC ≈ 2 ms 추가 */
bool capture_on_frame(const dump_frame_t *frame, uint32_t frame_seq);

/* 버튼 등에서 호출: 다음 프레임을 강제로 캡처 (ISR에서 호출 가능) */
void capture_request_manual(void);

#endif
