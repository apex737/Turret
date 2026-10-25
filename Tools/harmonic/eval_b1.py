"""Step8b B1 평가: B0 점수 + 거름 3개(정수배 정확도 · 지속 · 기본음 출렁임). B0와 같은 창, 같은 곡선으로 비교.

    python harmonic/eval_b1.py      → reports/step8b/b1_report.md, b1_curve.png, 창별 특징 DataSet/_cache/b1_feats.npz
    python harmonic/eval_b1.py --cached      (특징을 다시 계산하지 않고 캐시로 평가만)

특징은 harmonic/features.py. 창 목록·신호 읽기는 eval_b0와 같다 (eval_b0의 함수를 그대로 쓰고 점수 함수만 바꿔 끼운다).
거름 경계값: fold k는 나머지 fold의 공개 원음 드론 창 95%가 통과하는 값 (정수배 어긋남 ≤ 95번째 백분위, 지속 ≥ 5번째, 출렁임 ≤ 95번째).
점수 = 거름을 모두 통과하면 B0 점수 S, 아니면 0. 곡선은 이 점수의 기준값을 바꿔 가며 그린다 (curve_b0와 같은 방식).
비교 설정: B0(거름 없음), B1-정수배(정수배 거름만), B1-시간(지속·출렁임 거름만), B1(셋 다).
"""
import argparse, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, os.path.join(HERE, "..", "ml"))
import harmonic.eval_b0 as e
import harmonic.features as hf
import harmonic.curve_b0 as cb

FEATS = os.path.join(e.CACHE, "b1_feats.npz")
NF = len(hf.NAMES)
SETS = {"B0": (), "B1-정수배": ("dev",), "B1-시간": ("persist", "glide"), "B1": ("dev", "persist", "glide")}
FOLD_OF = {"Fp": 1}


def feats_of(x12, ts):
    F = np.zeros((len(ts), NF)); R = np.zeros(len(ts))
    for i, t in enumerate(ts):
        s = int(round(t * e.FS)); w = x12[s:s + e.FS]
        if len(w) < e.FS:
            w = np.pad(w, (0, e.FS - len(w)))
        F[i] = hf.features(w)
        R[i] = 10 * np.log10(np.mean((w - w.mean()) ** 2) + 1e-20)
    return F, R


def compute():
    e.scores_of = feats_of; e.CANDS = [None] * NF           # eval_b0의 창 읽기를 그대로 쓰고 점수만 특징으로
    fl = e.floor_db(); P = e.public(); D, off, V, I = e.device(fl)
    np.savez_compressed(FEATS, fl=fl, off=off, **{f"P_{k}": v for k, v in P.items()}, **{f"D_{k}": v for k, v in D.items()},
                        **{f"V_{k}": v for k, v in V.items()}, **{f"I_{k}": v for k, v in I.items()})


def load():
    z = np.load(FEATS, allow_pickle=False)
    pick = lambda pre: {k[len(pre):]: z[k] for k in z.files if k.startswith(pre)}
    return pick("P_"), pick("D_"), pick("V_"), pick("I_"), float(z["off"])


def col(F, name):
    return F[:, hf.NAMES.index(name)]


def gates(P):
    """fold k마다 나머지 fold 드론 창 95% 통과 경계"""
    g = {}
    for k in range(1, 6):
        m = (P["label"] == 1) & (P["fold"] != k)
        dev = col(P["S"], "dev_hz")[m]
        g[k] = dict(dev=np.quantile(dev, 0.95), persist=np.quantile(col(P["S"], "persist")[m], 0.05),
                    glide=np.quantile(col(P["S"], "glide")[m], 0.95))
    return g


