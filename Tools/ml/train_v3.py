"""Step8 v3 평가: v2(새 FPV 양성)에 FSD50K 어려운 비드론을 학습 전용으로 더한다. 모델·fold·문턱 규칙·시험 데이터는 v0과 같다.

    python ml/train_v3.py      (embed_v0/v1/v2/v3 결과 사용) → reports/step8/v3_report.md

설정 (변수 하나씩)
  v2        v0 + 새 FPV 깨끗한 구간          (기준선)
  v3        v2 + FSD50K 비드론 전부 (곤충 200·새 150·나머지 9범주 80 클립)
  v3-bug    v2 + FSD50K 곤충·새만             (어느 범주가 효과인지)
  v3m       v3 + 새 FPV 잡음 섞인 구간
시험 비드론은 계속 ESC-50 fold k다. FSD50K에서 ESC-50 원본과 같은 Freesound ID는 받을 때 뺐다 (fsd50k_fetch.py).
"""
import os, sys
import numpy as np
from joblib import Parallel, delayed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import train_v0 as t0
import train_v1 as t1
import train_v2 as t2

CONFIGS = {"v2": (("fpv",), None), "v3": (("fpv",), "all"), "v3-bug": (("fpv",), ("Insect", "Bird_vocalization_and_bird_call_and_bird_song")),
           "v3m": (("fpv", "mix"), "all")}


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    O, A, D, off, _ = t1.load()
    P = t2.load_fpv()
    z = np.load(os.path.join(t1.CACHE, "emb_v3_neg.npz"), allow_pickle=False)
    H = {k: z[k] for k in ("emb", "cls", "group")}
    print(f"원본 창 {len(O['label'])}, 새 FPV 창 {len(P['kind'])}, FSD50K 비드론 창 {len(H['cls'])}")

    def extra(sel):
        if sel is None:
            return None
        m = np.ones(len(H["cls"]), bool) if sel == "all" else np.isin(H["cls"], sel)
        return H["emb"][m], np.zeros(m.sum(), int), H["group"][m]

    jobs = [(c, k) for c in CONFIGS for k in range(1, 6)]
    out = Parallel(n_jobs=-1)(delayed(t2.run_fold)(O, A, D, P, (CONFIGS[c][0], (), False), k, off, extra(CONFIGS[c][1])) for c, k in jobs)
    R = {}
    for (c, k), r in zip(jobs, out):
        R.setdefault(c, {})[k] = r

    def summ(c):
        F = R[c]
        fa = sum(F[k]["fa"] for k in F); h = sum(F[k]["hours"] for k in F)
        cat = {}
        for k in F:
            for c_, n in F[k]["cat_fa"].items():
                cat[c_] = cat.get(c_, 0) + n
        return dict(fpv=F[1]["rec"], fpv_auc=F[1]["auc"], ins=F[1].get("auc_insects", np.nan), m3fly=F[3].get("auc_flyover", np.nan),
                    rec_all=np.mean([F[k]["rec"] for k in F]), auc=np.mean([F[k]["auc"] for k in F]),
                    ev=sum(F[k]["ev"] for k in F), n_ev=sum(F[k]["n_ev"] for k in F), fa=fa, fa_h=fa / h, cat=cat,
                    dev={F[k]["air"]: F[k]["dev_rec"] for k in F if "dev_rec" in F[k]})
    S = {c: summ(c) for c in CONFIGS}
    md = ["# Step8 v3 — FSD50K 어려운 비드론 추가 (CNN14 임베딩 + 로지스틱 회귀, 기체 하나씩 빼는 5-fold)", "",
          "> `Tools/ml/train_v3.py`가 만든 파일. FSD50K(곤충·새·전동공구·엔진·항공기 등 1,070 클립)와 새 FPV는 학습 전용이고 시험 데이터는 v0과 같다.",
          f"> 문턱: 학습 데이터 안 교차검증에서 비드론 창 오탐 {t0.FPR_TARGET:.0%}. 사건·클립 판정은 연속 3창 중 2창.", "",
          "| 설정 | FPV 창 재현율 | FPV 창 AUC | FPV 대 곤충 AUC | Matrice 통과 AUC | 5기종 평균 창 재현율 | 평균 창 AUC | 사건 (2-of-3) | 오탐/시간 (클립) | 장치 경로 재현율 (FPV / Mini3 / Air3) |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for c in CONFIGS:
        s = S[c]
        dv = " / ".join(f"{s['dev'][a]:.2f}" if a in s["dev"] else "-" for a in ("Fp", "3p", "A3"))
        md.append(f"| {c} | {s['fpv']:.2f} | {s['fpv_auc']:.3f} | {s['ins']:.2f} | {s['m3fly']:.3f} | {s['rec_all']:.2f} | {s['auc']:.3f} | "
                  f"{s['ev']}/{s['n_ev']} | {s['fa_h']:.1f} ({s['fa']}) | {dv} |")
    md += ["", "## 오탐 범주 (5 fold 합, 클립 수)", "", "| 설정 | 오탐 범주 |", "| --- | --- |"]
    for c in CONFIGS:
        md.append(f"| {c} | " + ", ".join(f"{c_} {n}" for c_, n in sorted(S[c]["cat"].items(), key=lambda kv: -kv[1])[:10]) + " |")
    md.append("")
    open(os.path.join(t1.OUT, "v3_report.md"), "w", encoding="utf-8").write("\n".join(md))
    print("\n".join(md[5:]))


if __name__ == "__main__":
    main()
