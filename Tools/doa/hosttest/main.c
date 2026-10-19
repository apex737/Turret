/* MCU의 doa.c + CMSIS arm_rfft_fast_f32를 PC에서 그대로 돌린다 (Tools/doa/test_doa_host.py가 빌드·실행).
 * stdin : 프레임마다 [uint32 frame_seq][uint8 restart][int16 pcm[3][256]] 반복 (little endian)
 * stdout: 끝난 관측 창마다 CSV 한 줄 (s0, tau×3, peak×3, angle, norm, snr_db, flags, bg_s0, bg_n), 재시작 프레임마다 #restart */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdbool.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
#include "doa.h"

void error_handle(void) { fprintf(stderr, "error\n"); exit(1); }
uint32_t doa_now_cycles(void) { return 0u; }

int main(void)
{
#ifdef _WIN32
	_setmode(_fileno(stdin), _O_BINARY);
#endif
	static int16_t pcm[DOA_CH][DOA_FRAME];
	uint32_t seq;
	uint8_t restart;
	doa_result_t r;
	doa_init();
	while (fread(&seq, 4, 1, stdin) == 1 && fread(&restart, 1, 1, stdin) == 1) {
		if (fread(pcm, 2, DOA_CH * DOA_FRAME, stdin) != DOA_CH * DOA_FRAME)
			return 1;
		if (restart)
			printf("#restart\n");                 /* 녹음 경계 표시 (test_doa_host.py가 결과를 나눔) */
		if (doa_push(pcm, seq, restart != 0u, &r))
			printf("%u,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%u,%u,%u\n", r.s0,
			       r.tau[0], r.tau[1], r.tau[2], r.peak[0], r.peak[1], r.peak[2],
			       r.angle_deg, r.norm, r.snr_db, r.flags, r.bg_s0, r.bg_n);
	}
	return 0;
}
