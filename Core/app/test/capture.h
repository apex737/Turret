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
 *
 * 용어
 *  - 프레임   : ADC가 한 번에 넘겨주는 1024샘플 x 3채널 묶음 (20.48 ms)
 *  - AC RMS   : 평균(바이어스 ≈2048)을 뺀 신호의 실효값. "얼마나 크게 진동했나"를 나타내는 숫자 [LSB]
 *  - 잡음 바닥: 조용할 때의 RMS. "평소 이 정도는 항상 들린다"는 기준선
 *  - 트리거   : "소리가 났다"고 판단해 덤프를 보내기 시작하는 것
 *  - EMA      : 지수이동평균(Exp-Mov-Avg). 새로운 값을 조금씩 섞어 천천히 따라가는 평균
 */

#include "dump.h"
#include <stdint.h>
#include <stdbool.h>

/* 캡처했을 때 무엇을 보낼지 선택 (여기서 바꾸거나, 컴파일 옵션 -DCAPTURE_SEND_RAW=0 으로 지정)
 *  1 : 원파형(RAW) + 결과 패킷. 검증용 — doa_live.py가 MCU와 PC의 계산을 비교한다. 초당 1회 이하
 *  0 : 결과 패킷만. 운용용 — 62바이트라 송신이 1 ms 미만이고, holdoff가 짧아 자주 갱신된다 */
#ifndef CAPTURE_SEND_RAW
#define CAPTURE_SEND_RAW          1
#endif

/* 트리거 후 재트리거 금지 프레임 수의 기본값 (프레임 하나 = 20.48 ms)
 *  원파형을 보낼 때 : 50 (≈1 s)   송신 134 ms + 잔향
 *  결과만 보낼 때   : 10 (≈0.2 s) 잔향이 가라앉는 시간만. 잔향에 다시 걸리면 늘릴 것 */
#ifndef CAPTURE_HOLDOFF_DEFAULT
#define CAPTURE_HOLDOFF_DEFAULT   (CAPTURE_SEND_RAW ? 50u : 10u)
#endif

/* 트리거 동작을 정하는 설정값 */
typedef struct {
    float    k_on;            /* 잡음 바닥 대비 배수. 4.0 ≈ +12 dB */
    float    min_rms;         /* 절대 하한 [LSB]. 잡음 바닥이 아주 낮을 때 오트리거 방지 */
    uint16_t learn_frames;    /* 부팅 직후 잡음 학습 프레임 수 (트리거 안 함) */
    uint16_t holdoff_frames;  /* 디바운싱 할 프레임 수 */
    float    floor_alpha;     /* 잡음 바닥 EMA 계수 (0~1, 클수록 빨리 따라감) */
} capture_cfg_t;

// 실행 중 바뀌는 상태 (capture_init()에서 초기화)
typedef struct
{
	dump_frame_t prev;			// 직전 프레임 보관 (3ch x 1024 x 2B = 6 KB). 트리거 시 "소리 직전"으로 같이 보냄
	bool prev_valid;			// prev에 쓸 만한 데이터가 있는지 (부팅 직후엔 false)
	uint32_t prev_seq;			// prev의 프레임 번호. 현재 프레임과 연속인지 확인하는 데 사용
	uint32_t frames;			// 지금까지 처리한 프레임 수. learn_frames와 비교해 학습 구간인지 판단
	uint16_t holdoff;			// 재트리거 금지 남은 프레임 수 (0이면 트리거 가능)
	float floor;				// 학습된 잡음 바닥 [LSB]. 조용할 때의 RMS를 EMA로 따라감
	volatile bool manual;		// 수동 캡처 요청 플래그 (버튼 ISR이 세우므로 volatile)
} capture_state_t;

/* cfg == NULL 이면 기본값: k_on 4, min_rms 20, learn 25(≈0.5 s), holdoff CAPTURE_HOLDOFF_DEFAULT, alpha 0.05
 * 내부 상태(잡음 바닥, 직전 프레임, 홀드오프 등)도 모두 초기화한다. */
void capture_init(const capture_cfg_t *cfg);

/* 매 프레임 호출. 이번 프레임을 캡처했으면 true. (원파형을 보냈거나, 결과 전용 모드에서 트리거됨)
 * 비용: RMS 계산 + 6 KB 복사 ≈ 수십 µs, 트리거 시 CRC ≈ 2 ms 추가
 *  frame     : 방금 받은 프레임
 *  frame_seq : 그 프레임의 번호 (직전 프레임과 연속인지 판단하는 데 사용) */
bool capture_on_frame(const dump_frame_t *frame, uint32_t frame_seq);

/* 버튼 등에서 호출: 다음 프레임을 강제로 캡처 (ISR에서 호출 가능)
 * 실제 송신은 ISR이 아니라 다음 capture_on_frame()에서 이뤄진다. 플래그만 세워 두는 함수. */
void capture_request_manual(void);

/* 캡처 직후 불리는 함수. 같은 캡처로 다른 계산(TDOA 등)을 하고 싶을 때 등록한다.
 * 결과 전용 모드(CAPTURE_SEND_RAW 0)에서는 이 함수가 유일한 출력 경로다.
 *  prev  : 직전 프레임 (이어붙이지 못했으면 NULL)
 *  cur   : 트리거 프레임
 *  flags : 패킷에 실린 DUMP_FLAG_*
 * 포인터는 함수가 돌아올 때까지만 유효하다. */
typedef void (*capture_trigger_cb_t)(const dump_frame_t *prev, const dump_frame_t *cur,
                                     uint32_t frame_seq, uint8_t flags);
void capture_set_trigger_cb(capture_trigger_cb_t cb);

#endif
