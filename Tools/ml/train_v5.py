"""Step8 v5 평가: 장치 경로 녹음(스피커 → MAX4466 → 보드)을 학습에 더한다. 기준선은 채택 운용점 (v3m · 직선 · 창 오탐 0.5%).

    python ml/train_v5.py      (embed_v0~v3, embed_v5 결과 사용) → reports/step8/v5_report.md

설정 (변수 하나씩)
  v3m    기준선 (채택)
  v5p    + 장치 경로 FPV (학습 양성)만        → 스피커 음색 자체를 "드론"으로 배우는지 (지름길) 확인용
  v5     + 장치 경로 FPV + 장치 경로 FSD50K 비드론 (양쪽 클래스가 같은 스피커를 거침)
시험
  공개 원음      v0과 같음 (기체 하나씩 빼는 5-fold, ESC-50 fold k)
  장치 경로 양성 speaker_10min (Salford·WS 원음 재생 녹음, 학습에 쓰지 않은 기체) — 창 재현율, 20 s 구간 검출(3창 중 2창)
  장치 경로 음성 30_devpath의 ESC-50 150 클립 중 fold k 클립 → 장치 경로 오탐/시간 (같은 2-of-3 규칙)
"""
import os, sys
import numpy as np
from joblib import Parallel, delayed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import train_v0 as t0
import train_v1 as t1
import train_v2 as t2

FPR = 0.005                                                  # 채택 운용점 (Step8 9절)
CONFIGS = {"v3m": (False, False), "v5p": (True, False), "v5": (True, True)}


def load_dev():
    z = np.load(os.path.join(t1.CACHE, "emb_v5_dev.npz"), allow_pickle=False)
    return {k: z[k] for k in ("emb", "part", "idx", "label", "role", "group", "cls", "fold", "t")}


