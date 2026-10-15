"""Step8 첫 모델 평가: CNN14 임베딩 + 로지스틱 회귀, 기체 하나씩 빼는 5-fold.

    python ml/train_v0.py            (embed_v0.py 결과 사용) → reports/step8/v0_report.md

fold k: 시험 = 기체 하나(학습에 없음) + ESC-50 fold k, 학습 = 나머지
문턱  : 학습 데이터 안에서 사건 단위 교차검증 점수로, 비드론 창의 오탐률 1%가 되는 값 (시험 데이터는 문턱 선택에 안 씀)
판정  : 창(1 s, 0.5 s 이동) 단위와 "연속 3창 중 2창 이상"(지속 확인) 단위를 함께 보고
비교  : 학습 없는 기준선 = AudioSet 점수 max(Aircraft, Propeller/airscrew, Helicopter) 의 AUC
"""
import os, sys, csv
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
CACHE = os.path.join(ROOT, "DataSet", "_cache", "emb_v0.npz")
OUT = os.path.join(ROOT, "reports", "step8")
FPR_TARGET = 0.01
AIRCRAFT = {"Fp": "DJI FPV", "3p": "Mini 3 Pro", "M3": "Matrice 300", "Yn": "Yuneec H520E", "A3": "Air 3 (WS)"}


def model():
    return make_pipeline(StandardScaler(), LogisticRegression(C=0.05, class_weight="balanced", max_iter=3000))


def two_of_three(flags):
    f = np.asarray(flags, int)
    if len(f) < 3:
        return f.sum() >= min(2, len(f))
    return bool((np.convolve(f, np.ones(3, int), mode="valid") >= 2).any())


def audioset_idx(names):
    lab = list(csv.reader(open(os.path.expanduser("~/panns_data/class_labels_indices.csv"), encoding="utf-8")))[1:]
    return [int(r[0]) for r in lab if r[2] in names]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    z = np.load(CACHE, allow_pickle=False)
    keep = z["label"] >= 0
    X, y = z["emb"][keep], z["label"][keep]
    fold, event, cat, air, row, t = (z[k][keep] for k in ("fold", "event", "category", "aircraft", "row", "t"))
    zs = z["clip"][keep][:, audioset_idx({"Aircraft", "Propeller, airscrew", "Helicopter"})].max(axis=1)
    print(f"창 {len(y)} (드론 {y.sum()}, 비드론 {(y == 0).sum()}), 불확실 제외 {(~keep).sum()}")

    lines, cat_fa = [], {}
    for k in range(1, 6):
        tr, te = fold != k, fold == k
        # 문턱: 학습 데이터 안의 사건 단위 교차검증 점수
        oof = np.zeros(tr.sum())
        for a, b in GroupKFold(4).split(X[tr], y[tr], event[tr]):
            oof[b] = model().fit(X[tr][a], y[tr][a]).predict_proba(X[tr][b])[:, 1]
        thr = np.quantile(oof[y[tr] == 0], 1 - FPR_TARGET)
        clf = model().fit(X[tr], y[tr])
        s = clf.predict_proba(X[te])[:, 1]
        yt, ev, ro = y[te], event[te], row[te]
        auc = roc_auc_score(yt, s); auc0 = roc_auc_score(yt, zs[te])
        pos, neg = yt == 1, yt == 0
        # 사건 검출: 드론 사건(파일·마이크 단위 창 묶음)마다 창 / 2-of-3
        ev_hit1, ev_hit2 = {}, {}
        for r_ in np.unique(ro[pos]):
            m = pos & (ro == r_)
            order = np.argsort(t[te][m]); f = (s[m] >= thr)[order]
            e = ev[m][0]
            ev_hit1[e] = ev_hit1.get(e, False) or f.any()
            ev_hit2[e] = ev_hit2.get(e, False) or two_of_three(f)
        # 비드론 클립 오탐: 클립(파일) 단위
        fa1 = fa2 = nclip = 0; dur = 0.0
        for r_ in np.unique(ro[neg]):
            m = neg & (ro == r_)
            order = np.argsort(t[te][m]); f = (s[m] >= thr)[order]
            nclip += 1; dur += 0.5 * m.sum() + 0.5
            fa1 += f.any(); hit = two_of_three(f); fa2 += hit
            if hit:
                c = cat[te][m][0]; cat_fa[c] = cat_fa.get(c, 0) + 1
        lines.append(dict(fold=k, air=AIRCRAFT[air[te][pos][0]] if pos.any() else "-", n_ev=len(ev_hit1),
                          auc=auc, auc0=auc0, thr=thr, rec_w=np.mean(s[pos] >= thr), fpr_w=np.mean(s[neg] >= thr),
                          ev1=sum(ev_hit1.values()), ev2=sum(ev_hit2.values()), fa1=fa1, fa2=fa2, nclip=nclip,
                          fa2_h=fa2 / (dur / 3600)))
        L = lines[-1]
        print(f"fold{k} {L['air']:14s} AUC {auc:.3f} (무학습 {auc0:.3f})  창 재현율 {L['rec_w']:.2f} 오탐 {L['fpr_w']:.3f}  "
              f"사건 {L['ev2']}/{L['n_ev']} (2-of-3)  클립 오탐 {fa2}/{nclip}")

    os.makedirs(OUT, exist_ok=True)
    tot_ev = sum(L["n_ev"] for L in lines); tot_hit = sum(L["ev2"] for L in lines)
    tot_fa = sum(L["fa2"] for L in lines); tot_clip = sum(L["nclip"] for L in lines)
    top = sorted(cat_fa.items(), key=lambda kv: -kv[1])[:12]
    md = ["# Step8 v0 — CNN14 임베딩 + 로지스틱 회귀 (공개 원음, 기체 하나씩 빼는 5-fold)", "",
          "> `Tools/ml/train_v0.py`가 만든 파일. 입력 `Tools/ml/embed_v0.py` (장치와 같은 FIR·↓4 → 16 kHz → 1 s 창 → CNN14).",
          f"> 문턱: 학습 데이터 안 교차검증에서 비드론 창 오탐 {FPR_TARGET:.0%}. 사건·클립 판정은 연속 3창 중 2창.", "",
          "| fold | 시험 기체 (학습에 없음) | 창 AUC | 무학습 AUC | 창 재현율 | 창 오탐률 | 사건 검출 (2-of-3) | 비드론 클립 오탐 |",
          "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for L in lines:
        md.append(f"| {L['fold']} | {L['air']} | {L['auc']:.3f} | {L['auc0']:.3f} | {L['rec_w']:.2f} | {L['fpr_w']:.3f} | "
                  f"{L['ev2']}/{L['n_ev']} | {L['fa2']}/{L['nclip']} |")
    md += ["", f"**합계**: 드론 사건 {tot_hit}/{tot_ev} 검출, 비드론 클립 {tot_fa}/{tot_clip} 오탐.", "",
           "오탐이 많은 비드론 범주 (5 fold 합, 클립 수): " + ", ".join(f"{c} {n}" for c, n in top), ""]
    open(os.path.join(OUT, "v0_report.md"), "w", encoding="utf-8").write("\n".join(md))
    print("\n".join(md[-4:]))


if __name__ == "__main__":
    main()
