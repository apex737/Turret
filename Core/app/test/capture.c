#include "capture.h"
#include <math.h>
#include <string.h>

/* 클리핑 판정 경계. 12비트 ADC는 0~4095인데, 양 끝 근처에 붙은 샘플은 신호가 잘렸다고 본다 */
#define CLIP_LO 8u
#define CLIP_HI 4087u

// 현재 설정 (k_on, min_rms, learn/holdoff 프레임 수, floor_alpha)
static capture_cfg_t conf;
static capture_state_t stat;
static capture_trigger_cb_t on_trigger; // 캡처를 보낸 직후 부를 함수 (없으면 NULL)

// 프레임 통계 계산
static void frame_stats(
		const dump_frame_t *f,	// 입력 프레임
		float rms[DUMP_CH],			// RMS (트리거; 신호에서 소리가 크다는 것 == 진동의 폭이 크다)
		uint16_t clip[DUMP_CH]) // 0, 4095 샘플수 -> 신호가 너무 큰지 경고 (flags에 CLIP 표시)
{
	for (uint32_t ch = 0; ch < DUMP_CH; ch++) /* 채널마다 따로 계산 */
	{
		const uint16_t *x = (*f)[ch]; /* 이 채널의 1024샘플 */
		uint32_t s = 0;								/* 합 Σv */
		uint64_t s2 = 0;							/* 제곱의 합 Σv² (커질 수 있어 64비트) */
		uint16_t num_clip = 0;				/* 클리핑 샘플 개수 */
		for (uint32_t i = 0; i < DUMP_N; i++)
		{
			uint32_t v = x[i];
			s += v;
			s2 += (uint64_t)(v * v);															/* 4095² ≈ 1.7천만이라 32비트 곱은 안전 */
			num_clip += (v <= CLIP_LO || v >= CLIP_HI) ? 1u : 0u; /* 양 끝에 붙었으면 +1 */
		}

		// 표준편차 = sqrt( (N·Σv² - (Σv)²) ) / N
		uint64_t num = (uint64_t)DUMP_N * s2 - (uint64_t)s * s;
		rms[ch] = sqrtf((float)num) / (float)DUMP_N;
		clip[ch] = num_clip;
	}
}

// 캡처 모듈 초기화
void capture_init(
		const capture_cfg_t *cfg // 캡처 설정 (NULL이면 기본값)
)
{
	static const capture_cfg_t dflt = {
			/* cfg가 NULL일 때 쓰는 default 값 */
			.k_on = 4.0f,
			.min_rms = 20.0f,
			.learn_frames = 25u,
			.holdoff_frames = CAPTURE_HOLDOFF_DEFAULT,
			.floor_alpha = 0.05f,
	};
	conf = cfg ? *cfg : dflt; /* 인자가 있으면 그것, 없으면 기본값을 복사 */
	stat.prev_valid = false;	/* 아직 직전 프레임 없음 */
	stat.frames = 0;					/* 학습 구간 처음부터 */
	stat.holdoff = 0;					/* 홀드오프 없음 */
	stat.floor = 0.0f;				/* 잡음 바닥은 첫 프레임에서 정해짐 */
	stat.manual = false;
}

/**
 * @brief  수동 캡처 요청
 * @note   플래그만 세운다. 실제 송신은 다음 capture_on_frame()에서 (ISR에서 호출해도 안전)
 */
void capture_request_manual(void)
{
	stat.manual = true;
}

// 캡처를 보낸 직후 부를 함수 등록 (NULL이면 해제)
void capture_set_trigger_cb(capture_trigger_cb_t cb)
{
	on_trigger = cb;
}

