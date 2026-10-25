"""Step8b 운용점 곡선: 판정 기준 점수를 바꿔 가며 재현율 대 오탐을 그린다. B0(고조파) 대 v3m(동결한 학습 모델).

    python harmonic/curve_b0.py      (eval_b0.py가 만든 DataSet/_cache/b0_scores.npz, Step8 임베딩 사용)
    → reports/step8b/b0_curve.png, b0_curve.md (수치만)

진단용이다. 기준 점수를 시험 데이터로 고르는 것이 아니라, 같은 오탐에서 어느 쪽이 더 많이 잡는지(곡선이 위에 있는지)를 본다
(Step8 diag_v4_curve와 같은 방식). 기준 점수 하나를 다섯 fold에 똑같이 쓴다.
  공개 원음: 가로 = ESC-50 오탐/시간 (클립, 3창 중 2창), 세로 = FPV 창 재현율 (fold 1)
  장치 경로: 가로 = devpath ESC-50 창 오탐률, 세로 = speaker_10min FPV 창 재현율
조용한 창 규칙(보드 바닥 + 6 dB 미만 → 없음)은 B0 설계의 일부라 B0에만 걸고, v3m은 규칙 없이 / 규칙을 건 것 둘 다 그린다.
"""
import os, sys
import numpy as np
from joblib import Parallel, delayed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, os.path.join(HERE, "..", "ml"))
import train_v0 as t0, train_v1 as t1, train_v2 as t2, train_v5 as t5

CACHE = t1.CACHE
OUT = os.path.join(HERE, "..", "..", "reports", "step8b")
FOLD_OF = {"Fp": 1}


def load_b0():
    z = np.load(os.path.join(CACHE, "b0_scores.npz"), allow_pickle=False)
    pick = lambda pre: {k[len(pre):]: z[k] for k in z.files if k.startswith(pre)}
    return pick("P_"), pick("D_"), pick("V_"), pick("I_"), float(z["off"])


def v3m_fold(O, A, D, P, H, V, off, k):
    """v3m 학습(채택 설정)으로 fold k 모델 → 시험 창 점수"""
    t0.FPR_TARGET = t5.FPR
    res = t2.run_fold(O, A, D, P, (("fpv", "mix"), (), False), k, off, (H["emb"], np.zeros(len(H["emb"]), int), H["group"]))
    clf = res["clf"]
    te = O["fold"] == k
    out = dict(k=k, o_idx=np.flatnonzero(te), o_s=clf.predict_proba(O["emb"][te])[:, 1])
    m = (V["role"] == "test") & (V["fold"] == k)
    out.update(v_idx=np.flatnonzero(m), v_s=clf.predict_proba(V["emb"][m])[:, 1])
    if k == 1:
        m = (D["kind"] == "test") & (D["aircraft"] == "Fp")
        out.update(d_idx=np.flatnonzero(m), d_s=clf.predict_proba(D["emb"][m])[:, 1])
    return out


