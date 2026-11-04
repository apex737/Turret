/* MCU의 harm.c(B0) + CMSIS cfft를 PC에서 그대로 돌린다 (Tools/harmonic/test_b0_host.py가 빌드·실행).
 * stdin : 프레임마다 [uint32 frame_seq][uint8 restart][uint8 defer][int16 pcm[256]] 반복 (little endian, MIC1만)
 * stdout: 끝난 창마다 CSV 한 줄 (s0, n, score, f0, rms_db, frames, flags) */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdbool.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
#include "harm.h"

void error_handle(void) { fprintf(stderr, "error\n"); exit(1); }
uint32_t doa_now_cycles(void) { return 0u; }

/* doa.c의 작업 공간 대역 (MCU에서는 doa.c의 블록 FFT 버퍼 8 KB) */
static float s_scratch[2048];
float *doa_scratch(void) { return s_scratch; }

int main(void)
{
#ifdef _WIN32
	_setmode(_fileno(stdin), _O_BINARY);
#endif
	static int16_t pcm[HARM_FRAME];
	uint32_t seq;
	uint8_t restart, defer;
	harm_result_t r;
	harm_init();
	while (fread(&seq, 4, 1, stdin) == 1 && fread(&restart, 1, 1, stdin) == 1 && fread(&defer, 1, 1, stdin) == 1) {
		if (fread(pcm, 2, HARM_FRAME, stdin) != HARM_FRAME)
			return 1;
		if (harm_push(pcm, seq, restart != 0u, defer != 0u, &r))
			printf("%u,%u,%.9g,%.9g,%.9g,%u,%u\n", r.s0, r.n, r.score, r.f0, r.rms_db, r.frames, r.flags);
	}
	return 0;
}
