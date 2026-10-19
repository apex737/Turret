"""Step8 v1 평가: v0(CNN14 임베딩 + 로지스틱 회귀)과 같은 모델·fold·문턱 규칙에 증강과 장치 잡음 음성을 더한다.

    python ml/train_v1.py      (embed_v0.py, embed_v1.py 결과 사용) → reports/step8/v1_report.md

설정 (학습 데이터만 다르고 시험은 v0과 같은 원본 fold k)
  v0        원본만
  +S +D +E +N +A   증강 그룹 하나씩 (embed_v1.py 설명)
  +dev      장치 잡음 음성만
  v1        증강 전부 + 장치 잡음 음성
누수 방지: 기체 a의 증강본은 fold a가 시험일 때 학습에서 뺀다. 장치 잡음은 학습 전용.
v1 판정 (Roadmap Step8 v1, 개발용): FPV 창 재현율 ≥ 0.5, Matrice 통과 비행 AUC ≥ 0.9, 오탐/시간이 v0보다 늘지 않음.
장치 경로 시험: speaker_10min 창 중 그 fold의 시험 기체 구간만 (FPV·Mini 3 Pro·Air 3 fold).
"""
import csv, os, sys
import numpy as np
from joblib import Parallel, delayed
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import train_v0 as t0

ROOT = t0.ROOT
CACHE = os.path.join(ROOT, "DataSet", "_cache")
OUT = os.path.join(ROOT, "reports", "step8")
CONFIGS = {"v0": ((), False), "+S": (("S",), False), "+D": (("D",), False), "+E": (("E",), False), "+N": (("N",), False),
           "+A": (("A",), False), "+dev": ((), True), "v1": (("S", "D", "E", "N", "A"), True)}
GOAL = dict(fpv_rec=0.5, m3_fly_auc=0.9)


def load():
    z = np.load(os.path.join(CACHE, "emb_v0.npz"), allow_pickle=False)
    keep = z["label"] >= 0
    rows = list(csv.DictReader(open(os.path.join(ROOT, "data", "dataset_manifest.csv"), encoding="utf-8")))
    O = {k: z[k][keep] for k in ("emb", "label", "fold", "event", "category", "aircraft", "row", "t")}
    O["op"] = np.array([rows[r]["op"] for r in O["row"]])
    a = np.load(os.path.join(CACHE, "emb_v1_aug.npz"), allow_pickle=False)
    A = {k: a[k] for k in ("emb", "group", "fold", "event", "aircraft")}
    d = np.load(os.path.join(CACHE, "emb_v1_dev.npz"), allow_pickle=False)
    D = {k: d[k] for k in ("emb", "kind", "category", "aircraft", "t")}
    return O, A, D, float(d["offset"]), float(d["offset_corr"])