def score(F, folds, g, use):
    ok = np.ones(len(F), bool)
    for i, k in enumerate(folds):
        gk = g[int(k)]
        if "dev" in use: ok[i] &= F[i, 2] <= gk["dev"]
        if "persist" in use: ok[i] &= F[i, 3] >= gk["persist"]
        if "glide" in use: ok[i] &= F[i, 4] <= gk["glide"]
    return np.where(ok, F[:, 0], 0.0)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(); ap.add_argument("--cached", action="store_true"); a = ap.parse_args()
    if not a.cached or not os.path.exists(FEATS):
        compute()
    P, D, V, I, off = load()
    g = gates(P)
    ph = (D["t"] - off) % 20.0
    dm = (D["kind"] == "test") & (D["aircraft"] == "Fp") & (ph >= 1.5) & (ph + 1.0 <= 18.5)
    thr = np.r_[np.linspace(0, 30, 121), np.linspace(30, 80, 51)]
    R = {}
    for name, use in SETS.items():
        sp = score(P["S"], P["fold"], g, use)
        pub = cb.public_curve(sp, P["label"], P["fold"], P["row"], P["t"], P["event"], thr)
        sd = score(D["S"][dm], np.ones(dm.sum()), g, use); gd = D["gate"][dm]
        sv = score(V["S"], V["fold"], g, use); gv = V["gate"]
        dev = np.array([(np.mean((sv >= th) & gv), np.mean((sd >= th) & gd)) for th in thr])
        bg = {}
        for c in ("device_quiet", "device_fan", "device_ac"):
            m = D["category"] == c
            bg[c] = [np.mean([np.mean((score(D["S"][m], np.full(m.sum(), k), g, use) >= th) & D["gate"][m]) for k in range(1, 6)]) for th in thr]
        R[name] = dict(pub=pub, dev=dev, bg=bg,
                       pass_drone=np.mean(score(P["S"][P["label"] == 1], P["fold"][P["label"] == 1], g, use) > 0),
                       pass_esc=np.mean(score(P["S"][P["label"] == 0], P["fold"][P["label"] == 0], g, use) > 0),
                       pass_dev_fpv=np.mean(sd > 0), pass_dev_esc=np.mean(sv > 0))
    best = lambda c, xc, yc, lim: (f"{c[c[:, xc] <= lim, yc].max():.2f}" if (c[:, xc] <= lim).any() else "-")
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.3))
    eng = {"B0": "B0", "B1-정수배": "B1 harmonicity only", "B1-시간": "B1 persistence+glide only", "B1": "B1 all three"}
    for name in SETS:
        ax[0].plot(R[name]["pub"][:, 0], R[name]["pub"][:, 1], label=eng[name])
        ax[1].plot(R[name]["dev"][:, 0] * 100, R[name]["dev"][:, 1], label=eng[name])
    ax[0].set_xscale("symlog", linthresh=1); ax[0].set_xlim(0, 700); ax[0].set_ylim(0, 1.02)
    ax[0].set_xlabel("False alarms per hour (ESC-50, public, 2-of-3 clips)"); ax[0].set_ylabel("FPV window recall"); ax[0].set_title("Public recordings")
    ax[1].set_xlim(0, 70); ax[1].set_ylim(0, 1.02)
    ax[1].set_xlabel("Device path: ESC-50 window false-positive rate (%)"); ax[1].set_ylabel("Device path FPV window recall"); ax[1].set_title("Device path (+ quiet-window rule)")
    for x in ax: x.grid(alpha=0.3); x.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(os.path.join(e.OUT, "b1_curve.png"), dpi=110)
    md = ["# Step8b B1 — B0 + 거름 3개 (정수배 정확도 · 지속 · 기본음 출렁임)", "",
          "> `Tools/harmonic/eval_b1.py`가 만든 파일. 수치만 적는다 (판정은 Steps/Step8b.md). 그림: [b1_curve.png](b1_curve.png)",
          "> 거름 경계 = fold마다 나머지 fold 공개 원음 드론 창 95%가 통과하는 값. 곡선은 점수 기준값을 다섯 fold에 똑같이 쓰고 바꿔 가며 그린 진단.", "",
          "## 거름 경계값 (fold 1 ~ 5)", "", "| 특징 | " + " | ".join(f"fold {k}" for k in range(1, 6)) + " |", "|---|" + "---|" * 5]
    for key, unit in (("dev", " Hz"), ("persist", ""), ("glide", "")):
        md.append(f"| {key} | " + " | ".join(f"{g[k][key]:.2f}{unit}" for k in range(1, 6)) + " |")
    md += ["", "## 거름 통과 비율", "", "| 설정 | 공개 드론 창 | 공개 ESC-50 창 | 장치 FPV 창 | 장치 ESC-50 창 |", "|---|---|---|---|---|"]
    for name in SETS:
        r = R[name]
        md.append(f"| {name} | {r['pass_drone']:.0%} | {r['pass_esc']:.0%} | {r['pass_dev_fpv']:.0%} | {r['pass_dev_esc']:.0%} |")
    md += ["", "## 공개 원음: 오탐/시간 예산 안 최대 FPV 창 재현율 · 사건 검출률 (v3m: 0.25 · 0.81 / 0.43 · 0.81 / 0.71 · 0.95)", "",
           "| 설정 | ≤ 1회/시간 | ≤ 10회/시간 | ≤ 50회/시간 | ≤ 200회/시간 |", "|---|---|---|---|---|"]
    for name in SETS:
        c = R[name]["pub"]
        md.append(f"| {name} | " + " | ".join(f"{best(c, 0, 1, l)} · {best(c, 0, 2, l)}" for l in (1, 10, 50, 200)) + " |")
    md += ["", "## 장치 경로: 창 오탐률 예산 안 최대 FPV 창 재현율 (v3m: 0.00 / 0.04 / 0.11 / 0.25, v3m + 조용한 창 규칙: 0.07 / 0.21 / 0.34 / 0.41)", "",
           "| 설정 | ≤ 1% | ≤ 5% | ≤ 10% | ≤ 20% |", "|---|---|---|---|---|"]
    for name in SETS:
        c = R[name]["dev"]
        md.append(f"| {name} | " + " | ".join(best(c, 0, 1, l) for l in (0.01, 0.05, 0.10, 0.20)) + " |")
    md += ["", "## 배경 창 오탐률 (장치 경로 FPV 재현율 0.5가 되는 기준값에서)", "", "| 설정 | 기준값 | 조용함 | 선풍기 | 에어컨 |", "|---|---|---|---|---|"]
    for name in SETS:
        d = R[name]["dev"]; ok = np.flatnonzero(d[:, 1] >= 0.5)
        if len(ok):
            i = ok[-1]
            md.append(f"| {name} | {thr[i]:.1f} | " + " | ".join(f"{R[name]['bg'][c][i]:.1%}" for c in ("device_quiet", "device_fan", "device_ac")) + " |")
        else:
            md.append(f"| {name} | — (0.5에 못 미침) | - | - | - |")
    md.append("")
    p = os.path.join(e.OUT, "b1_report.md"); open(p, "w", encoding="utf-8").write("\n".join(md))
    print("\n".join(md)); print(f"→ {p}")


if __name__ == "__main__":
    main()
