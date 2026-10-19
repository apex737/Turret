"""Step8 v4 (C1): 분류기만 바꾼다 — CNN14 임베딩 위의 직선(로지스틱 회귀) → 작은 신경망(MLP). 데이터·fold·문턱 규칙은 v2·v3과 같다.

    python ml/train_v4.py      (embed_v0~v3 결과 사용) → reports/step8/v4_report.md

왜: v3에서 비드론을 더하면 오탐은 줄지만 FPV·장치 경로 재현율이 같이 떨어졌다. 고정 임베딩 위의 직선 하나로는
    FPV와 기계음을 함께 가를 수 없다는 뜻으로 보고, 굽은 경계를 그릴 수 있는 분류기로 같은 데이터를 다시 본다.
MLP: 표준화 → 2048 → 256 (ReLU, 드롭아웃 0.5) → 1. Adam lr 1e-3, 가중치 감쇠 1e-3, 20 에폭, 배치 512,
     양성 가중치 = 음성 수 / 양성 수 (로지스틱 회귀의 class_weight="balanced"와 같은 역할). 시드 2개로 흔들림을 본다.
데이터 조합: v2 (새 FPV 깨끗한 구간), v3-bug (+ FSD50K 곤충·새), v3m (+ FSD50K 전부 + FPV 잡음 구간)
"""
import os, sys
import numpy as np
from joblib import Parallel, delayed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import train_v0 as t0
import train_v1 as t1
import train_v2 as t2

DATA = {"v2": (("fpv",), None), "v3-bug": (("fpv",), ("Insect", "Bird_vocalization_and_bird_call_and_bird_song")),
        "v3m": (("fpv", "mix"), "all")}
SEEDS = (0, 1)


