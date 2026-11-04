# Tools/.venv — Core/app/inc/harm_hann.h 생성: np.hanning(2048)의 앞 절반(대칭)을 float 상수표로
import os
import numpy as np

N = 2048
w = np.hanning(N)[:N // 2].astype(np.float32)
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "Core", "app", "inc", "harm_hann.h")
lines = ["/* 자동 생성: Tools/harmonic/gen_hann_table.py — np.hanning(2048)의 앞 1024개 (뒤 절반은 대칭). 손으로 고치지 않는다 */",
         "#ifndef INC_HARM_HANN_H_", "#define INC_HARM_HANN_H_", "static const float harm_hann[1024] = {"]
for i in range(0, N // 2, 8):
    lines.append("\t" + ", ".join(f"{v!r}f" if "e" in repr(float(v)) or "." in repr(float(v)) else f"{v}.0f" for v in map(float, w[i:i + 8])) + ",")
lines += ["};", "#endif", ""]
open(out, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
print("wrote", os.path.normpath(out))
