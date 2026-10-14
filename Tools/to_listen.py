"""공개 원음을 일반 플레이어로 들을 수 있는 wav로 바꾼다. (분석용 아님, 귀로 확인하는 용도)

    python to_listen.py in.wav [--ch 1] [--start 82 --dur 30] [--hp 100] [--out dir]

- 형식: 무엇이든(50 kHz float, 32-bit int 다채널 …) → 48 kHz, 16-bit, 모노
- 고역 통과(--hp): 바람 같은 저주파가 레벨을 차지해 드론 고조파가 묻히는 것을 막는다. 0이면 끔
- 레벨: RMS를 -20 dBFS로 맞추고, 피크는 -1 dBFS에서 자른다. 원래 레벨(dBFS)은 화면에 출력
"""
import argparse, os, warnings
from math import gcd
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfiltfilt, resample_poly

FS_OUT = 48000
db = lambda v: 20 * np.log10(v + 1e-20)


def load(path, ch):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")              # Salford 파일의 비표준 청크 경고
        fs, x = wavfile.read(path, mmap=True)
    x = np.asarray(x[:, ch - 1] if x.ndim > 1 else x)
    if x.dtype.kind in "iu":                          # 정수 PCM → [-1, 1)
        x = x.astype(np.float64) / float(2 ** (8 * x.dtype.itemsize - 1))
    return fs, x.astype(np.float64)


def convert(path, ch, start, dur, hp, out_dir):
    fs, x = load(path, ch)
    a = int(start * fs)
    x = x[a: a + int(dur * fs)] if dur else x[a:]
    x = x - x.mean()
    print(f"{os.path.basename(path)}  fs={fs}  ch{ch}  원래 레벨: rms {db(np.sqrt(np.mean(x**2))):.1f} dBFS, peak {db(np.abs(x).max()):.1f} dBFS")

    if hp > 0:
        x = sosfiltfilt(butter(4, hp, "highpass", fs=fs, output="sos"), x)
    if fs != FS_OUT:
        g = gcd(fs, FS_OUT)
        x = resample_poly(x, FS_OUT // g, fs // g)

    x *= 10 ** (-20 / 20) / (np.sqrt(np.mean(x**2)) + 1e-20)
    lim = 10 ** (-1 / 20)
    clipped = np.mean(np.abs(x) > lim)
    x = np.clip(x, -lim, lim)

    os.makedirs(out_dir, exist_ok=True)
    name = os.path.splitext(os.path.basename(path))[0] + f"_ch{ch}" + (f"_{start:g}s" if start else "") + ("" if hp <= 0 else f"_hp{hp:g}") + ".wav"
    wavfile.write(os.path.join(out_dir, name), FS_OUT, (x * 32767).astype(np.int16))
    print(f"  → {name}  (rms -20 dBFS로 맞춤, 잘린 샘플 {clipped * 100:.2f}%)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("wav", nargs="+")
    ap.add_argument("--ch", type=int, default=1, help="1부터 시작하는 채널 번호")
    ap.add_argument("--start", type=float, default=0.0, help="시작 [s]")
    ap.add_argument("--dur", type=float, default=0.0, help="길이 [s], 0이면 끝까지")
    ap.add_argument("--hp", type=float, default=100.0, help="고역 통과 [Hz], 0이면 끔")
    ap.add_argument("--out", default="listen")
    a = ap.parse_args()
    for p in a.wav:
        convert(p, a.ch, a.start, a.dur, a.hp, a.out)
