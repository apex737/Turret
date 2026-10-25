"""진단 (D8-7 A): 장치 경로 오탐이 보드 자체 잡음 때문인가.

    python ml/diag_v5_noise.py      (embed_v0~v3, v5 결과 사용) → reports/step8/diag_v5_noise.md

가설: 분류기는 창마다 RMS를 −30 dBFS로 맞춘 뒤 본다. 작은 소리 창을 키우면 남는 것은 대부분 보드 자체 잡음
      (프레임 동기 빗이 340 ~ 490 Hz에 남음, MAX4466 자체 잡음)이고, 이것을 드론으로 본다.
확인 두 가지 (채택 운용점과 같은 학습·문턱, fold마다)
  1. 소리 없이 보드 잡음만 있는 창 (quiet_10min, fan_10min, doa_bg·bg2 에어컨; 학습에 안 씀)이 문턱을 넘는 비율
  2. 장치 경로 ESC-50 시험 창의 오탐률을 창 레벨(보드 잡음 바닥 대비 dB)별로 → 가설이 맞으면 작은 창일수록 오탐이 많다
  3. 같은 날 같은 녹음 안에서: 재생 전·후 (스피커 쉼) 창 대 ESC 클립의 디지털 무음을 재생 중인 창
     → 무음 재생 중에만 오탐이 많으면 원인은 보드 잡음이 아니라 재생 경로(노트북 앰프·스피커·USB 접지)다
"""
import os, sys
import numpy as np
import soundfile as sf
from joblib import Parallel, delayed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import train_v0 as t0, train_v1 as t1, train_v2 as t2, train_v5 as t5

DUMPS = os.path.join(HERE, "..", "dumps", "stream")
BINS = [(-99, 3), (3, 10), (10, 20), (20, 99)]          # 보드 잡음 바닥 대비 [dB]


def floor_db():
    """quiet_10min MIC1의 0.5 s RMS 중앙값 = 보드 잡음 바닥"""
    x, fs = sf.read(os.path.join(DUMPS, "quiet_10min", "seg_000.wav"), dtype="float64")
    x = x[:, 0] - x[:, 0].mean(); h = int(0.5 * fs); n = len(x) // h
    return float(np.median(10 * np.log10(np.mean(x[:n * h].reshape(n, h) ** 2, axis=1))))


def window_db(V):
    """장치 경로 창마다 MIC1 RMS [dBFS] (창 = 녹음 시각 t부터 1 s)"""
    out = np.zeros(len(V["t"]))
    for part in np.unique(V["part"]):
        x, fs = sf.read(os.path.join(DUMPS, f"devpath_{part}", "seg_000.wav"), dtype="float64")
        x = x[:, 0] - x[:, 0].mean()
        for i in np.flatnonzero(V["part"] == part):
            s = int(V["t"][i] * fs)
            out[i] = 10 * np.log10(np.mean(x[s:s + int(fs)] ** 2) + 1e-20)
    return out


def idle_and_silence(V):
    """재생 전·후 창 임베딩 + ESC 시험 창 중 재생 파일이 디지털 무음인 창 표시"""
    import embed_v0 as e0, embed_v1 as e1, embed_v5 as e5
    from audio.to_listen import load
    emb, E, n_idle = e1.Embedder(), [], 0
    silent = np.zeros(len(V["t"]), bool)
    for part in np.unique(V["part"]):
        x12, valid, fs12 = e5.recording(f"devpath_{part}")
        off, drift, _, _ = e5.align(x12.mean(axis=1), fs12, part)
        fs, p = load(os.path.join(e5.PLAY, f"30_devpath_{part}.wav"), 1)
        end = off + len(p) / fs * (1 + drift)
        y = e0.rs(x12[:, 0] - x12[:, 0].mean(), fs12, e0.FS_M); W = e0.windows(y)
        t = np.arange(len(W)) * e0.HOP / e0.FS_M
        idle = ((t + 1.0 <= off - 0.5) | (t >= end + 0.5)) & (t + 1.0 <= len(x12) / fs12)
        E.append(emb(W[idle])[0]); n_idle += idle.sum()
        for i in np.flatnonzero((V["part"] == part) & (V["role"] == "test")):
            tp = (V["t"][i] - off) / (1 + drift); a = int(tp * fs)
            silent[i] = np.max(np.abs(p[max(a, 0):a + fs])) < 1e-4
    print(f"재생 전·후 창 {n_idle}, 무음 재생 중 ESC 창 {silent.sum()}")
    return np.concatenate(E), silent