def public_curve(score, label, fold, row, t, event, thr):
    """기준 점수 thr마다 (ESC 오탐/시간, FPV 창 재현율, 사건 검출률)"""
    out = []
    pos, neg = label == 1, label == 0
    neg_rows = np.unique(row[neg]); pos_rows = np.unique(row[pos])
    hours = sum((0.5 * np.sum(neg & (row == r)) + 0.5) for r in neg_rows) / 3600
    order = {r: np.flatnonzero(row == r)[np.argsort(t[row == r])] for r in np.r_[neg_rows, pos_rows]}
    for th in thr:
        hit = score >= th
        fa = sum(t0.two_of_three(hit[order[r]]) for r in neg_rows)
        ev = {}
        for r in pos_rows:
            ix = order[r][label[order[r]] == 1]; e = event[ix[0]]
            ev[e] = ev.get(e, False) or t0.two_of_three(hit[ix])
        fpv = np.mean(hit[pos & (fold == 1)])
        out.append((fa / hours, fpv, np.mean(list(ev.values()))))
    return np.array(out)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    BP, BD, BV, BI, off = load_b0()
    O, A, D, off1, _ = t1.load(); P = t2.load_fpv(); V = t5.load_dev()
    z = np.load(os.path.join(CACHE, "emb_v3_neg.npz"), allow_pickle=False); H = {k: z[k] for k in ("emb", "cls", "group")}
    assert len(O["t"]) == len(BP["t"]) and np.allclose(O["t"], BP["t"]), "eval_b0와 Step8 창 목록이 다르다"
    vt = (V["role"] == "test")
    assert vt.sum() == len(BV["t"]), "devpath 시험 창 수가 다르다"
    res = Parallel(n_jobs=5)(delayed(v3m_fold)(O, A, D, P, H, V, off1, k) for k in range(1, 6))
    s_o = np.zeros(len(O["t"])); s_v = np.zeros(len(V["t"])); s_d = None; d_idx = None
    for r in res:
        s_o[r["o_idx"]] = r["o_s"]; s_v[r["v_idx"]] = r["v_s"]
        if r["k"] == 1: s_d, d_idx = r["d_s"], r["d_idx"]
    # 장치 경로 FPV 창: Step8과 같은 선택 (20 s 구간의 1.5 s 경계 제외)
    ph = (D["t"][d_idx] - off1) % 20.0; keep = (ph >= 1.5) & (ph + 1.0 <= 18.5)
    s_d = s_d[keep]
    bm = (BD["kind"] == "test") & (BD["aircraft"] == "Fp"); bph = (BD["t"] - off) % 20.0
    bm &= (bph >= 1.5) & (bph + 1.0 <= 18.5)
    b_d, b_dg = BD["S"][bm, 0], BD["gate"][bm]
    s_vt = s_v[vt]; b_v, b_vg = BV["S"][:, 0], BV["gate"]
    # devpath 시험 창의 레벨(조용한 창 규칙)은 B0 캐시의 gate를 v3m에도 그대로 쓴다 (같은 창, 같은 순서)
    thr_b = np.r_[np.linspace(0, 30, 121), np.linspace(30, 80, 51)]
    thr_v = np.r_[np.linspace(0, 0.9, 46), np.linspace(0.9, 0.9995, 60)]
    cb = public_curve(BP["S"][:, 0], BP["label"], BP["fold"], BP["row"], BP["t"], BP["event"], thr_b)
    cv = public_curve(s_o, O["label"], O["fold"], O["row"], O["t"], O["event"], thr_v)
    dev = lambda sd, gd, sv, gv, thr: np.array([(np.mean((sv >= th) & gv), np.mean((sd >= th) & gd)) for th in thr])
    one = lambda n: np.ones(n, bool)
    db = dev(b_d, b_dg, b_v, b_vg, thr_b)
    dv = dev(s_d, one(len(s_d)), s_vt, one(len(s_vt)), thr_v)
    # v3m + 조용한 창 규칙: speaker_10min 창의 gate는 B0 캐시 순서와 같다 (같은 D 창 선택)
    dvg = dev(s_d, b_dg, s_vt, b_vg, thr_v)

    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.3))
    ax[0].plot(cb[:, 0], cb[:, 1], "-", label="B0 harmonic, FPV window recall")
    ax[0].plot(cb[:, 0], cb[:, 2], ":", label="B0 harmonic, event detection")
    ax[0].plot(cv[:, 0], cv[:, 1], "-", label="v3m learned, FPV window recall")
    ax[0].plot(cv[:, 0], cv[:, 2], ":", label="v3m learned, event detection")
    ax[0].set_xscale("symlog", linthresh=1); ax[0].set_xlim(0, 700); ax[0].set_ylim(0, 1.02)
    ax[0].set_xlabel("False alarms per hour (ESC-50, public, 2-of-3 clips)"); ax[0].set_ylabel("Recall"); ax[0].set_title("Public recordings")
    ax[1].plot(db[:, 0] * 100, db[:, 1], "-", label="B0 harmonic (+ quiet-window rule)")
    ax[1].plot(dv[:, 0] * 100, dv[:, 1], "-", label="v3m learned")
    ax[1].plot(dvg[:, 0] * 100, dvg[:, 1], "--", label="v3m learned + quiet-window rule")
    ax[1].set_xlim(0, 70); ax[1].set_ylim(0, 1.02)
    ax[1].set_xlabel("Device path: ESC-50 window false-positive rate (%)"); ax[1].set_ylabel("Device path FPV window recall"); ax[1].set_title("Device path (speaker -> MAX4466)")
    for a in ax: a.grid(alpha=0.3); a.legend(fontsize=8)
    fig.tight_layout(); os.makedirs(OUT, exist_ok=True); fig.savefig(os.path.join(OUT, "b0_curve.png"), dpi=110)

    def best(c, xcol, ycol, lim):
        ok = c[:, xcol] <= lim
        return f"{c[ok, ycol].max():.2f}" if ok.any() else "-"
    md = ["# Step8b 운용점 곡선 — B0(고조파) 대 v3m(학습)", "",
          "> `Tools/harmonic/curve_b0.py`가 만든 파일. 수치만 적는다. 기준 점수를 다섯 fold에 똑같이 쓰고 바꿔 가며 그린 진단 곡선이다 (시험 데이터로 기준을 고르는 것이 아님).",
          "> 그림: [b0_curve.png](b0_curve.png)", "",
          "## 공개 원음: 오탐/시간 예산 안에서 가능한 최대값 (FPV 창 재현율 · 사건 검출률)", "",
          "| 오탐 예산 | B0 | v3m |", "|---|---|---|"]
    for lim in (1, 10, 50, 200):
        md.append(f"| ≤ {lim}회/시간 | {best(cb, 0, 1, lim)} · {best(cb, 0, 2, lim)} | {best(cv, 0, 1, lim)} · {best(cv, 0, 2, lim)} |")
    md += ["", "## 장치 경로: 창 오탐률 예산 안에서 가능한 최대 FPV 창 재현율", "",
           "| 오탐률 예산 | B0 (+ 조용한 창 규칙) | v3m | v3m + 조용한 창 규칙 |", "|---|---|---|---|"]
    for lim in (0.01, 0.05, 0.10, 0.20):
        md.append(f"| ≤ {lim:.0%} | {best(db, 0, 1, lim)} | {best(dv, 0, 1, lim)} | {best(dvg, 0, 1, lim)} |")
    md.append("")
    p = os.path.join(OUT, "b0_curve.md"); open(p, "w", encoding="utf-8").write("\n".join(md))
    print(f"→ {p}")


if __name__ == "__main__":
    main()
