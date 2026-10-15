"""MCU 전처리(preproc.c)의 PC 기준 구현. config/frontend_config.json의 계수·규약을 그대로 따른다.

    pcm = preproc_reference(raw)      # raw: uint16 [ch, N] (50 kHz, N은 4의 배수), 상태 0에서 시작 → int16 [ch, N/4]

규약: x = adc − 2048, y[k] = Σ b[j]·x[4k − j], pcm = sat16(rint(16·y))
"""
import json, os
import numpy as np
from scipy.signal import lfilter

CFG = json.load(open(os.path.join(os.path.dirname(__file__), "..", "..", "config", "frontend_config.json"), encoding="utf-8"))
B = np.array(CFG["coeffs"], dtype=np.float64)
M = CFG["decim"]
FS_OUT = CFG["fs_out"]
TRANSIENT_OUT = (CFG["num_taps"] + M - 1) // M     # 상태 0에서 시작한 뒤 과도 구간 (출력 샘플)
GROUP_DELAY_OUT = CFG["group_delay_in"] / M         # 12.5 kHz 샘플 단위 지연 (37/4 = 9.25)


def preproc_reference(raw):
    x = np.asarray(raw, dtype=np.float64) - CFG["adc_center"]
    y = lfilter(B, [1.0], x, axis=-1)[..., ::M]                # CMSIS 출력 위상: y[k]는 x[4k]까지의 입력으로 계산 (호스트 실측)
    return np.clip(np.rint(y * CFG["pcm_scale"]), -32768, 32767).astype(np.int16)
