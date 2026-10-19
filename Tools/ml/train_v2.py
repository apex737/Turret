"""Step8 v2 평가: Salford 밖 FPV 양성(DVIDS·Freesound)을 학습에 더한다. 모델·fold·문턱 규칙·시험 데이터는 v0과 같다.

    python ml/train_v2.py      (embed_v0/v1/v2 결과 사용) → reports/step8/v2_report.md

설정
  v0        원본만
  v2        + 새 FPV 깨끗한 구간 (DVIDS fpv, Freesound)
  v2m       + 새 FPV 잡음 섞인 구간까지 (DVIDS mix)
  v2m+N     v2m + 원본 배경 혼합 증강 (v1에서 유일하게 조금 나았던 N)
  v2m+dev   v2m + 장치 잡음 음성
새 FPV는 어느 fold에서도 시험에 들어가지 않는다 (학습 전용). 문턱 교차검증에서는 영상·파일 하나를 한 묶음으로 둔다.
추가 지표 (출처 사이 일반화): DVIDS를 빼고 학습(fold 1 조건 + Freesound FPV)한 모델이 DVIDS FPV 창을 얼마나 찾는가.
"""
import os, sys
import numpy as np
from joblib import Parallel, delayed
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import train_v0 as t0
import train_v1 as t1

CACHE = t1.CACHE
OUT = t1.OUT
CONFIGS = {"v0": ((), (), False), "v2": (("fpv",), (), False), "v2m": (("fpv", "mix"), (), False),
           "v2m+N": (("fpv", "mix"), ("N",), False), "v2m+dev": (("fpv", "mix"), (), True)}


def load_fpv():
    z = np.load(os.path.join(CACHE, "emb_v2_fpv.npz"), allow_pickle=False)
    return {k: z[k] for k in ("emb", "group", "kind")}


def fit_with_threshold(X, y, g):
    oof = np.zeros(len(y))
    for a, b in GroupKFold(4).split(X, y, g):
        oof[b] = t0.model().fit(X[a], y[a]).predict_proba(X[b])[:, 1]
    return t0.model().fit(X, y), np.quantile(oof[y == 0], 1 - t0.FPR_TARGET)


def train_set(O, A, D, P, kinds, groups, dev, k, exclude_group=None, extra=None):
    tr = O["fold"] != k
    X = [O["emb"][tr]]; y = [O["label"][tr]]; g = [O["event"][tr]]
    if kinds:
        m = np.isin(P["kind"], kinds) & (P["group"] != exclude_group)
        X.append(P["emb"][m]); y.append(np.ones(m.sum(), int)); g.append(P["group"][m])
    if groups:
        m = np.isin(A["group"], groups) & (A["fold"] != k)
        X.append(A["emb"][m]); y.append(np.ones(m.sum(), int)); g.append(A["event"][m])
    if dev:
        m = D["kind"] == "neg"
        X.append(D["emb"][m]); y.append(np.zeros(m.sum(), int)); g.append(D["category"][m])
    if extra is not None:                                # (X, y, group) 학습 전용 추가 데이터 (예: v3 FSD50K 비드론)
        X.append(extra[0]); y.append(extra[1]); g.append(extra[2])
    return np.concatenate(X), np.concatenate(y), np.concatenate(g)


def run_fold(O, A, D, P, cfg, k, off, extra=None):
    kinds, groups, dev = cfg
    clf, thr = fit_with_threshold(*train_set(O, A, D, P, kinds, groups, dev, k, extra=extra))
    te = O["fold"] == k
    s = clf.predict_proba(O["emb"][te])[:, 1]
    yt, ev, ro, tt, op, cat = (O[q][te] for q in ("label", "event", "row", "t", "op", "category"))
    pos, neg = yt == 1, yt == 0
    ev_hit = {}
    for r_ in np.unique(ro[pos]):
        mm = pos & (ro == r_); f = (s[mm] >= thr)[np.argsort(tt[mm])]
        ev_hit[ev[mm][0]] = ev_hit.get(ev[mm][0], False) or t0.two_of_three(f)
    fa = nclip = 0; dur = 0.0; cat_fa = {}
    for r_ in np.unique(ro[neg]):
        mm = neg & (ro == r_); f = (s[mm] >= thr)[np.argsort(tt[mm])]
        nclip += 1; dur += 0.5 * mm.sum() + 0.5
        if t0.two_of_three(f):
            fa += 1; cat_fa[cat[mm][0]] = cat_fa.get(cat[mm][0], 0) + 1
    air = O["aircraft"][te][pos][0]
    res = dict(fold=k, air=air, auc=roc_auc_score(yt, s), rec=np.mean(s[pos] >= thr), fpr=np.mean(s[neg] >= thr),
               ev=sum(ev_hit.values()), n_ev=len(ev_hit), fa=fa, nclip=nclip, hours=dur / 3600, cat_fa=cat_fa, thr=thr)
    for o in ("flyover", "hover", "flight"):
        m = pos & (op == o)
        if m.any():
            res[f"auc_{o}"] = roc_auc_score(np.r_[np.ones(m.sum()), np.zeros(neg.sum())], np.r_[s[m], s[neg]])
            res[f"rec_{o}"] = np.mean(s[m] >= thr)
    ph = (D["t"] - off) % 20.0
    m = (D["kind"] == "test") & (D["aircraft"] == air) & (ph >= 1.5) & (ph + 1.0 <= 18.5)
    if m.any():
        sd = clf.predict_proba(D["emb"][m])[:, 1]
        res.update(dev_n=int(m.sum()), dev_rec=float(np.mean(sd >= thr)), dev_med=float(np.median(sd)))
    # 곤충과의 분리 (v1 실패 원인): 시험 fold의 드론 창 대 곤충 창 AUC
    ins = neg & (cat == "insects")
    if ins.any():
        res["auc_insects"] = roc_auc_score(np.r_[np.ones(pos.sum()), np.zeros(ins.sum())], np.r_[s[pos], s[ins]])
    return res


