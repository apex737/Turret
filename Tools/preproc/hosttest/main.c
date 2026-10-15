/* MCU의 preproc.c + CMSIS arm_fir_decimate_f32를 PC에서 그대로 돌린다 (Tools/test_preproc_host.py가 빌드·실행).
 * stdin : uint16 [nf][3][1024] (50 kHz 프레임 연속)
 * stdout: int16  [nf][3][256]  (12.5 kHz PCM)
 * 상태 0에서 시작해 프레임 사이에 상태를 이어 간다 (MCU 연속 수음과 같음). */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdbool.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
#include "preproc.h"

void error_handle(void) { fprintf(stderr, "error\n"); exit(1); }

int main(int argc, char **argv)
{
	if (argc < 2) { fprintf(stderr, "usage: pre <frames>\n"); return 2; }
	const int nf = atoi(argv[1]);
#ifdef _WIN32
	_setmode(_fileno(stdin), _O_BINARY);      /* 텍스트 모드면 \n이 \r\n으로 바뀐다 */
	_setmode(_fileno(stdout), _O_BINARY);
#endif
	static uint16_t in[3][1024];
	static int16_t out[3][256];
	preproc_reset();
	for (int f = 0; f < nf; f++) {
		if (fread(in, 2, 3 * 1024, stdin) != 3 * 1024) return 1;
		preproc_run(in, out);
		fwrite(out, 2, 3 * 256, stdout);
	}
	return 0;
}