def run(O, A, D, P, H, V, off, cfg, k):
    t0.FPR_TARGET = FPR                                      # joblib 작업자는 모듈을 새로 읽으므로 안에서 바꾼다
    pos, neg = CONFIGS[cfg]
    X, y, g = [H["emb"]], [np.zeros(len(H["emb"]), int)], [H["group"]]
    for use, lab in ((pos, 1), (neg, 0)):
        if use:
            m = (V["role"] == "train") & (V["label"] == lab)
            X.append(V["emb"][m]); y.append(np.full(m.sum(), lab)); g.append(V["group"][m])
    res = t2.run_fold(O, A, D, P, (("fpv", "mix"), (), False), k, off, (np.concatenate(X), np.concatenate(y), np.concatenate(g)))
    clf, thr = res.pop("clf"), res["thr"]
    # 장치 경로 오탐: ESC-50 fold k 클립의 장치 녹음
    m = (V["role"] == "test") & (V["fold"] == k)
    s = clf.predict_proba(V["emb"][m])[:, 1]
    clip = np.char.add(V["part"][m], V["idx"][m].astype(str))
    fa, hours, cat = 0, 0.0, {}
    for c in np.unique(clip):
        mm = clip == c
        hours += (0.5 * mm.sum() + 0.5) / 3600
        if t0.two_of_three((s[mm] >= thr)[np.argsort(V["t"][m][mm])]):
            fa += 1; cc = V["cls"][m][mm][0]; cat[cc] = cat.get(cc, 0) + 1
    res.update(dfa=fa, dhours=hours, dfpr=float(np.mean(s >= thr)), dcat=cat)
    # 장치 경로 양성: speaker_10min 20 s 구간마다 3창 중 2창이면 검출 (dev_rec와 같은 창 선택)
    ph = (D["t"] - off) % 20.0
    m = (D["kind"] == "test") & (D["aircraft"] == res["air"]) & (ph >= 1.5) & (ph + 1.0 <= 18.5)
    if m.any():
        sd = clf.predict_proba(D["emb"][m])[:, 1]
        seg = np.floor((D["t"][m] - off) / 20).astype(int)
        hit = [t0.two_of_three((sd[seg == q] >= thr)[np.argsort(D["t"][m][seg == q])]) for q in np.unique(seg)]
        res.update(dev_seg=int(sum(hit)), dev_nseg=len(hit))
    return res


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    O, A, D, off, _ = t1.load()
    P = t2.load_fpv()
    z = np.load(os.path.join(t1.CACHE, "emb_v3_neg.npz"), allow_pickle=False)
    H = {k: z[k] for k in ("emb", "cls", "group")}
    V = load_dev()
    tr = V["role"] == "train"
    print(f"장치 경로 창: 학습 양성 {np.sum(tr & (V['label'] == 1))}, 학습 음성 {np.sum(tr & (V['label'] == 0))}, 시험 음성 {np.sum(~tr)}")
    jobs = [(c, k) for c in CONFIGS for k in range(1, 6)]
    out = Parallel(n_jobs=-1)(delayed(run)(O, A, D, P, H, V, off, c, k) for c, k in jobs)
    R = {}
    for (c, k), r in zip(jobs, out):
        R.setdefault(c, {})[k] = r

    def summ(F):
        fa = sum(F[k]["fa"] for k in F); h = sum(F[k]["hours"] for k in F)
        dfa = sum(F[k]["dfa"] for k in F); dh = sum(F[k]["dhours"] for k in F)
        cat = {}
        for k in F:
            for c_, n in F[k]["dcat"].items():
                cat[c_] = cat.get(c_, 0) + n
        dev = {F[k]["air"]: (F[k]["dev_rec"], F[k]["dev_seg"], F[k]["dev_nseg"]) for k in F if "dev_rec" in F[k]}
        return dict(fpv=F[1]["rec"], fev=f"{F[1]['ev']}/{F[1]['n_ev']}", ev=sum(F[k]["ev"] for k in F), n_ev=sum(F[k]["n_ev"] for k in F), fa=fa, fa_h=fa / h,
                    dfa=dfa, dfa_h=dfa / dh, dh=dh, dfpr=np.mean([F[k]["dfpr"] for k in F]), dev=dev, cat=cat)
    S = {c: summ(R[c]) for c in CONFIGS}
    md = ["# Step8 v5 — 장치 경로 녹음 추가 (CNN14 임베딩 + 로지스틱 회귀, 기체 하나씩 빼는 5-fold)", "",
          "> `Tools/ml/train_v5.py`가 만든 파일. 장치 경로 = 노트북 스피커 → MAX4466 → 보드 STREAM (`30_devpath_A·B`).",
          f"> 문턱: 학습 데이터 안 교차검증에서 비드론 창 오탐 {FPR:.1%} (채택 운용점). 사건·클립·구간 판정은 연속 3창 중 2창.", "",
          "| 설정 | 공개: FPV 창 재현율 | 공개: FPV 사건 | 공개: 사건 | 공개: 오탐/시간 | 장치: FPV 창 재현율 | 장치: FPV 20 s 구간 검출 | 장치: Mini3 / Air3 창 재현율 | 장치: 오탐/시간 (ESC 클립) | 장치: 창 오탐률 |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for c in CONFIGS:
        s = S[c]
        fp = s["dev"].get("Fp", (np.nan, 0, 0))
        oth = " / ".join(f"{s['dev'][a][0]:.2f}" if a in s["dev"] else "-" for a in ("3p", "A3"))
        md.append(f"| {c} | {s['fpv']:.2f} | {s['fev']} | {s['ev']}/{s['n_ev']} | {s['fa_h']:.2f} ({s['fa']}) | {fp[0]:.2f} | {fp[1]}/{fp[2]} | {oth} | "
                  f"{s['dfa_h']:.1f} ({s['dfa']}/{s['dh']:.2f} h) | {s['dfpr']:.3f} |")
    md += ["", "## 장치 경로 오탐 범주 (5 fold 합, 클립 수)", "", "| 설정 | 범주 |", "| --- | --- |"]
    for c in CONFIGS:
        md.append(f"| {c} | " + (", ".join(f"{c_} {n}" for c_, n in sorted(S[c]["cat"].items(), key=lambda kv: -kv[1])[:10]) or "없음") + " |")
    md.append("")
    open(os.path.join(t1.OUT, "v5_report.md"), "w", encoding="utf-8").write("\n".join(md))
    print("\n".join(md[5:]))


if __name__ == "__main__":
    main()