def holdout_dvids(O, A, D, P):
    """DVIDS를 빼고 (fold 1 조건 + Freesound FPV) 학습 → DVIDS FPV 창 재현율. 출처가 다른 FPV로 일반화되는지"""
    X, y, g = train_set(O, A, D, P, ("fpv", "mix"), (), False, 1, exclude_group=None)
    keep = ~np.char.startswith(np.r_[O["event"][O["fold"] != 1], P["group"][np.isin(P["kind"], ("fpv", "mix"))]].astype(str), "dvids")
    clf, thr = fit_with_threshold(X[keep], y[keep], g[keep])
    out = {}
    for grp in np.unique(P["group"]):
        if grp.startswith("dvids"):
            m = P["group"] == grp
            out[grp] = (float(np.mean(clf.predict_proba(P["emb"][m])[:, 1] >= thr)), int(m.sum()))
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    O, A, D, off, _ = t1.load()
    P = load_fpv()
    counts = ", ".join(f"{g} {np.sum(P['group'] == g)}" for g in np.unique(P["group"]))
    print(f"원본 창 {len(O['label'])}, 새 FPV 창 {len(P['kind'])} ({counts})")
    jobs = [(c, k) for c in CONFIGS for k in range(1, 6)]
    out = Parallel(n_jobs=-1)(delayed(run_fold)(O, A, D, P, CONFIGS[c], k, off) for c, k in jobs)
    R = {}
    for (c, k), r in zip(jobs, out):
        R.setdefault(c, {})[k] = r
    hold = holdout_dvids(O, A, D, P)

    def summ(c):
        F = R[c]
        fa = sum(F[k]["fa"] for k in F); h = sum(F[k]["hours"] for k in F)
        return dict(fpv=F[1]["rec"], fpv_auc=F[1]["auc"], ins=F[1].get("auc_insects", np.nan), m3fly=F[3].get("auc_flyover", np.nan),
                    ws=F[5]["rec"], auc=np.mean([F[k]["auc"] for k in F]), ev=sum(F[k]["ev"] for k in F), n_ev=sum(F[k]["n_ev"] for k in F),
                    fa_h=fa / h, dev={F[k]["air"]: F[k]["dev_rec"] for k in F if "dev_rec" in F[k]})
    S = {c: summ(c) for c in CONFIGS}
    md = ["# Step8 v2 — Salford 밖 FPV 양성 추가 (CNN14 임베딩 + 로지스틱 회귀, 기체 하나씩 빼는 5-fold)", "",
          "> `Tools/ml/train_v2.py`가 만든 파일. 새 FPV(DVIDS 영상 사람 라벨, Freesound 2개)는 학습 전용이고 시험 데이터는 v0과 같다.",
          f"> 문턱: 학습 데이터 안 교차검증에서 비드론 창 오탐 {t0.FPR_TARGET:.0%}. 사건·클립 판정은 연속 3창 중 2창.", "",
          "| 설정 | FPV 창 재현율 | FPV 창 AUC | FPV 대 곤충 AUC | Matrice 통과 AUC | Air 3(WS) 재현율 | 평균 창 AUC | 사건 (2-of-3) | 오탐/시간 | 장치 경로 재현율 (FPV / Mini3 / Air3) |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for c in CONFIGS:
        s = S[c]
        dv = " / ".join(f"{s['dev'][a]:.2f}" if a in s["dev"] else "-" for a in ("Fp", "3p", "A3"))
        md.append(f"| {c} | {s['fpv']:.2f} | {s['fpv_auc']:.3f} | {s['ins']:.2f} | {s['m3fly']:.3f} | {s['ws']:.2f} | {s['auc']:.3f} | "
                  f"{s['ev']}/{s['n_ev']} | {s['fa_h']:.1f} | {dv} |")
    md += ["", "**출처 사이 일반화:** DVIDS를 빼고 학습한 모델(fold 1 조건 + Freesound FPV)의 DVIDS FPV 창 재현율: " +
           ", ".join(f"{g} {r:.2f} ({n}창)" for g, (r, n) in hold.items()), ""]
    best = max(CONFIGS, key=lambda c: S[c]["fpv"])
    md += [f"## {best} fold별", "", "| fold | 시험 기체 | 창 AUC | 창 재현율 | 창 오탐률 | 사건 | 비드론 클립 오탐 | 장치 경로 재현율 |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for k in range(1, 6):
        r = R[best][k]
        dv = f"{r['dev_rec']:.2f}" if "dev_rec" in r else "-"
        md.append(f"| {k} | {t0.AIRCRAFT[r['air']]} | {r['auc']:.3f} | {r['rec']:.2f} | {r['fpr']:.3f} | {r['ev']}/{r['n_ev']} | {r['fa']}/{r['nclip']} | {dv} |")
    cat = {}
    for k in range(1, 6):
        for c_, n in R[best][k]["cat_fa"].items():
            cat[c_] = cat.get(c_, 0) + n
    md += ["", f"{best} 오탐이 많은 비드론 범주 (클립 수): " + ", ".join(f"{c_} {n}" for c_, n in sorted(cat.items(), key=lambda kv: -kv[1])[:10]), ""]
    open(os.path.join(OUT, "v2_report.md"), "w", encoding="utf-8").write("\n".join(md))
    print("\n".join(md[5:5 + len(CONFIGS) + 4]))


if __name__ == "__main__":
    main()
