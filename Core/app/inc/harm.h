#ifndef INC_HARM_H_
#define INC_HARM_H_

/*
 * harm : MIC1 12.5 kHz PCM에서 고조파 점수 B0를 계산한다 (Step8b B0의 MCU 이식, 스피드런 2026-11-04)
 *
 *  - Tools/harmonic/score.py의 score()와 같은 계산. 상수는 그쪽과 같아야 Tools/harmonic/test_b0_host.py로 비교된다 (I3).
 *  - 프레임: 2048점 Hann, 1024샘플마다 (164 ms 창, 82 ms 이동). 프레임마다 전력 P, 바닥 = 이웃 33빈 중앙값 ÷ ln2,
 *    SNR = P ÷ 바닥, 빈마다 ±1빈 최대, (SNR − 1)을 0 ~ 9로 자름 → pk. score.py와 달리 평균(DC)은 프레임마다 뺀다.
 *  - 창: 프레임 11개(= 2048 + 10 × 1024 = 12288샘플 ≈ 1 s). 프레임 6개(6144샘플 ≈ 0.49 s)마다 새 창을 시작한다.
 *    창 점수 = 기본음 후보 f0 40 ~ 700 Hz(1 Hz 간격)마다 고조파 1 ~ 4번 빈의 pk 합을 프레임 평균한 곡선의 최댓값.
 *  - 메모리: FFT는 doa.c의 블록 FFT 작업 공간(doa_scratch, 8 KB)을 같이 쓴다. doa_push가 끝난 뒤에만 계산한다.
 *  - CPU: 무거운 계산(FFT·중앙값)은 4프레임(1024샘플)에 한 번. DOA 창이 끝난 프레임이면 다음 프레임으로 미룬다.
 * 시간축: 샘플 번호 = (frame_seq − 1) × 256 + 블록 안 위치 (doa.h와 같음).
 */

#include "def.h"

#define HARM_FRAME        256u      // 입력 프레임당 샘플 수 (PREPROC_OUT과 같아야 함)
#define HARM_FS           12500.0f
#define HARM_NFFT         2048u     // score.py NFFT
#define HARM_HOP          1024u     // score.py HOP
#define HARM_NFR          11u       // 창 하나의 프레임 수 = 1 + (12500 − 2048) ÷ 1024 (score.py가 1 s 창에서 만드는 프레임 수)
#define HARM_WIN_HOP      6u        // 창 시작 간격 [프레임] = 6144샘플 ≈ 0.49 s (분류 창 1 s · 0.5 s 이동과 맞춤)
#define HARM_H            4u        // score.py H: 고조파 1 ~ 4번
#define HARM_CAP          10.0f     // score.py CAP: 빈마다 SNR 상한
#define HARM_FLOOR_BINS   33u       // score.py FLOOR_BINS: 바닥 중앙값 이웃 수 (≈ 200 Hz)
#define HARM_F0_MIN       40u       // 기본음 후보 [Hz] (Step8b 판정 범위 40 ~ 700 Hz)
#define HARM_F0_MAX       700u
#define HARM_THR          13.1f     // 드론 후보 문턱: Step8b fold 문턱 5개(12.72 · 14.80 · 12.48 · 12.94 · 12.65)의 평균 {계산}

#define HARM_FLAG_POS     0x01u     // score ≥ HARM_THR
#define HARM_FLAG_RESTART 0x02u     // 이 창 앞에서 재시작이 있었음 (첫 창)

typedef struct {
	uint32_t s0;                    // 창 첫 샘플 번호
	uint32_t n;                     // 창 길이 [샘플] = 12288
	float    score;                 // 창 점수 (잡음만이면 0 근처, 드론 중앙 약 25)
	float    f0;                    // 점수가 가장 큰 기본음 후보 [Hz]
	float    rms_db;                // 창 MIC1 RMS [dBFS] (평균을 뺀 값, int16 만점 기준). PC가 조용한 창(보드 바닥 + 6 dB 미만)을 거른다
	uint16_t frames;                // 창에 들어간 프레임 수 (= HARM_NFR)
	uint16_t proc_us;               // 이 창 동안 프레임 계산 한 번의 최대 시간 [us]
	uint8_t  flags;                 // HARM_FLAG_*
} harm_result_t;

// 상태 초기화. 부팅 시 한 번
void harm_init(void);

/* PCM 한 프레임(MIC1)을 넣는다. 창이 끝나면 out을 채우고 true.
 *  restart : 이 프레임 앞에서 입력이 끊겼음 → 진행 중인 창을 버리고 다음 프레임부터 새로 시작 (doa_push와 같은 규칙)
 *  defer   : 이번 프레임에 무거운 계산을 하지 않는다 (DOA 창이 끝난 프레임). 미룬 계산은 다음 호출의 맨 앞에서 한다 */
bool harm_push(const int16_t pcm[HARM_FRAME], uint32_t frame_seq, bool restart, bool defer, harm_result_t *out);

#endif /* INC_HARM_H_ */
