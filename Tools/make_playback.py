"""Step5-3 재생 파일을 만든다 → DataSet/_playback/ (48 kHz, 16-bit, 모노)

    python make_playback.py

burst 캡처는 아무 시점에서나 164 ms를 자르므로, 시간 정렬이 필요 없는 신호만 쓴다.
  01_pink_30s        핑크 잡음 → 스피커+마이크 경로의 크기 응답 (녹음 PSD / 원본 PSD)
  02_tone550_steps   550 Hz(FPV f0 근처) 단일음, -36 ~ 0 dBFS를 6 dB씩 4 s → 음량별 고조파 왜곡
  1x_*               드론 원음 (100 Hz 고역 통과, RMS -20 dBFS) → 원본 대 장치 녹음의 고조파 비교
"""
import os
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfiltfilt, resample_poly
from to_listen import load

FS = 48000
ROOT = os.path.join(os.path.dirname(__file__), "..")
DATA = os.path.join(ROOT, "DataSet")
OUT = os.path.join(DATA, "_playback")
SAL = os.path.join(DATA, "Salford DroneNoise")

# (출력 이름, 원본, 채널, 구간[s])
DRONES = [
    ("11_fpv_ev1", os.path.join(SAL, "Ed_Fp_10_F15_N_W_dw_ev1_M5.wav"), 0, None),
    ("12_fpv_ev2", os.path.join(SAL, "Ed_Fp_10_F15_N_W_dw_ev2_M5.wav"), 0, None),
    ("13_fpv_ev3", os.path.join(SAL, "Ed_Fp_10_F15_N_W_dw_ev3_M5.wav"), 0, None),
    ("14_mini3pro_hover", os.path.join(SAL, "Ed_3p_10_H00_N_C_nw_ev1_M1.wav"), 0, None),
    ("15_air3", os.path.join(DATA, "Western Sydney DJI Air 3", "device_1_nosync.wav"), 0, (82, 112)),
]


def write(name, x):
    x = np.clip(x, -1, 1)
    wavfile.write(os.path.join(OUT, name + ".wav"), FS, (x * 32767).astype(np.int16))
    print(f"{name}.wav  {len(x) / FS:.1f} s")


def pink(n, rng):
    """1/f 잡음: 백색 잡음의 스펙트럼을 1/sqrt(f)로 기울임."""
    X = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / FS)
    X[1:] /= np.sqrt(f[1:]); X[0] = 0
    x = np.fft.irfft(X, n)
    return x * 10 ** (-20 / 20) / np.sqrt(np.mean(x ** 2))


def main():
    os.makedirs(OUT, exist_ok=True)
    rng = np.random.default_rng(0)
    write("01_pink_30s", pink(30 * FS, rng))
    t = np.arange(4 * FS) / FS
    fade = np.minimum(1, np.minimum(t, t[::-1]) / 0.05)          # 클릭 방지 50 ms 페이드
    steps = [np.sqrt(2) * 10 ** (lv / 20) * np.sin(2 * np.pi * 550 * t) * fade for lv in range(-36, 1, 6)]
    write("02_tone550_steps", np.concatenate(steps))
    for name, path, ch, seg in DRONES:
        fs, x = load(path, ch + 1)
        if seg:
            x = x[int(seg[0] * fs): int(seg[1] * fs)]
        x = sosfiltfilt(butter(4, 100, "highpass", fs=fs, output="sos"), x - x.mean())
        if fs != FS:
            from math import gcd
            g = gcd(fs, FS); x = resample_poly(x, FS // g, fs // g)
        x *= 10 ** (-20 / 20) / np.sqrt(np.mean(x ** 2))
        write(name, np.clip(x, -10 ** (-1 / 20), 10 ** (-1 / 20)))


if __name__ == "__main__":
    main()
