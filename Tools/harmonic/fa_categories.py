"""Step8b: B0가 어떤 비드론 범주에서 오탐하는가 (공개 ESC-50, 장치 경로 ESC-50). 거를 특징을 고르기 위한 집계.

    python harmonic/fa_categories.py      (eval_b0.py의 DataSet/_cache/b0_scores.npz 사용) → reports/step8b/b0_fa_categories.md

기준 점수는 eval_b0와 같다 (fold k = 나머지 fold 드론 창 재현율 0.9, 기본음 40 ~ 700 Hz).
  공개: 범주마다 클립 오탐률 (클립 안에서 연속 3창 중 2창), 창 오탐률, 점수 중앙값
  장치 경로: 범주마다 창 오탐률 (조용한 창 규칙 포함)
드론 창 점수 중앙값을 같이 적어, 어느 범주가 드론보다 점수가 높은지 본다.
"""
import os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, os.path.join(HERE, "..", "ml"))
import train_v0 as t0

ROOT = os.path.join(HERE, "..", "..")
CACHE = os.path.join(ROOT, "DataSet", "_cache")
OUT = os.path.join(ROOT, "reports", "step8b")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    z = np.load(os.path.join(CACHE, "b0_scores.npz"), allow_pickle=False)
    S, lab, fold, row, t, cat = (z[k] for k in ("P_S", "P_label", "P_fold", "P_row", "P_t", "P_category"))
    s = S[:, 0]
    thr = {k: np.quantile(s[(lab == 1) & (fold != k)], 0.1) for k in range(1, 6)}
    th_w = np.array([thr[int(f)] for f in fold]); hit = s >= th_w
    neg = lab == 0
    rows = {}
    for r in np.unique(row[neg]):
        m = np.flatnonzero(neg & (row == r)); m = m[np.argsort(t[m])]
        c = cat[m[0]]; e = rows.setdefault(c, [0, 0, [], []])
        e[0] += 1; e[1] += t0.two_of_three(hit[m]); e[2] += list(hit[m]); e[3] += list(s[m])
    drone_med = np.median(s[lab == 1])
    tab = sorted(((c, n, fa, np.mean(w), np.median(sc)) for c, (n, fa, w, sc) in rows.items()), key=lambda x: -x[2] / x[1])
    # 장치 경로 ESC: 범주는 emb_v5_dev에서 (eval_b0와 같은 순서: role == test)
    v = np.load(os.path.join(CACHE, "emb_v5_dev.npz"), allow_pickle=False)
    vcls = v["cls"][v["role"] == "test"]
    VS, VG, VF = z["V_S"][:, 0], z["V_gate"], z["V_fold"]
    vhit = np.array([(VS[i] >= thr[int(VF[i])]) and VG[i] for i in range(len(VS))])
    dev = sorted(((c, np.sum(vcls == c), np.mean(vhit[vcls == c]), np.median(VS[vcls == c])) for c in np.unique(vcls)), key=lambda x: -x[2])

    md = ["# Step8b B0 오탐 범주", "",
          "> `Tools/harmonic/fa_categories.py`가 만든 파일. 수치만 적는다. 기준 점수 = 나머지 fold 드론 창 재현율 0.9 (기본음 40 ~ 700 Hz).",
          f"> 드론 창(공개 원음) 점수 중앙값 {drone_med:.1f}. 기준 점수 fold 1 ~ 5: " + ", ".join(f"{thr[k]:.1f}" for k in range(1, 6)), "",
          "## 공개 ESC-50 — 클립 오탐률이 높은 순 (전체 50범주)", "",
          "| 범주 | 클립 수 | 오탐 클립 | 클립 오탐률 | 창 오탐률 | 점수 중앙값 |", "|---|---|---|---|---|---|"]
    for c, n, fa, w, med in tab:
        md.append(f"| {c} | {n} | {fa} | {fa / n:.0%} | {w:.0%} | {med:.1f} |")
    lo = [c for c, n, fa, w, med in tab if fa / n <= 0.2]
    md += ["", f"클립 오탐률 20% 이하 범주 ({len(lo)}개): " + ", ".join(lo), "",
           "## 장치 경로 ESC-50 — 창 오탐률이 높은 순 (조용한 창 규칙 포함)", "",
           "| 범주 | 창 수 | 창 오탐률 | 점수 중앙값 |", "|---|---|---|---|"]
    for c, n, w, med in dev:
        md.append(f"| {c} | {n} | {w:.0%} | {med:.1f} |")
    md.append("")
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, "b0_fa_categories.md"); open(p, "w", encoding="utf-8").write("\n".join(md))
    print("\n".join(md[:16])); print("..."); print(f"→ {p}")


if __name__ == "__main__":
    main()
