"""Step5-1: 공개 원음의 고조파 구조를 잰다 → f_use(쓸 대역 상한) 결정 근거.

    python harmonic_survey.py            # DataSet/ 아래 정해진 그룹 전체, 결과는 reports/step5/

프레임마다 (1) 고조파 점수로 f0를 찾고 (2) 1번째부터 나이퀴스트까지 각 고조파 자리의 SNR을 잰다.
같은 탐색 폭으로 고조파 "사이"(h+0.5)·f0 자리의 SNR도 재서 기준으로 삼는다. 둘의 차이가 그 고조파가 실제로 있는지다.

출력 (그룹마다)
- f0 분포
- 고조파 차수별 SNR 중앙값 (고조파 자리 vs 사이 자리) → "쓸 만한" 마지막 고조파
- 선 에너지 누적 → 95% / 99% 주파수
- 선 폭 (1~5번째, -3 dB 폭)
"""
import os, sys, glob, warnings
import numpy as np
from scipy.io import wavfile
from scipy.signal import stft, medfilt
from scipy.ndimage import median_filter
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.join(os.path.dirname(__file__), "..")
DATA = os.path.join(ROOT, "DataSet")
OUT = os.path.join(ROOT, "reports", "step5")

NFFT = 8192            # 50 kHz에서 164 ms, Δf 6.1 Hz (burst 캡처 길이와 같음)
H_DET, CAP = 10, 10.0  # f0 탐색용 빗살 수, 빗살당 점수 상한
SCORE_ON = 45.0        # 잡음만 있을 때 최고 점수는 30~40 (f0_probe.py와 같은 기준)
F_TOP = 20000.0        # 고조파를 잴 상한 [Hz]
USABLE_DB = 6.0        # 고조파 자리 SNR이 사이 자리보다 이만큼 높으면 "있음"
H_MAX = 80             # 잴 최대 차수

db = lambda v: 10 * np.log10(np.asarray(v, dtype=float) + 1e-30)

# 그룹: (이름, 파일 패턴 또는 (파일, 채널, 구간) 목록, f0 탐색 범위)
SAL = os.path.join(DATA, "Salford DroneNoise")
WS = os.path.join(DATA, "Western Sydney DJI Air 3", "device_1_nosync.wav")
GROUPS = [
    ("Salford DJI FPV flyover",      os.path.join(SAL, "Ed_Fp_10_F15_*.wav"), (300, 1200)),
    ("Salford Mini 3 Pro flyover",   os.path.join(SAL, "Ed_3p_10_F15_*.wav"), (100, 800)),
    ("Salford Mini 3 Pro hover",     os.path.join(SAL, "Ed_3p_10_H00_*.wav"), (100, 800)),
    ("Salford Matrice 300 flyover",  os.path.join(SAL, "Ed_M3_10_F15_*.wav"), (40, 600)),
    ("Salford Matrice 300 hover",    os.path.join(SAL, "Ed_M3_10_H00_*.wav"), (40, 600)),
    ("Salford Yuneec H520E flyover", os.path.join(SAL, "Ed_Yn_10_F15_*.wav"), (40, 600)),
    ("Salford Yuneec H520E hover",   os.path.join(SAL, "Ed_Yn_10_H00_*.wav"), (40, 600)),
    ("WS DJI Air 3 (ch1-5)",         [(WS, c, seg) for c in range(5) for seg in ((82, 112), (200, 240))], (80, 600)),
]


def load(path, ch=0, seg=None):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fs, x = wavfile.read(path, mmap=True)
    if x.ndim > 1:
        x = x[:, ch]
    if seg:
        x = x[int(seg[0] * fs): int(seg[1] * fs)]
    x = np.asarray(x, dtype=np.float64)
    return fs, x - x.mean()