def run(O, A, D, P, H, V, off, cfg, k, idle_emb=None):
    t0.FPR_TARGET = t5.FPR
    pos, neg = t5.CONFIGS[cfg]
    X, y, g = [H["emb"]], [np.zeros(len(H["emb"]), int)], [H["group"]]
    for use, lab in ((pos, 1), (neg, 0)):
        if use:
            m = (V["role"] == "train") & (V["label"] == lab)
            X.append(V["emb"][m]); y.append(np.full(m.sum(), lab)); g.append(V["group"][m])
    res = t2.run_fold(O, A, D, P, (("fpv", "mix"), (), False), k, off, (np.concatenate(X), np.concatenate(y), np.concatenate(g)))
    clf, thr = res["clf"], res["thr"]
    noise = {c: clf.predict_proba(D["emb"][(D["kind"] == "neg") & (D["category"] == c)])[:, 1] >= thr
             for c in ("device_quiet", "device_fan", "device_ac")}
    m = (V["role"] == "test") & (V["fold"] == k)
    esc = (np.flatnonzero(m), clf.predict_proba(V["emb"][m])[:, 1] >= thr)
    idle = clf.predict_proba(idle_emb)[:, 1] >= thr if idle_emb is not None else None
    return cfg, k, noise, esc, idle


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    O, A, D, off, _ = t1.load(); P = t2.load_fpv(); V = t5.load_dev()
    z = np.load(os.path.join(t1.CACHE, "emb_v3_neg.npz"), allow_pickle=False); H = {k: z[k] for k in ("emb", "cls", "group")}
    fl = floor_db(); wdb = window_db(V) - fl
    idle_emb, silent = idle_and_silence(V)
    out = Parallel(n_jobs=-1)(delayed(run)(O, A, D, P, H, V, off, c, k, idle_emb) for c in ("v3m", "v5") for k in range(1, 6))
    md = ["# 진단 — 장치 경로 오탐과 보드 자체 잡음", "",
          "> `Tools/ml/diag_v5_noise.py`가 만든 파일. 수치만 적는다. 학습·문턱은 채택 운용점과 같다 (창 오탐 0.5%, fold마다).",
          f"> 보드 잡음 바닥 = quiet_10min MIC1 0.5 s RMS 중앙값 {fl:.1f} dBFS. 창 레벨은 이 바닥 대비 dB.", "",
          "## 1. 보드 잡음만 있는 창이 문턱을 넘는 비율 (5 fold 평균, 학습에 안 쓴 창)", "",
          "| 설정 | 조용함 (quiet_10min) | 선풍기 (fan_10min) | 에어컨 (doa_bg) |", "|---|---|---|---|"]
    for cfg in ("v3m", "v5"):
        r = [o for o in out if o[0] == cfg]
        md.append(f"| {cfg} | " + " | ".join(f"{np.mean([o[2][c].mean() for o in r]):.1%}" for c in ("device_quiet", "device_fan", "device_ac")) + " |")
    md += ["", "## 2. 장치 경로 ESC-50 시험 창의 오탐률, 창 레벨별 (5 fold 합)", "",
           "| 설정 | " + " | ".join(f"바닥 +{a} ~ +{b} dB" if a > -99 and b < 99 else (f"바닥 + {b} dB 미만" if a == -99 else f"바닥 + {a} dB 이상") for a, b in BINS) + " |",
           "|---|" + "---|" * len(BINS)]
    for cfg in ("v3m", "v5"):
        idx = np.concatenate([o[3][0] for o in out if o[0] == cfg]); fp = np.concatenate([o[3][1] for o in out if o[0] == cfg])
        cells = []
        for a, b in BINS:
            m = (wdb[idx] >= a) & (wdb[idx] < b)
            cells.append(f"{fp[m].mean():.1%} ({m.sum()}창)" if m.any() else "-")
        md.append(f"| {cfg} | " + " | ".join(cells) + " |")
    md += ["", "## 3. 같은 녹음 안에서: 스피커가 쉴 때 대 디지털 무음을 재생 중일 때 (오탐률)", "",
           "| 설정 | 재생 전·후 창 (5 fold 평균) | 무음 재생 중인 ESC 창 (5 fold 합) | 소리가 있는 ESC 창 (5 fold 합) |", "|---|---|---|---|"]
    for cfg in ("v3m", "v5"):
        r = [o for o in out if o[0] == cfg]
        idx = np.concatenate([o[3][0] for o in r]); fp = np.concatenate([o[3][1] for o in r])
        md.append(f"| {cfg} | {np.mean([o[4].mean() for o in r]):.1%} ({len(r[0][4])}창) | {fp[silent[idx]].mean():.1%} ({silent[idx].sum()}창) | "
                  f"{fp[~silent[idx]].mean():.1%} ({(~silent[idx]).sum()}창) |")
    md.append("")
    p = os.path.join(t1.OUT, "diag_v5_noise.md")
    open(p, "w", encoding="utf-8").write("\n".join(md))
    print("\n".join(md[3:])); print(f"→ {p}")


if __name__ == "__main__":
    main()
