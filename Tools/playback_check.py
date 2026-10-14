"""Step5-3/5-4: 스피커로 튼 소리를 burst로 받은 녹음을 원본과 비교한다.

    python playback_check.py --pink pink_1m [--silence quiet] --tone tone_1m --drone fpv_ev1=11_fpv_ev1 air3=15_air3

  --pink    LABEL       핑크 잡음 녹음 → 재생 경로의 크기 응답 (채널별), -10 dB 대역
  --silence LABEL       무음 녹음 → 장치 잡음 바닥 (응답이 잡음에 묻히는 주파수를 표시)
  --tone    LABEL       550 Hz 단계 녹음 → burst별 기본음 레벨과 2·3·4배 고조파(dBc) → 재생 음량 상한
  --drone   LABEL=NAME  드론 원음 녹음 → 원본(DataSet/_playback/NAME.wav)과 고조파 SNR 프로파일 비교

녹음 폴더: Tools/dumps/step5/<LABEL>/b_*.npz (burst_rx.py가 저장). 그림: reports/step5/playback_*.png
"""
import argparse, glob, os, sys
import numpy as np
from scipy.io import wavfile
from scipy.signal import welch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import harmonic_survey as hs

HERE = os.path.dirname(__file__)
DUMPS = os.path.join(HERE, "dumps", "step5")
PLAY = os.path.join(HERE, "..", "DataSet", "_playback")
OUT = os.path.join(HERE, "..", "reports", "step5")
FS = 50000
FRANGE = {"fpv": (300, 1200), "mini3pro": (100, 800), "air3": (80, 600)}
db = lambda v: 10 * np.log10(np.asarray(v, dtype=float) + 1e-30)


def bursts(label):
    files = sorted(glob.glob(os.path.join(DUMPS, label, "b_*.npz")))
    if not files:
        sys.exit(f"녹음 없음: {os.path.join(DUMPS, label)}")
    out = []
    for f in files:
        d = np.load(f)["data"].astype(np.float64)
        out.append((d - d.mean(axis=1, keepdims=True)) / 2048.0)   # 12비트 → ±1
    return out


def psd_bursts(label):
    """burst마다 Welch PSD → 평균. [채널, 주파수]"""
    P = None
    for b in bursts(label):
        f, p = welch(b, FS, nperseg=2048, axis=1)
        P = p if P is None else P + p
    return f, P / len(bursts(label))


def check_pink(label, silence):
    f, Pr = psd_bursts(label)
    fs0, x = wavfile.read(os.path.join(PLAY, "01_pink_30s.wav"))
    fo, Po = welch(x.astype(np.float64) / 32768, fs0, nperseg=2048)
    Po = np.interp(f, fo, Po, right=np.nan)
    H = db(Pr / Po[None, :])
    ref = np.nanmedian(H[:, (f > 800) & (f < 1200)], axis=1, keepdims=True)
    H -= ref
    fig, ax = plt.subplots(figsize=(10, 5))
    for c in range(H.shape[0]):
        ax.semilogx(f[1:], H[c, 1:], label=f"ch{c + 1}")
    if silence:
        _, Pn = psd_bursts(silence)
        ax.semilogx(f[1:], db(Pn[0, 1:] / Pr[0, 1:]), c="gray", ls=":", label="silence / pink (ch1)")
    ax.axhline(-10, c="r", ls="--", lw=.8)
    ax.set_ylim(-50, 15); ax.set_xlim(30, 24000); ax.grid(alpha=.3, which="both"); ax.legend()
    ax.set_xlabel("Hz"); ax.set_ylabel("dB (1 kHz = 0)"); ax.set_title(f"speaker → MAX4466 response ({label})")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "playback_response.png"), dpi=90); plt.close(fig)
    with np.errstate(all="ignore"):
        import warnings; warnings.simplefilter("ignore")
        m = np.nanmean(H, axis=0)
    ok = np.where(m >= -10)[0]
    lo, hi = f[ok[ok > 0].min()], f[ok.max()]
    print(f"[응답] -10 dB 대역(채널 평균): {lo:.0f} ~ {hi:.0f} Hz.  채널 간 차이(0.2~5 kHz) 최대 "
          f"{np.nanmax(np.ptp(H[:, (f > 200) & (f < 5000)], axis=0)):.1f} dB")