def frames(fs, x):
    f, t, Z = stft(x, fs, window="hann", nperseg=NFFT, noverlap=NFFT * 3 // 4, boundary=None)
    P = (np.abs(Z) ** 2).T                                            # [프레임, bin]
    df = fs / NFFT
    # 잡음 바닥: 같은 프레임에서 이웃 200 Hz의 중앙값 (선은 좁아서 중앙값에 섞이지 않음). 중앙값 → 평균 환산 1/ln2
    floor = median_filter(P, size=(1, int(round(200 / df)) | 1), mode="nearest") / np.log(2)
    return f, t, P, floor, df


def track_f0(snr, df, fmin, fmax):
    pk = np.maximum(snr, np.maximum(np.roll(snr, 1, axis=1), np.roll(snr, -1, axis=1)))
    cand = np.arange(fmin, fmax + 0.25, 0.5)
    S = np.zeros((snr.shape[0], cand.size))
    for h in range(1, H_DET + 1):
        k = np.round(h * cand / df).astype(int)
        ok = k < snr.shape[1] - 1
        S[:, ok] += np.minimum(pk[:, k[ok]], CAP)
    smax = S.max(axis=1)
    low = np.argmax(S >= 0.9 * smax[:, None], axis=1)               # 두 배로 읽기 방지: 90% 이상 중 가장 낮은 후보
    f0 = cand[low]
    # 0.05 Hz 단위로 다듬기: 높은 차수에서 f0 오차가 h배로 커지므로
    fine = f0[:, None] + np.arange(-1.0, 1.0001, 0.05)[None, :]       # [프레임, 후보]
    rows = np.arange(len(f0))[:, None]
    sc = np.zeros(fine.shape)
    for h in range(1, H_DET + 1):
        k = np.clip(np.round(h * fine / df).astype(int), 0, snr.shape[1] - 1)
        sc += np.minimum(pk[rows, k], CAP)
    return fine[np.arange(len(f0)), sc.argmax(axis=1)], smax


def harmonic_profile(snr, P, floor, f0, on, df, fs):
    """차수 h마다 [고조파 자리 SNR, 사이 자리 SNR] (dB, on 프레임별), 선 에너지 스펙트럼, 선 폭."""
    from scipy.ndimage import maximum_filter1d
    idx = np.where(on)[0]
    ftop = min(F_TOP, fs / 2 - 200)
    hmax = min(H_MAX, int(ftop / f0[idx].min()))
    h = np.arange(1, hmax + 1)
    nb = snr.shape[1]
    F = f0[idx, None] * h[None, :]                                    # [on 프레임, 차수]
    valid = F <= ftop
    k = np.clip(np.round(F / df).astype(int), 1, nb - 2)
    km = np.clip(np.round((F + 0.5 * f0[idx, None]) / df).astype(int), 1, nb - 2)
    # 탐색 폭: 다듬은 f0 오차(±0.05 Hz)가 h배로 커지는 만큼. 폭별로 최대값 필터를 미리 만든다
    w = np.maximum(1, np.ceil(h * 0.05 / df).astype(int))
    at = np.full(F.shape, np.nan); mid = np.full(F.shape, np.nan)
    rows = np.arange(len(idx))[:, None]
    for wv in np.unique(w):
        cols = np.where(w == wv)[0]
        mx = maximum_filter1d(snr[idx], 2 * wv + 1, axis=1)
        at[:, cols] = db(mx[rows, k[:, cols]]); mid[:, cols] = db(mx[rows, km[:, cols]])
    at[~valid] = np.nan; mid[~valid] = np.nan
    # 선 에너지: 고조파 자리(±1칸)에서 바닥 위로 올라온 만큼
    ex = np.clip(P[idx] - floor[idx], 0, None)
    line_E = np.zeros(nb)
    for d in (-1, 0, 1):
        kk = np.clip(k + d, 0, nb - 1)
        np.add.at(line_E, kk[valid], ex[rows, kk][valid])
    # 선 폭 (1~5번째): 반값(-3 dB) 이상인 칸 수 × Δf
    widths = []
    off = np.arange(-6, 7)
    for hh in range(min(5, hmax)):
        seg = P[idx[:, None], np.clip(k[:, hh:hh + 1] + off[None, :], 0, nb - 1)]
        widths.append(list((seg >= seg.max(axis=1, keepdims=True) / 2).sum(axis=1) * df))
    return at, mid, line_E, widths


def analyze_group(name, src, frange):
    items = sorted(glob.glob(src)) if isinstance(src, str) else src
    items = [(p, 0, None) if isinstance(p, str) else p for p in items]
    all_f0, ats, mids, Es, W = [], [], [], None, [[] for _ in range(5)]
    fs_g = None; example = None
    for (p, ch, seg) in items:
        fs, x = load(p, ch, seg)
        f, t, P, floor, df = frames(fs, x)
        snr = P / (floor + 1e-30)
        f0, score = track_f0(snr, df, *frange)
        # 드론 프레임: 점수가 높고, f0가 앞뒤 프레임과 이어지는 것 (튀는 프레임 제외)
        on = (score >= SCORE_ON) & (np.abs(f0 - medfilt(f0, 7)) <= 0.03 * f0)
        if on.sum() < 5:
            continue
        at, mid, E, widths = harmonic_profile(snr, P, floor, f0, on, df, fs)
        all_f0.append(f0[on]); ats.append(at); mids.append(mid)
        Es = E if Es is None else Es[: len(E)] + E[: len(Es)]
        for h in range(len(widths)): W[h] += widths[h]
        fs_g, f_axis = fs, f
        if example is None or on.mean() > example[-1]:
            example = (p, ch, t, f, snr, f0, on, on.mean())
    if not ats:
        return None
    hmax = max(a.shape[1] for a in ats)
    pad = lambda a: np.pad(a, ((0, 0), (0, hmax - a.shape[1])), constant_values=np.nan)
    A = np.vstack([pad(a) for a in ats]); M = np.vstack([pad(m) for m in mids])
    f0c = np.concatenate(all_f0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        a_med = np.nanmedian(A, axis=0); m_med = np.nanmedian(M, axis=0)
    excess = a_med - m_med
    usable = np.where(excess >= USABLE_DB)[0]
    # 연달아 쓸 만한 마지막 차수 (중간에 2개 이상 연속으로 빠지면 거기서 끊음)
    last_contig = 0; miss = 0
    for h in range(hmax):
        if excess[h] >= USABLE_DB: last_contig = h + 1; miss = 0
        else:
            miss += 1
            if miss >= 2 and last_contig: break
    cum = np.cumsum(Es) / Es.sum()
    f95 = f_axis[np.searchsorted(cum, 0.95)]; f99 = f_axis[np.searchsorted(cum, 0.99)]
    f0m = np.median(f0c)
    res = dict(name=name, n_files=len(ats), n_frames=len(f0c), fs=fs_g,
               f0_p5=np.percentile(f0c, 5), f0_med=f0m, f0_p95=np.percentile(f0c, 95),
               h_last=last_contig, f_last=last_contig * f0m, h_any=(usable.max() + 1) if usable.size else 0,
               f95=f95, f99=f99, width=[np.median(w) if w else np.nan for w in W],
               a_med=a_med, m_med=m_med, cum=cum, f_axis=f_axis, f0c=f0c, example=example)
    return res


def plot(res):
    name = res["name"]; fn = name.replace(" ", "_").replace("(", "").replace(")", "")
    p, ch, t, f, snr, f0, on, _ = res["example"]
    fig, ax = plt.subplots(2, 2, figsize=(13, 8))
    kk = f <= 12000
    ax[0, 0].pcolormesh(t, f[kk], 10 * np.log10(snr[:, kk].T + 1e-9), vmin=0, vmax=25, cmap="magma", shading="auto")
    ax[0, 0].scatter(t[on], f0[on], s=4, c="cyan")
    ax[0, 0].set_title(f"{os.path.basename(p)} ch{ch + 1} — SNR (dB), f0 = cyan", fontsize=9)
    ax[0, 0].set_ylabel("Hz"); ax[0, 0].set_xlabel("s")
    h = np.arange(1, len(res["a_med"]) + 1)
    ax[0, 1].plot(h, res["a_med"], "o-", ms=3, label="at h·f0")
    ax[0, 1].plot(h, res["m_med"], "x-", ms=3, c="gray", label="between (h+0.5)·f0")
    ax[0, 1].axvline(res["h_last"] + 0.5, c="r", ls="--", label=f"last contiguous usable h={res['h_last']} (~{res['f_last']:.0f} Hz)")
    ax[0, 1].set_xlabel("harmonic order h"); ax[0, 1].set_ylabel("median SNR [dB]"); ax[0, 1].legend(fontsize=8); ax[0, 1].grid(alpha=.3)
    ax[0, 1].set_title("harmonic SNR profile (median over drone frames)", fontsize=9)
    ax[1, 0].hist(res["f0c"], bins=80, color="tab:blue"); ax[1, 0].set_xlabel("f0 [Hz]"); ax[1, 0].set_title(f"f0 distribution ({res['n_frames']} frames, {res['n_files']} files)", fontsize=9)
    ax[1, 1].plot(res["f_axis"][: len(res["cum"])], res["cum"]); ax[1, 1].axhline(.95, c="gray", ls=":"); ax[1, 1].axhline(.99, c="gray", ls=":")
    for v, s in ((res["f95"], "95%"), (res["f99"], "99%")):
        ax[1, 1].axvline(v, c="r", ls="--"); ax[1, 1].text(v, .5, f" {s} {v:.0f} Hz", fontsize=8)
    for v in (6250, 12500):
        ax[1, 1].axvline(v, c="k", lw=.8); ax[1, 1].text(v, .2, f" fs/2 @ ↓{50000 // (2 * v)}", fontsize=8)
    ax[1, 1].set_xlim(0, 15000); ax[1, 1].set_xlabel("Hz"); ax[1, 1].set_title("cumulative line energy", fontsize=9); ax[1, 1].grid(alpha=.3)
    fig.suptitle(name); fig.tight_layout(); fig.savefig(os.path.join(OUT, fn + ".png"), dpi=90); plt.close(fig)
    return fn + ".png"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for name, src, fr in GROUPS:
        r = analyze_group(name, src, fr)
        if r is None:
            print(f"{name}: 드론 프레임 부족, 건너뜀"); continue
        png = plot(r)
        w = ", ".join(f"{v:.0f}" for v in r["width"])
        print(f"{name}: files {r['n_files']}, frames {r['n_frames']}, f0 {r['f0_p5']:.0f}/{r['f0_med']:.0f}/{r['f0_p95']:.0f} Hz, "
              f"연속 고조파 {r['h_last']}개(~{r['f_last']:.0f} Hz), 마지막으로 보이는 차수 {r['h_any']}, "
              f"선 에너지 95% {r['f95']:.0f} Hz / 99% {r['f99']:.0f} Hz, 선 폭(h1-5) {w} Hz")
        rows.append((r, png))
    np.save(os.path.join(OUT, "summary.npy"), np.array([{k: v for k, v in r.items() if k not in ("example", "f0c", "cum", "f_axis")} for r, _ in rows], dtype=object))
