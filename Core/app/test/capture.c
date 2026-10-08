#include "capture.h"
#include <math.h>
#include <string.h>

#define CLIP_LO   8u
#define CLIP_HI   4087u

volatile capture_status_t g_capture;

static capture_cfg_t   s_cfg;
static dump_frame_t    s_prev;          /* 직전 프레임 보관 (6 KB) */
static bool            s_prev_valid;
static uint32_t        s_prev_seq;
static uint32_t        s_frames;
static uint16_t        s_holdoff;
static float           s_floor;
static volatile bool   s_manual;

/**
 * @brief  프레임 통계 계산
 * @param  f: 입력 프레임
 * @param  rms: AC RMS 계산 결과 (DUMP_CH)
 * @param  clip: 클리핑 샘플 수 계산 결과 (DUMP_CH)
 */
static void frame_stats(const dump_frame_t *f, float rms[DUMP_CH], uint16_t clip[DUMP_CH])
{
    for (uint32_t c = 0; c < DUMP_CH; c++) {
        const uint16_t *x = (*f)[c];
        uint32_t s  = 0;
        uint64_t s2 = 0;
        uint16_t nc = 0;
        for (uint32_t i = 0; i < DUMP_N; i++) {
            uint32_t v = x[i];
            s  += v;
            s2 += (uint64_t)(v * v);
            nc += (v <= CLIP_LO || v >= CLIP_HI) ? 1u : 0u;
        }
        uint64_t num = (uint64_t)DUMP_N * s2 - (uint64_t)s * s;
        rms[c]  = sqrtf((float)num) / (float)DUMP_N;
        clip[c] = nc;
    }
}

/**
 * @brief  캡처 모듈 초기화
 * @param  cfg: 캡처 설정 (NULL이면 기본값)
 */
void capture_init(const capture_cfg_t *cfg)
{
    static const capture_cfg_t def = {
        .k_on = 4.0f, .min_rms = 20.0f,
        .learn_frames = 25u, .holdoff_frames = 50u, .floor_alpha = 0.05f,
    };
    s_cfg        = cfg ? *cfg : def;
    s_prev_valid = false;
    s_frames     = 0;
    s_holdoff    = 0;
    s_floor      = 0.0f;
    s_manual     = false;
    memset((void *)&g_capture, 0, sizeof(g_capture));
}

/**
 * @brief  수동 캡처 요청
 */
void capture_request_manual(void)
{
    s_manual = true;
}

/**
 * @brief  프레임 수신 시 처리
 * @param  frame: 수신된 프레임
 * @param  frame_seq: 프레임 번호
 * @retval true: 송신 성공, false: 송신 실패 또는 송신 안 함
 */
bool capture_on_frame(const dump_frame_t *frame, uint32_t frame_seq)
{
    float    rms[DUMP_CH];
    uint16_t clip[DUMP_CH];
    frame_stats(frame, rms, clip);

    float    level    = rms[0];
    uint32_t clip_sum = 0;
    for (uint32_t c = 0; c < DUMP_CH; c++) {
        if (rms[c] > level) level = rms[c];
        clip_sum += clip[c];
        g_capture.rms[c]  = rms[c];
        g_capture.clip[c] = clip[c];
    }

    s_frames++;
    if (s_holdoff) s_holdoff--;

    const bool  learning = (s_frames <= s_cfg.learn_frames);
    float       thr      = s_cfg.k_on * s_floor;
    if (thr < s_cfg.min_rms) thr = s_cfg.min_rms;
    const bool  loud     = (level > thr);
    const bool  manual   = s_manual;
    bool        sent     = false;

    if (manual || (!learning && s_holdoff == 0u && loud)) {
        if (dump_busy()) {
            g_capture.skip_busy++;
        } else {
            uint8_t flags = 0u;
            if (clip_sum) flags |= DUMP_FLAG_CLIP;
            if (manual)   flags |= DUMP_FLAG_MANUAL;

            /* 직전 프레임이 바로 앞 번호일 때만 이어붙임 (중간에 drop이 있으면 시간축이 끊김) */
            if (s_prev_valid && frame_seq == s_prev_seq + 1u) {
                const dump_frame_t *const fr[2] = { &s_prev, frame };
                sent = dump_send_frames(fr, 2u, frame_seq, flags | DUMP_FLAG_PRETRIG);
            } else {
                sent = dump_send(frame, frame_seq, flags);
            }
            if (sent) {
                g_capture.trig_cnt++;
                s_holdoff = s_cfg.holdoff_frames;
                s_manual  = false;
            }
        }
    }

    /* 잡음 바닥 학습: 학습 구간이거나, 조용한 프레임일 때만 갱신 (박수·잔향은 제외) */
    if (learning || !loud) {
        if (s_frames == 1u) s_floor = level;
        else                s_floor += s_cfg.floor_alpha * (level - s_floor);
        if (s_floor < 1.0f) s_floor = 1.0f;
    }
    g_capture.floor     = s_floor;
    g_capture.threshold = thr;

    memcpy(s_prev, *frame, sizeof(s_prev));
    s_prev_seq   = frame_seq;
    s_prev_valid = true;

    return sent;
}