def run_fold(O, A, D, groups, dev, k, off):
    tr = O["fold"] != k
    X = [O["emb"][tr]]; y = [O["label"][tr]]; g = [O["event"][tr]]
    if groups:
        m = np.isin(A["group"], groups) & (A["fold"] != k)
        X.append(A["emb"][m]); y.append(np.ones(m.sum(), int)); g.append(A["event"][m])     # 증강본 = 원본 사건과 같은 묶음
    if dev:
        m = D["kind"] == "neg"
        X.append(D["emb"][m]); y.append(np.zeros(m.sum(), int)); g.append(D["category"][m])
    X, y, g = np.concatenate(X), np.concatenate(y), np.concatenate(g)
    oof = np.zeros(len(y))
    for a, b in GroupKFold(4).split(X, y, g):
        oof[b] = t0.model().fit(X[a], y[a]).predict_proba(X[b])[:, 1]
    thr = np.quantile(oof[y == 0], 1 - t0.FPR_TARGET)
    clf = t0.model().fit(X, y)

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
               ev=sum(ev_hit.values()), n_ev=len(ev_hit), fa=fa, nclip=nclip, hours=dur / 3600, thr=thr, cat_fa=cat_fa)
    for o in ("flyover", "hover", "flight"):
        m = pos & (op == o)
        if m.any():
            res[f"auc_{o}"] = roc_auc_score(np.r_[np.ones(m.sum()), np.zeros(neg.sum())], np.r_[s[m], s[neg]])
            res[f"rec_{o}"] = np.mean(s[m] >= thr)
    ph = (D["t"] - off) % 20.0                       # 20 s 원음 구간 안의 위치 (재생 시작 추정 오차 ±1 s를 감안해 경계 1.5 s 제외)
    m = (D["kind"] == "test") & (D["aircraft"] == air) & (ph >= 1.5) & (ph + 1.0 <= 18.5)
    if m.any():
        sd = clf.predict_proba(D["emb"][m])[:, 1]
        res.update(dev_n=int(m.sum()), dev_rec=float(np.mean(sd >= thr)), dev_med=float(np.median(sd)))
    return res


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    O, A, D, off, corr = load()
    counts = ", ".join(f"{g} {np.sum(A['group'] == g)}" for g in t0np(A))
    print(f"원본 창 {len(O['label'])}, 증강 창 {len(A['group'])} ({counts}), "
          f"장치 음성 {np.sum(D['kind'] == 'neg')}, 장치 시험 {np.sum(D['kind'] == 'test')} (재생 시작 {off:.2f} s, 상관 {corr:.2f})")
    jobs = [(c, k) for c in CONFIGS for k in range(1, 6)]
    out = Parallel(n_jobs=-1, verbose=0)(delayed(run_fold)(O, A, D, CONFIGS[c][0], CONFIGS[c][1], k, off) for c, k in jobs)
    R = {}
    for (c, k), r in zip(jobs, out):
        R.setdefault(c, {})[k] = r

    def summ(c):
        F = R[c]
        fa = sum(F[k]["fa"] for k in F); h = sum(F[k]["hours"] for k in F)
        return dict(fpv=F[1]["rec"], m3fly=F[3].get("auc_flyover", np.nan), m3rec=F[3].get("rec_flyover", np.nan),
                    ws=F[5]["rec"], auc=np.mean([F[k]["auc"] for k in F]), ev=sum(F[k]["ev"] for k in F), n_ev=sum(F[k]["n_ev"] for k in F),
                    fa_h=fa / h, fa=fa, dev={F[k]["air"]: (F[k]["dev_rec"], F[k]["dev_n"]) for k in F if "dev_rec" in F[k]})

    S = {c: summ(c) for c in CONFIGS}
    md = ["# Step8 v1 — 증강 + 장치 잡음 음성 (CNN14 임베딩 + 로지스틱 회귀, 기체 하나씩 빼는 5-fold)", "",
          "> `Tools/ml/train_v1.py`가 만든 파일. 입력 `embed_v0.py`(원본), `embed_v1.py`(증강·장치). 모델·fold·문턱 규칙은 v0과 같다.",
          f"> 문턱: 학습 데이터 안 교차검증에서 비드론 창 오탐 {t0.FPR_TARGET:.0%}. 사건·클립 판정은 연속 3창 중 2창. 시험 fold는 증강하지 않는다.", "",
          "## 설정별 요약", "",
          "| 설정 | FPV 창 재현율 | Matrice 통과 AUC | Matrice 통과 재현율 | Air 3(WS) 재현율 | 평균 창 AUC | 사건 (2-of-3) | 오탐/시간 | 장치 경로 재현율 (FPV / Mini3 / Air3) |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for c in CONFIGS:
        s = S[c]
        dv = " / ".join(f"{s['dev'][a][0]:.2f}" if a in s["dev"] else "-" for a in ("Fp", "3p", "A3"))
        md.append(f"| {c} | {s['fpv']:.2f} | {s['m3fly']:.3f} | {s['m3rec']:.2f} | {s['ws']:.2f} | {s['auc']:.3f} | {s['ev']}/{s['n_ev']} | "
                  f"{s['fa_h']:.1f} | {dv} |")
    v0, v1 = S["v0"], S["v1"]
    ok = v1["fpv"] >= GOAL["fpv_rec"] and v1["m3fly"] >= GOAL["m3_fly_auc"] and v1["fa_h"] <= v0["fa_h"]
    md += ["", f"**v1 판정 (개발용):** FPV 창 재현율 {v0['fpv']:.2f} → {v1['fpv']:.2f} (목표 ≥ {GOAL['fpv_rec']}), "
           f"Matrice 통과 AUC {v0['m3fly']:.3f} → {v1['m3fly']:.3f} (목표 ≥ {GOAL['m3_fly_auc']}), "
           f"오탐/시간 {v0['fa_h']:.1f} → {v1['fa_h']:.1f} (v0 이하) → **{'달성' if ok else '미달'}**", "",
           "## v1 fold별", "",
           "| fold | 시험 기체 | 창 AUC | 창 재현율 | 창 오탐률 | 통과/호버 AUC | 사건 (2-of-3) | 비드론 클립 오탐 | 장치 경로 재현율 (창 수, 점수 중앙값) |",
           "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for k in range(1, 6):
        r = R["v1"][k]
        sub = " / ".join(f"{r[q]:.3f}" for q in ("auc_flyover", "auc_hover", "auc_flight") if q in r)
        dv = f"{r['dev_rec']:.2f} ({r['dev_n']}, {r['dev_med']:.2f})" if "dev_rec" in r else "-"
        md.append(f"| {k} | {t0.AIRCRAFT[r['air']]} | {r['auc']:.3f} | {r['rec']:.2f} | {r['fpr']:.3f} | {sub} | {r['ev']}/{r['n_ev']} | "
                  f"{r['fa']}/{r['nclip']} | {dv} |")
    cat = {}
    for k in range(1, 6):
        for c_, n in R["v1"][k]["cat_fa"].items():
            cat[c_] = cat.get(c_, 0) + n
    md += ["", "v1 오탐이 많은 비드론 범주 (클립 수): " + ", ".join(f"{c_} {n}" for c_, n in sorted(cat.items(), key=lambda kv: -kv[1])[:12]), "",
           f"장치 경로 시험: speaker_10min (노트북 스피커 → 보드 MIC1), 재생 시작 {off:.2f} s (포락선 상관 {corr:.2f}). "
           "장치 잡음 음성(같은 방·같은 보드)이 학습에 들어가므로 장치 경로 재현율은 낙관적일 수 있다.", ""]
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "v1_report.md"), "w", encoding="utf-8").write("\n".join(md))
    print("\n".join(md[6:6 + len(CONFIGS) + 4]))


def t0np(A):
    return [g for g in ("S", "D", "E", "N", "A") if np.any(A["group"] == g)]


if __name__ == "__main__":
    main()