class MLP:
    """sklearn처럼 fit / predict_proba만 있는 작은 신경망 (torch, CPU)"""
    def __init__(self, seed=0, hidden=256, epochs=20, wd=1e-3, drop=0.5):
        self.seed, self.hidden, self.epochs, self.wd, self.drop = seed, hidden, epochs, wd, drop

    def fit(self, X, y):
        import torch
        torch.manual_seed(self.seed); rng = np.random.default_rng(self.seed)
        self.mu, self.sd = X.mean(axis=0), X.std(axis=0) + 1e-6
        Xt = torch.from_numpy(((X - self.mu) / self.sd).astype(np.float32)); yt = torch.from_numpy(y.astype(np.float32))
        self.net = torch.nn.Sequential(torch.nn.Linear(X.shape[1], self.hidden), torch.nn.ReLU(), torch.nn.Dropout(self.drop),
                                       torch.nn.Linear(self.hidden, 1))
        opt = torch.optim.Adam(self.net.parameters(), lr=1e-3, weight_decay=self.wd)
        lossf = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor((y == 0).sum() / max((y == 1).sum(), 1), dtype=torch.float32))
        self.net.train()
        for _ in range(self.epochs):
            for b in np.array_split(rng.permutation(len(y)), max(1, len(y) // 512)):
                opt.zero_grad()
                lossf(self.net(Xt[b]).squeeze(1), yt[b]).backward()
                opt.step()
        return self

    def predict_proba(self, X):
        import torch
        self.net.eval()
        with torch.no_grad():
            p = torch.sigmoid(self.net(torch.from_numpy(((X - self.mu) / self.sd).astype(np.float32))).squeeze(1)).numpy()
        return np.c_[1 - p, p]


def run(O, A, D, P, H, data, model, seed, k, off):
    """작업자 프로세스 안에서 t0.model을 바꿔 끼운 뒤 v2와 같은 run_fold를 부른다 (joblib 작업자는 모듈을 새로 읽음)"""
    import torch
    torch.set_num_threads(1)
    if model == "mlp":
        t0.model = lambda: MLP(seed=seed)
    kinds, sel = DATA[data]
    extra = None
    if sel is not None:
        m = np.ones(len(H["cls"]), bool) if sel == "all" else np.isin(H["cls"], sel)
        extra = (H["emb"][m], np.zeros(m.sum(), int), H["group"][m])
    return t2.run_fold(O, A, D, P, (kinds, (), False), k, off, extra)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    O, A, D, off, _ = t1.load()
    P = t2.load_fpv()
    z = np.load(os.path.join(t1.CACHE, "emb_v3_neg.npz"), allow_pickle=False)
    H = {k: z[k] for k in ("emb", "cls", "group")}
    runs = [(d, "linear", 0) for d in DATA] + [(d, "mlp", s) for d in DATA for s in SEEDS]
    jobs = [(r, k) for r in runs for k in range(1, 6)]
    out = Parallel(n_jobs=10)(delayed(run)(O, A, D, P, H, d, m, s, k, off) for (d, m, s), k in jobs)
    R = {}
    for (r, k), res in zip(jobs, out):
        R.setdefault(r, {})[k] = res

    def summ(F):
        fa = sum(F[k]["fa"] for k in F); h = sum(F[k]["hours"] for k in F)
        cat = {}
        for k in F:
            for c_, n in F[k]["cat_fa"].items():
                cat[c_] = cat.get(c_, 0) + n
        return dict(fpv=F[1]["rec"], fpv_auc=F[1]["auc"], ins=F[1].get("auc_insects", np.nan), m3fly=F[3].get("auc_flyover", np.nan),
                    rec_all=np.mean([F[k]["rec"] for k in F]), auc=np.mean([F[k]["auc"] for k in F]), ev=sum(F[k]["ev"] for k in F),
                    n_ev=sum(F[k]["n_ev"] for k in F), fa=fa, fa_h=fa / h, cat=cat,
                    dev={F[k]["air"]: F[k]["dev_rec"] for k in F if "dev_rec" in F[k]})
    md = ["# Step8 v4 (C1) — 분류기만 MLP로 (CNN14 임베딩, 기체 하나씩 빼는 5-fold)", "",
          "> `Tools/ml/train_v4.py`가 만든 파일. 데이터·fold·문턱 규칙·시험 데이터는 v2·v3과 같고 분류기만 다르다.",
          f"> 문턱: 학습 데이터 안 교차검증에서 비드론 창 오탐 {t0.FPR_TARGET:.0%}. 사건·클립 판정은 연속 3창 중 2창. MLP는 시드 {len(SEEDS)}개.", "",
          "| 데이터 | 분류기 | FPV 창 재현율 | FPV 창 AUC | FPV 대 곤충 AUC | Matrice 통과 AUC | 5기종 평균 재현율 | 평균 창 AUC | 사건 | 오탐/시간 (클립) | 장치 경로 재현율 (FPV / Mini3 / Air3) |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    S = {r: summ(R[r]) for r in runs}
    for r in runs:
        s = S[r]
        dv = " / ".join(f"{s['dev'][a]:.2f}" if a in s["dev"] else "-" for a in ("Fp", "3p", "A3"))
        name = "직선" if r[1] == "linear" else f"MLP 시드 {r[2]}"
        md.append(f"| {r[0]} | {name} | {s['fpv']:.2f} | {s['fpv_auc']:.3f} | {s['ins']:.2f} | {s['m3fly']:.3f} | {s['rec_all']:.2f} | {s['auc']:.3f} | "
                  f"{s['ev']}/{s['n_ev']} | {s['fa_h']:.1f} ({s['fa']}) | {dv} |")
    md += ["", "## 오탐 범주 (5 fold 합, 클립 수)", "", "| 데이터 | 분류기 | 오탐 범주 |", "| --- | --- | --- |"]
    for r in runs:
        name = "직선" if r[1] == "linear" else f"MLP 시드 {r[2]}"
        md.append(f"| {r[0]} | {name} | " + ", ".join(f"{c_} {n}" for c_, n in sorted(S[r]["cat"].items(), key=lambda kv: -kv[1])[:8]) + " |")
    md.append("")
    open(os.path.join(t1.OUT, "v4_report.md"), "w", encoding="utf-8").write("\n".join(md))
    print("\n".join(md[5:5 + len(runs) + 2]))


if __name__ == "__main__":
    main()
