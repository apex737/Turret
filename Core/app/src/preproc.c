/*
 * preproc.c : 50 kHz 3채널 ADC 프레임 → FIR 저역 통과 + 4:1 데시메이션 → 12.5 kHz int16 PCM (규약은 preproc.h)
 *
 *  한 프레임 처리 순서 (채널마다 반복)
 *    1) uint16 ADC 값(0 ~ 4095)을 클리핑 검사하고, 2048을 빼서 0 중심 float로 바꾼다  → s_in
 *    2) arm_fir_decimate_f32: 75탭 FIR을 걸면서 4개 중 1개만 계산한다 (1024 → 256)  → s_out
 *    3) ×16 한 뒤 반올림하고 int16 범위로 포화시킨다                                → out
 *  FIR은 과거 입력(직전 74샘플)을 기억해야 하므로, 채널마다 CMSIS 인스턴스와 상태 버퍼를 따로 둔다.
 */
#include "preproc.h"
#include "arm_math.h"
#include <math.h>

/* 클리핑 판정 문턱 (12비트 ADC 0 ~ 4095의 양 끝 8 LSB). capture.h와 같은 값이다.
 * 마이크 신호가 이 범위에 닿으면 파형 꼭대기가 잘려 지연 추정이 틀어지므로 표시만 하고 처리는 계속한다. */
#define CLIP_LO 8u
#define CLIP_HI 4087u

/* s_fir[c] : 채널 c의 CMSIS FIR 데시메이터 인스턴스. 계수 포인터·탭 수·M·상태 버퍼 포인터를 묶어 둔 것.
 *            preproc_reset()이 초기화하고, preproc_run()이 매 프레임 넘겨준다. */
static arm_fir_decimate_instance_f32 s_fir[PREPROC_CH];
/* s_state[c] : 채널 c의 FIR 상태(지연선). 앞 74칸에 직전 프레임 끝부분 입력이 남아 있어서
 *              프레임 경계를 넘어 필터가 끊김 없이 이어진다. 크기 1098 float × 3채널 ≈ 13 KB.
 *              CMSIS가 내부에서 [이전 74샘플 | 이번 1024샘플]을 이어 붙이는 작업 공간으로도 쓴다. */
static float32_t s_state[PREPROC_CH][FIR_NUM_TAPS + PREPROC_IN - 1u];   /* CMSIS 요구 크기: numTaps + blockSize − 1 */
/* s_in  : 지금 처리 중인 한 채널의 입력 (0 중심 float, 1024개 = 4 KB)
 * s_out : 그 채널의 필터 출력 (float, 256개 = 1 KB, ×16 전)
 * 채널을 하나씩 차례로 처리하므로 세 채널이 같은 작업 버퍼를 돌려 쓴다 (그래서 이 함수는 재진입 불가: main에서만 호출). */
static float32_t s_in[PREPROC_IN];
static float32_t s_out[PREPROC_OUT];

/* arm_fir_decimate_init_f32는 blockSize가 M의 배수가 아니면 실패한다. 컴파일 시점에 미리 막는다 */
_Static_assert(PREPROC_IN % FIR_DECIM_M == 0u, "block size must be a multiple of M");

/* 세 채널의 FIR 상태를 0으로 초기화 (부팅 시, ADC 유실·overrun 뒤, 검증 burst 시작 시).
 * 상태가 0에서 시작하면 첫 PREPROC_TRANSIENT_OUT(19) 출력 샘플은 "과거가 0이었다"고 가정한 과도 구간이 된다. */
void preproc_reset(void)
{
	for (uint32_t c = 0; c < PREPROC_CH; c++) {
		/* init이 상태 버퍼를 0으로 채운다 */
		if (arm_fir_decimate_init_f32(&s_fir[c], (uint16_t)FIR_NUM_TAPS, (uint8_t)FIR_DECIM_M,
		                              fir_coeffs, s_state[c], PREPROC_IN) != ARM_MATH_SUCCESS)
			error_handle();   /* 인자 조합이 틀린 것 = 코드 버그. 멈춰서 디버거로 보게 한다 */
	}
}

/* 프레임 하나(채널당 1024샘플)를 처리한다
 *  in  : adc_get_frame()이 채운 채널별 원본 uint16[3][1024]
 *  out : 결과 int16[3][256] (stream_push / doa_push로 넘어감)
 *  반환: 세 채널 중 어디든 클리핑 샘플이 하나라도 있었으면 true → 호출자가 STREAM_FLAG_CLIP / DUMP_FLAG_CLIP을 세운다 */
bool preproc_run(const uint16_t in[PREPROC_CH][PREPROC_IN], int16_t out[PREPROC_CH][PREPROC_OUT])
{
	bool clip = false;                        /* 이 프레임에서 클리핑을 본 적이 있나 (세 채널 누적) */
	for (uint32_t c = 0; c < PREPROC_CH; c++) {
		/* 1) 정수 ADC 값 → 0 중심 float */
		for (uint32_t i = 0; i < PREPROC_IN; i++) {
			const uint32_t v = in[c][i];      /* v : ADC 원본 한 샘플 (0 ~ 4095) */
			clip |= (v <= CLIP_LO) || (v >= CLIP_HI);
			s_in[i] = (float32_t)((int32_t)v - PREPROC_ADC_CENTER);   /* −2048 ~ +2047 */
		}
		/* 2) FIR + ↓4. 마지막 인자는 입력 샘플 수(1024), 출력은 1024 / 4 = 256개 */
		arm_fir_decimate_f32(&s_fir[c], s_in, s_out, PREPROC_IN);
		/* 3) float → int16. ×16 하면 12비트 진폭(±2048)이 int16 진폭(±32768)에 맞는다 */
		for (uint32_t k = 0; k < PREPROC_OUT; k++) {
			/* lrintf: 현재 FPU 반올림 모드(기본 nearest-even)로 정수화. PC 기준은 np.rint와 같음 */
			const int32_t r = (int32_t)lrintf(s_out[k] * PREPROC_PCM_SCALE);   /* r : 포화 전 정수 결과 */
			out[c][k] = (int16_t)__SSAT(r, 16);   /* __SSAT(r, 16): −32768 ~ 32767로 자른다 (FIR 오버슈트 대비) */
		}
	}
	return clip;
}
