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

/* MCU의 def.c 대역. preproc_reset()이 CMSIS 초기화에 실패하면 부른다 */
void error_handle(void) { fprintf(stderr, "error\n"); exit(1); }

/* 사용법: pre <frames>   (argv[1] = 처리할 프레임 수) */
int main(int argc, char **argv)
{
	if (argc < 2) { fprintf(stderr, "usage: pre <frames>\n"); return 2; }
	const int nf = atoi(argv[1]);             /* nf : 처리할 프레임 수. stdin에 이만큼(nf × 6144 B)이 있어야 한다 */
#ifdef _WIN32
	_setmode(_fileno(stdin), _O_BINARY);      /* 텍스트 모드면 \n이 \r\n으로 바뀐다 */
	_setmode(_fileno(stdout), _O_BINARY);
#endif
	/* in  : 프레임 하나의 50 kHz 원본 [채널 3][1024] (= PREPROC_CH × PREPROC_IN, MCU의 adc_get_frame 출력과 같은 모양)
	 * out : 그 프레임의 12.5 kHz PCM [채널 3][256]  (= PREPROC_CH × PREPROC_OUT)
	 * static: 스택 대신 정적 영역에 둔다 */
	static uint16_t in[3][1024];
	static int16_t out[3][256];
	preproc_reset();                          /* 부팅 직후 MCU와 같은 출발점: FIR 상태 0 */
	for (int f = 0; f < nf; f++) {
		if (fread(in, 2, 3 * 1024, stdin) != 3 * 1024) return 1;   /* 프레임이 모자람 = 입력 길이와 nf가 안 맞음 */
		preproc_run(in, out);                 /* 상태를 지우지 않고 다음 프레임으로 이어 간다. 클리핑 반환값은 여기서 쓰지 않음 */
		fwrite(out, 2, 3 * 256, stdout);
	}
	return 0;
}
