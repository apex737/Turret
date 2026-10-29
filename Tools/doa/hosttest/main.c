/* MCU의 doa.c + CMSIS arm_rfft_fast_f32를 PC에서 그대로 돌린다 (Tools/doa/test_doa_host.py가 빌드·실행).
 * stdin : 프레임마다 [uint32 frame_seq][uint8 restart][int16 pcm[DOA_CH][256]] 반복 (little endian, 4채널)
 * stdout: 끝난 관측 창마다 CSV 한 줄 (s0, tau×6, peak×6, angle, elev, norm, resid, snr_db, flags, bg_s0, bg_n),
 *         재시작 프레임마다 #restart */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdbool.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
#include "doa.h"

/* MCU 쪽 함수 대역. doa.c가 부르지만 MCU에서는 def.c / app.c에 있는 것들이다 */
void error_handle(void) { fprintf(stderr, "error\n"); exit(1); }   /* MCU는 무한 루프로 멈추지만, PC에서는 실패 코드로 끝낸다 */
uint32_t doa_now_cycles(void) { return 0u; }                         /* DWT 사이클 카운터가 없음 → proc_us는 항상 0 */

int main(void)
{
#ifdef _WIN32
	_setmode(_fileno(stdin), _O_BINARY);      /* 텍스트 모드면 0x1A(EOF)·\r\n 변환으로 이진 입력이 깨진다 */
#endif
	static int16_t pcm[DOA_CH][DOA_FRAME];    /* 프레임 하나의 12.5 kHz PCM, 채널별 256샘플 (MCU의 preproc 출력과 같은 모양) */
	uint32_t seq;                             /* 그 프레임의 ADC 프레임 번호. doa_push가 샘플 번호(s0)를 계산하는 데 쓴다 */
	uint8_t restart;                          /* 1 = 녹음 파일의 첫 프레임. 앞과 시간축이 이어지지 않음 (MCU에서는 RESYNC 프레임에 해당) */
	doa_result_t r;                           /* doa_push가 관측 창 하나를 끝냈을 때 채우는 결과 */
	doa_init();
	/* 프레임 레코드를 하나씩 읽는다: seq(4 B) → restart(1 B) → pcm(DOA_CH × 512 B). 헤더를 못 읽으면 입력 끝으로 보고 정상 종료 */
	while (fread(&seq, 4, 1, stdin) == 1 && fread(&restart, 1, 1, stdin) == 1) {
		if (fread(pcm, 2, DOA_CH * DOA_FRAME, stdin) != DOA_CH * DOA_FRAME)
			return 1;                         /* 헤더 뒤 PCM이 잘림 = 입력 파일이 깨짐 */
		if (restart)
			printf("#restart\n");                 /* 녹음 경계 표시 */
		/* MCU의 on_stream_frame()과 같은 호출. 창이 끝난 프레임에서만 true → 결과 한 줄 출력.
		 * float는 %.9g: float32 값을 손실 없이 문자열로 옮기는 자릿수 */
		if (doa_push(pcm, seq, restart != 0u, &r)) {
			printf("%u", r.s0);
			for (unsigned p = 0; p < DOA_PAIRS; p++) printf(",%.9g", r.tau[p]);
			for (unsigned p = 0; p < DOA_PAIRS; p++) printf(",%.9g", r.peak[p]);
			printf(",%.9g,%.9g,%.9g,%.9g,%.9g,%u,%u,%u\n", r.angle_deg, r.elev_deg, r.norm, r.resid, r.snr_db,
			       r.flags, r.bg_s0, r.bg_n);
		}
	}
	return 0;
}
