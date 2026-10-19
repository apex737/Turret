"""Step7 합성 시험: 정답 방위를 아는 3채널 신호를 만들어 doa_stream.py(D0)의 오차·유효율을 잰다. 보드 없이 설정을 고르는 용도.

    python doa/eval_doa_synth.py                  # SNR 단계별 기본 설정 + 설정 하나씩 바꾸기
    python doa/eval_doa_synth.py --quick          # 각도·원음을 줄여 빠르게

만드는 법
  드론 원음(DataSet/_playback/11~15, 48 kHz) → 장치와 같은 FIR·↓4 (12.5 kHz)
  → 방위 θ, 고도 φ의 평면파로 마이크별 분수 지연 (주파수 영역 위상 회전, 대역 제한 신호라 정확)
  → 실제 장치 잡음(Tools/dumps/stream/quiet_10min, 세 채널 동시 녹음이라 공통 주변음·보드 간섭 포함)을 SNR에 맞춰 더함
SNR: 300–3000 Hz 대역 전력비, 세 채널 평균.
배경 빼기(D1): quiet_10min 앞 절반의 60 s로 배경 교차 스펙트럼을 만들고, 시험 잡음은 뒤 절반에서 뽑는다 (같은 구간을 쓰지 않음).
"""
import argparse, os, sys, time
from math import gcd
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly, lfilter, welch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, ".."))
import gcc_phat as g
import doa_stream as ds
ds.DELAY_US = np.zeros(3)                                # 합성 신호는 채널 지연이 없다
import preproc.frontend as fe

PLAY = os.path.join(HERE, "..", "..", "DataSet", "_playback")
NOISE = os.path.join(HERE, "..", "dumps", "stream", "quiet_10min", "seg_000.wav")
SOURCES = ["11_fpv_ev1", "12_fpv_ev2", "13_fpv_ev3", "14_mini3pro_hover", "15_air3"]
FS = ds.FS_NOM


def to_device(path):
    x, fs = sf.read(path, dtype="float64")
    x = x if x.ndim == 1 else x[:, 0]
    k = gcd(int(fs), int(fe.CFG["fs_in"]))
    x50 = resample_poly(x, int(fe.CFG["fs_in"]) // k, int(fs) // k)
    return lfilter(fe.B, [1.0], x50)[::fe.M]


def delayed(src, az, el, pos):
    """평면파: 마이크 i 도착 시각 = −p_i·u / c. 주파수 영역 위상 회전으로 분수 지연."""
    u = np.array([np.cos(np.radians(az)) * np.cos(np.radians(el)), np.sin(np.radians(az)) * np.cos(np.radians(el))])
    n = len(src); nfft = 1 << int(np.ceil(np.log2(n + 64)))
    S = np.fft.rfft(src, nfft); f = np.fft.rfftfreq(nfft, 1 / FS)
    return np.array([np.fft.irfft(S * np.exp(-2j * np.pi * f * (-(p @ u) / g.SOUND_SPEED)), nfft)[:n] for p in pos])


def band_power(x):
    f, P = welch(x, FS, nperseg=1024, axis=-1)
    m = (f >= 300) & (f <= 3000)
    return P[..., m].sum(axis=-1)


def trial_set(srcs, noise, a, snr, angles, el, rng, pos, bg0=None):
    errs, valid = [], []
    for name, src in srcs:
        for az in angles:
            x = delayed(src, az, el, pos)
            o = rng.integers(0, noise.shape[1] - x.shape[1])
            nz = noise[:, o:o + x.shape[1]]
            k = np.sqrt(band_power(x).mean() / band_power(nz).mean() / 10 ** (snr / 10))
            bg = None if bg0 is None else [k ** 2 * R for R in bg0]       # 시험 잡음과 같은 배율의 배경
            res = ds.run(x + k * nz, FS, a, bg=bg)
            v = np.array([r["valid"] for r in res])
            valid += list(v)
            errs += list(ds.ang_err([r["angle"] for r, ok in zip(res, v) if ok], az))
    e = np.array(errs)
    return (np.median(e) if len(e) else np.nan, np.percentile(e, 95) if len(e) else np.nan, np.mean(valid))


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--seconds", type=float, default=8.0, help="원음마다 쓰는 길이 [s]")
    ds.add_args(ap)
    a = ap.parse_args()
    pos, d = ds.positions()
    rng = np.random.default_rng(0)
    srcs = [(s, to_device(os.path.join(PLAY, s + ".wav"))) for s in (SOURCES[:2] if a.quick else SOURCES)]
    n = int(a.seconds * FS)
    srcs = [(s, x[np.argmax(np.convolve(x ** 2, np.ones(n), "valid")[::1000]) * 1000:][:n]) for s, x in srcs]   # 가장 큰 구간
    noise = sf.read(NOISE, dtype="float64")[0].T
    noise -= noise.mean(axis=1, keepdims=True)
    half = noise.shape[1] // 2
    bg0 = ds.background(noise[:, :half], FS, a)
    noise = noise[:, half:]
    angles = np.arange(0, 360, 45 if a.quick else 30)
    base = dict(obs=a.obs, block=a.block, band=list(a.band))
    print(f"원음 {len(srcs)}개 × 방위 {len(angles)}개 × {a.seconds:.0f} s, 간격 {d * 1000:.0f} mm, 잡음 = 장치 quiet_10min")
    print(f"기준 설정 {base}.  표: 유효 출력의 오차 중앙값 / p95, 유효율.  Step7 통과: ≤5° / ≤10°, ≥80%\n")

    def show(tag, snr, el=0.0, sub=False, **chg):
        b = argparse.Namespace(**{**vars(a), **chg})
        bgb = (bg0 if b.block == a.block else ds.background(sf.read(NOISE, dtype='float64')[0].T[:, :half], FS, b)) if sub else None
        t0 = time.time(); med, p95, vr = trial_set(srcs, noise, b, snr, angles, el, rng, pos, bgb)
        ok = med <= 5 and p95 <= 10 and vr >= 0.8
        print(f"  {tag:28s} SNR {snr:+3d} dB  오차 {med:5.1f}° / {p95:5.1f}°  유효 {vr * 100:5.1f}%  {'통과' if ok else '  - '}  ({time.time() - t0:.0f} s)")

    print("[1] SNR 단계: D0 (배경 빼기 없음) 대 D1 (배경 빼기)")
    for snr in (20, 10, 5, 0, -5):
        show("D0", snr)
        show("D1 배경 빼기", snr, sub=True)
    print("\n[2] D1에서 한 번에 하나씩 바꾸기 (SNR 5 dB)")
    for obs in (0.25, 1.0):
        show(f"관측 {obs} s", 5, sub=True, obs=obs)
    for band in ((300, 2000), (150, 3000), (300, 5000)):
        show(f"대역 {band[0]}–{band[1]} Hz", 5, sub=True, band=list(band))
    for block in (256, 1024):
        show(f"블록 {block}", 5, sub=True, block=block)
    print("\n[3] 고도각 (D1, SNR 10 dB) — 평면 배열이라 방위만 추정, norm = cos(고도)")
    for el in (30, 45, 60):
        show(f"고도 {el}°", 10, el=el, sub=True)


if __name__ == "__main__":
    main()