// 프레임 수신 시 처리
bool capture_on_frame(
		const dump_frame_t *frame, // 수신된 프레임
		uint32_t frame_seq				 // 프레임 번호
)
/** 한 프레임당 흐름:
 *  1) 크기(level) 측정
 * 	2) 임계값 계산
 * 	3) 조건 만족 시 송신
 *  4) 잡음 바닥 갱신
 *  5) 이번 프레임을 직전 프레임으로 저장 */
{
	float rms[DUMP_CH];
	uint16_t clip[DUMP_CH];

	// 채널별 RMS(신호크기), 클리핑 개수 계산
	frame_stats(frame, rms, clip);

	// 1) RMS(신호크기) 측정
	float level = rms[0];
	uint32_t clip_sum = 0; /* 3채널 클리핑 합 (flags 결정용) */
	for (uint32_t ch = 0; ch < DUMP_CH; ch++)
	{
		if (rms[ch] > level)
			level = rms[ch];
		clip_sum += clip[ch];
	}

	stat.frames++; /* 처리한 프레임 수 +1 */
	if (stat.holdoff)
		stat.holdoff--; /* 홀드오프가 남아있으면 1프레임 소모 */

	// --- 2) 임계값 계산 ---
	// learning : 부팅 직후 잡음 학습 중인가 (이 동안은 트리거 금지)
	const bool learning = (stat.frames <= conf.learn_frames);

	// thr : 잡음 바닥의 k_on배. 단, 최소 min_rms 이상
	float thr = conf.k_on * stat.floor;
	if (thr < conf.min_rms)
		thr = conf.min_rms;

	const bool trig = (level > thr);
	const bool manual = stat.manual; /* 이 함수 도중 값이 바뀌지 않도록 한 번만 읽어 복사 */
	bool sent = false;

	/* --- 3) 송신 조건: 수동 요청이거나, (학습 끝 && 홀드오프 끝 && 소리 큼) --- */
	if (manual || (!learning && stat.holdoff == 0u && trig))
	{
		uint8_t flags = 0u;
		if (clip_sum)
			flags |= DUMP_FLAG_CLIP; /* 클리핑이 있었음 */
		if (manual)
			flags |= DUMP_FLAG_MANUAL; /* 수동 트리거 */

		/* 직전 프레임이 바로 앞 번호일 때만 이어붙임 (중간에 drop이 있으면 시간축이 끊김)
		 * prev_valid: 보관해 둔 직전 프레임이 있다 (부팅 직후 첫 프레임에는 없음)
		 * frame_seq == prev_seq + 1: 직전 프레임 번호가 바로 앞 번호다. */
		const bool pretrig = (stat.prev_valid && frame_seq == stat.prev_seq + 1u);
		if (pretrig)
			flags |= DUMP_FLAG_PRETRIG;

#if CAPTURE_SEND_RAW
		if (!dump_busy()) /* 이전 패킷을 아직 보내는 중이면 이번 건은 포기 */
		{
			if (pretrig)
			{
				// {직전, 현재} 두 프레임을 순서대로 보냄
				const dump_frame_t *const fr[2] = {&stat.prev, frame};
				sent = dump_send_frames(fr, 2u, frame_seq, flags);
			}
			else
			{
				sent = dump_send(frame, frame_seq, flags);
			}
		}
#else
		sent = true; /* 결과 전용 모드: 원파형은 보내지 않고, 아래 콜백이 결과 패킷만 보낸다 */
#endif

		if (sent)
		{
			stat.holdoff = conf.holdoff_frames; /* 잔향/송신 시간 동안 재트리거 금지 시작 */
			stat.manual = false;								/* 수동 요청 소비 (송신에 성공했을 때만 지움 → 실패하면 다음 프레임에 재시도) */

			// 같은 캡처를 넘겨준다. stat.prev는 아래 5)에서 덮어쓰기 전이라 아직 직전 프레임
			if (on_trigger)
				on_trigger(pretrig ? &stat.prev : NULL, frame, frame_seq, flags);
		}
	}

	/* --- 4) 잡음 바닥 학습: 학습 구간이거나, 조용한 프레임일 때만 갱신 (박수·잔향은 제외) ---
	 *  EMA: floor += alpha × (level - floor)  → 새 값 쪽으로 alpha 비율만큼 천천히 이동
	 *  소리가 난 프레임으로 갱신하면 임계값이 같이 올라가 다음 소리를 놓치므로 trig일 땐 건드리지 않는다. */
	if (learning || !trig)
	{
		if (stat.frames == 1u)
			stat.floor = level; /* 첫 프레임은 그 값으로 바로 초기화 */
		else
			stat.floor += conf.floor_alpha * (level - stat.floor);
		if (stat.floor < 1.0f)
			stat.floor = 1.0f; /* 바닥이 0이 되면 임계값이 0이 되는 것 방지 */
	}

	/* 5) 상태 갱신 (prev = curr) */
	memcpy(stat.prev, *frame, sizeof(stat.prev));
	stat.prev_seq = frame_seq;
	stat.prev_valid = true;

	return sent; // true: 캡처함 (원파형 송신 성공 또는 결과 전용 모드에서 트리거), false: 캡처 안 함
}