def check_tone(label):
    rows = []
    for b in bursts(label):
        x = b[0] * np.hanning(b.shape[1])
        X = np.abs(np.fft.rfft(x)) ** 2
        df = FS / b.shape[1]
        amp = lambda f0: X[int(round(f0 / df)) - 2: int(round(f0 / df)) + 3].max()
        a1 = amp(550)
        rows.append((db(a1) - db((np.hanning(b.shape[1]).sum() / 2) ** 2) - 3.0,     # 기본음 dBFS (사인 기준)
                     *[db(amp(550 * h)) - db(a1) for h in (2, 3, 4)]))
    rows = np.array(sorted(rows))
    print("[왜곡] 기본음 dBFS → 2·3·4배 (dBc)")
    for r in rows[:: max(1, len(rows) // 12)]:
        print(f"   {r[0]:6.1f} dBFS → {r[1]:6.1f} {r[2]:6.1f} {r[3]:6.1f}" + ("   ← 왜곡" if max(r[1:]) > -40 else ""))
    clean = rows[np.max(rows[:, 1:], axis=1) <= -40]
    if len(clean):
        print(f"   고조파가 모두 -40 dBc 이하인 가장 큰 기본음: {clean[:, 0].max():.1f} dBFS (마이크 입력 기준)")


def profile_of(frames_iter, frange, fs):
    A, M = [], []
    for (P, floor, df) in frames_iter:
        snr = P / (floor + 1e-30)
        f0, sc = hs.track_f0(snr, df, *frange)
        on = sc >= hs.SCORE_ON
        if on.sum() == 0:
            continue
        a, m, _, _ = hs.harmonic_profile(snr, P, floor, f0, on, df, fs)
        A.append(a); M.append(m)
    hmax = max(a.shape[1] for a in A)
    pad = lambda a: np.pad(a, ((0, 0), (0, hmax - a.shape[1])), constant_values=np.nan)
    A = np.vstack([pad(a) for a in A]); M = np.vstack([pad(m) for m in M])
    return np.nanmedian(A, axis=0) - np.nanmedian(M, axis=0), len(A)


def contiguous(excess):
    last, miss = 0, 0
    for h, e in enumerate(excess):
        if e >= hs.USABLE_DB: last, miss = h + 1, 0
        else:
            miss += 1
            if miss >= 2 and last: break
    return last


def check_drone(label, name):
    frange = next(v for k, v in FRANGE.items() if k in name)
    fs0, x = wavfile.read(os.path.join(PLAY, name + ".wav"))
    x = x.astype(np.float64) / 32768
    _, _, P, floor, df = hs.frames(fs0, x)
    e_src, n_src = profile_of([(P, floor, df)], frange, fs0)
    def gen():
        for b in bursts(label):
            _, _, P, floor, df = hs.frames(FS, b[0])
            yield P, floor, df
    e_dev, n_dev = profile_of(gen(), frange, FS)
    hs_ = min(len(e_src), len(e_dev), 30)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(np.arange(1, hs_ + 1), e_src[:hs_], "o-", label=f"original ({name})")
    ax.plot(np.arange(1, hs_ + 1), e_dev[:hs_], "s-", label=f"device ({label}, ch1)")
    ax.axhline(hs.USABLE_DB, c="r", ls="--", lw=.8)
    ax.set_xlabel("harmonic order h"); ax.set_ylabel("SNR at h·f0 − SNR between [dB]"); ax.grid(alpha=.3); ax.legend()
    ax.set_title("harmonics: original vs speaker→MAX4466")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, f"playback_{label}.png"), dpi=90); plt.close(fig)
    print(f"[드론 {label}] 연속으로 쓸 만한 고조파: 원본 {contiguous(e_src)}개 → 장치 {contiguous(e_dev)}개 "
          f"(원본 프레임 {n_src}, 장치 burst {n_dev})")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--pink"); ap.add_argument("--silence"); ap.add_argument("--tone")
    ap.add_argument("--drone", nargs="*", default=[])
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if a.pink: check_pink(a.pink, a.silence)
    if a.tone: check_tone(a.tone)
    for spec in a.drone:
        label, name = spec.split("=")
        check_drone(label, name)


if __name__ == "__main__":
    main()
