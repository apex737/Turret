"""진단: 문턱을 바꿔 가며 FPV 창 재현율 대 오탐/시간 곡선 (직선 대 MLP, v2·v3m 데이터). 시험 데이터로 문턱을 고르는 것이 아니라
분류기 자체가 나은지(곡선이 위에 있는지), 문턱 위치만 옮겨졌는지를 가르는 용도.

    python ml/diag_v4_curve.py      → reports/step8/v4_curve.png, 표 출력
오탐/시간: v0과 같은 규칙 (ESC-50 시험 클립에서 연속 3창 중 2창 이상 = 오탐 1회, 5 fold 합)
"""
import os, sys
import numpy as np
from joblib import Parallel, delayed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import train_v0 as t0, train_v1 as t1, train_v2 as t2, train_v4 as t4

RUNS = [("v2", "linear", 0), ("v2", "mlp", 0), ("v2", "mlp", 1), ("v3m", "linear", 0), ("v3m", "mlp", 0), ("v3m", "mlp", 1)]
THR = np.r_[np.linspace(0.0, 0.9, 46), np.linspace(0.9, 0.9995, 60)]


def scores(O, A, D, P, H, data, model, seed, k):
    import torch
    torch.set_num_threads(1)
    kinds, sel = t4.DATA[data]
    extra = None
    if sel is not None:
        m = np.ones(len(H["cls"]), bool) if sel == "all" else np.isin(H["cls"], sel)
        extra = (H["emb"][m], np.zeros(m.sum(), int), H["group"][m])
    X, y, _ = t2.train_set(O, A, D, P, kinds, (), False, k, extra=extra)
    clf = (t4.MLP(seed=seed) if model == "mlp" else t0.model()).fit(X, y)
    te = O["fold"] == k
    return clf.predict_proba(O["emb"][te])[:, 1], O["label"][te], O["row"][te], O["t"][te], O["event"][te]


def curve(per_fold):
    out = []
    for th in THR:
        fa = 0; hours = 0.0
        hit = {}
        for k, (s, y, ro, t, ev) in per_fold.items():
            pos = y == 1
            for r in np.unique(ro[pos]):                     # 사건 검출: 사건(파일·마이크 묶음) 안에서 연속 3창 중 2창 (v0 규칙)
                m = pos & (ro == r); f = (s[m] >= th)[np.argsort(t[m])]
                hit[ev[m][0]] = hit.get(ev[m][0], False) or t0.two_of_three(f)
            neg = y == 0
            for r in np.unique(ro[neg]):
                m = neg & (ro == r); f = (s[m] >= th)[np.argsort(t[m])]
                hours += (0.5 * m.sum() + 0.5) / 3600
                fa += t0.two_of_three(f)
        s, y, _, _, _ = per_fold[1]
        fpv_ev = [v for e, v in hit.items() if "_Fp_" in e]
        out.append((th, np.mean(s[y == 1] >= th), fa / hours, np.mean(list(hit.values())), np.mean(fpv_ev)))
    return np.array(out)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    O, A, D, off, _ = t1.load(); P = t2.load_fpv()
    z = np.load(os.path.join(t1.CACHE, "emb_v3_neg.npz"), allow_pickle=False); H = {k: z[k] for k in ("emb", "cls", "group")}
    jobs = [(r, k) for r in RUNS for k in range(1, 6)]
    res = Parallel(n_jobs=10)(delayed(scores)(O, A, D, P, H, *r, k) for r, k in jobs)
    C = {}
    for (r, k), v in zip(jobs, res):
        C.setdefault(r, {})[k] = v
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    plt.figure(figsize=(6.4, 4.2))
    print("오탐/시간 ≤ 1, 2, 5에서 가능한 최대값: FPV 창 재현율 | 사건 검출률 (21건) | FPV 사건 (3건)")
    for r in RUNS:
        cv = curve(C[r])
        cells = []
        for lim in (1, 2, 5):
            ok = cv[:, 2] <= lim
            cells.append(f"≤{lim}: {cv[ok, 1].max():.2f} | {cv[ok, 3].max():.2f} | {cv[ok, 4].max():.2f}" if ok.any() else f"≤{lim}: -")
        print(f"  {r[0]:4s} {r[1]:6s} 시드{r[2]}:  " + "   ".join(cells))
        plt.plot(cv[:, 2], cv[:, 1], ("-" if r[1] == "linear" else "--"), label=f"{r[0]} {'직선' if r[1] == 'linear' else 'MLP'} s{r[2]}")
    plt.xscale("symlog", linthresh=1); plt.xlim(0, 60); plt.xlabel("False alarms per hour (ESC-50 test, 2-of-3)"); plt.ylabel("FPV window recall (fold 1)")
    plt.axvline(1, color="gray", lw=0.8); plt.grid(alpha=0.3); plt.legend(fontsize=8); plt.tight_layout()
    plt.savefig(os.path.join(t1.OUT, "v4_curve.png"), dpi=110)


if __name__ == "__main__":
    main()
