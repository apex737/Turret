"""Step8b 고조파 센서 B0 평가: Step8과 같은 시험셋에서 재현율·오탐을 재고 동결한 학습 모델(v3m)과 비교한다.

    python harmonic/eval_b0.py      → reports/step8b/b0_report.md (수치만, 판정은 Steps/Step8b.md), 창별 점수 DataSet/_cache/b0_scores.npz

시험셋 (Step8과 같은 창: 1 s 창, 0.5 s 이동, 같은 시각)
  공개 원음  emb_v0 캐시의 창 목록 (Salford·WS 드론 + ESC-50, 기체 하나씩 빼는 5-fold). 원음 → 장치 FIR·↓4 → 12.5 kHz
  장치 경로  speaker_10min 드론 구간 (emb_v1_dev와 같은 창), devpath ESC-50 시험 창 (emb_v5_dev)
  배경       quiet_10min, fan_10min(455 s까지), doa_bg + doa_bg2 (에어컨), devpath 재생 전·후 (스피커 쉼)
문턱: fold k는 나머지 fold의 드론 창 재현율 0.9가 되는 점수. 장치 창은 그 기체(또는 ESC fold)의 fold 문턱을 쓴다.
조용한 창: 장치 녹음만, 보드 잡음 바닥(quiet_10min MIC1 0.5 s RMS 중앙값) + 6 dB 미만 창은 "없음".
"""
import csv, os, sys
import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, os.path.join(HERE, "..", "ml"))
import harmonic.score as hs
import embed_v0 as e0
import train_v0 as t0
from audio.to_listen import load

ROOT = os.path.join(HERE, "..", "..")
CACHE = os.path.join(ROOT, "DataSet", "_cache")
DUMPS = os.path.join(HERE, "..", "dumps", "stream")
OUT = os.path.join(ROOT, "reports", "step8b")
SCORES = os.path.join(CACHE, "b0_scores.npz")
CONFIGS = {"40 ~ 700 Hz": (40, 700), "300 ~ 700 Hz (FPV)": (300, 700)}
GATE_DB = 6.0
FS = hs.FS
CANDS = [hs.candidates(*r) for r in CONFIGS.values()]
FOLD_OF = {"Fp": 1, "3p": 2, "M3": 3, "Yn": 4, "A3": 5}
V3M = dict(fpv=0.22, ev="17/21", fa=0.77, dev_fpv=0.05, dev_seg="6/18", dev_fp=0.068, dev_fa=82, quiet=0.001, fan=0.009, ac=0.015, idle=0.394)


def scores_of(x12, ts):
    """12.5 kHz 신호에서 시각 ts[s]의 1 s 창마다 → [창, 범위] 점수, 창 RMS[dBFS]"""
    S = np.zeros((len(ts), len(CANDS))); R = np.zeros(len(ts))
    for i, t in enumerate(ts):
        s = int(round(t * FS)); w = x12[s:s + FS]
        if len(w) < FS:
            w = np.pad(w, (0, FS - len(w)))
        S[i] = [v for v, _ in hs.score(w, CANDS)]
        R[i] = 10 * np.log10(np.mean((w - w.mean()) ** 2) + 1e-20)
    return S, R


def rec12(folder, seconds=None):
    x, fs = sf.read(os.path.join(DUMPS, folder, "seg_000.wav"), dtype="float64")
    x = x[:, 0] - x[:, 0].mean()
    return x[:int(seconds * fs)] if seconds else x


def floor_db():
    x = rec12("quiet_10min"); h = int(0.5 * FS); n = len(x) // h
    return float(np.median(10 * np.log10(np.mean(x[:n * h].reshape(n, h) ** 2, axis=1))))


def public():
    z = np.load(os.path.join(CACHE, "emb_v0.npz"), allow_pickle=False)
    keep = z["label"] >= 0
    W = {k: z[k][keep] for k in ("row", "t", "label", "fold", "event", "category", "aircraft")}
    rows = list(csv.DictReader(open(os.path.join(ROOT, "data", "dataset_manifest.csv"), encoding="utf-8")))
    S = np.zeros((len(W["t"]), len(CANDS)))
    for n, r_ in enumerate(np.unique(W["row"])):
        r = rows[r_]
        fs, x = load(os.path.join(ROOT, r["path"]), int(r["channel"]) + 1)
        t0_, t1_ = float(r["t0"]), float(r["t1"])
        if t1_ > 0:
            x = x[int(t0_ * fs): int(t1_ * fs)]
        y = e0.frontend_float(x - x.mean(), fs)                                  # 12.5 kHz, 장치와 같은 대역
        m = np.flatnonzero(W["row"] == r_)
        S[m], _ = scores_of(y, W["t"][m])
        if n % 200 == 0:
            print(f"공개 원음 {n}/{len(np.unique(W['row']))}")
    W["S"] = S
    return W


def device(fl):
    """장치 경로 창: speaker_10min 시험 창, 배경 창, devpath ESC 시험 창, devpath 재생 전·후 창"""
    d = np.load(os.path.join(CACHE, "emb_v1_dev.npz"), allow_pickle=False)
    D = {k: d[k] for k in ("kind", "category", "aircraft", "t")}; off = float(d["offset"])
    src = {"speaker_10min": rec12("speaker_10min"), "device_quiet": rec12("quiet_10min"), "device_fan": rec12("fan_10min", 455),
           "device_ac": np.concatenate([rec12("doa_bg"), rec12("doa_bg2")])}
    D["S"] = np.zeros((len(D["t"]), len(CANDS))); D["R"] = np.zeros(len(D["t"]))
    for c, x in src.items():
        m = np.flatnonzero(D["category"] == c)
        D["S"][m], D["R"][m] = scores_of(x, D["t"][m])
    D["gate"] = D["R"] - fl >= GATE_DB
    v = np.load(os.path.join(CACHE, "emb_v5_dev.npz"), allow_pickle=False)
    V = {k: v[k] for k in ("part", "idx", "role", "fold", "t")}
    m = V["role"] == "test"; V = {k: a[m] for k, a in V.items()}
    V["S"] = np.zeros((len(V["t"]), len(CANDS))); V["R"] = np.zeros(len(V["t"]))
    import embed_v5 as e5
    from audio.to_listen import load as ld
    idle_S, idle_R = [], []
    for part in np.unique(V["part"]):
        x = rec12(f"devpath_{part}")
        m = np.flatnonzero(V["part"] == part)
        V["S"][m], V["R"][m] = scores_of(x, V["t"][m])
        x12, _, fs12 = e5.recording(f"devpath_{part}")
        o, drift, _, _ = e5.align(x12.mean(axis=1), fs12, part)
        fs, p = ld(os.path.join(e5.PLAY, f"30_devpath_{part}.wav"), 1)
        end = o + len(p) / fs * (1 + drift)
        ts = np.arange(0, len(x) / FS - 1.0, 0.5)
        ts = ts[(ts + 1.0 <= o - 0.5) | (ts >= end + 0.5)]
        s_, r_ = scores_of(x, ts); idle_S.append(s_); idle_R.append(r_)
    V["gate"] = V["R"] - fl >= GATE_DB
    I = {"S": np.concatenate(idle_S), "R": np.concatenate(idle_R)}; I["gate"] = I["R"] - fl >= GATE_DB
    return D, off, V, I


def evaluate(P, D, off, V, I, j):
    thr = {k: np.quantile(P["S"][(P["label"] == 1) & (P["fold"] != k), j], 0.1) for k in range(1, 6)}
    ev, fa, hours, rec = {}, 0, 0.0, {}
    for k in range(1, 6):
        te = P["fold"] == k; s = P["S"][te, j] >= thr[k]
        y, ro, tt, evn = P["label"][te], P["row"][te], P["t"][te], P["event"][te]
        rec[k] = float(np.mean(s[y == 1]))
        for r_ in np.unique(ro[y == 1]):
            mm = (y == 1) & (ro == r_)
            ev[evn[mm][0]] = ev.get(evn[mm][0], False) or t0.two_of_three(s[mm][np.argsort(tt[mm])])
        for r_ in np.unique(ro[y == 0]):
            mm = (y == 0) & (ro == r_)
            hours += (0.5 * mm.sum() + 0.5) / 3600; fa += t0.two_of_three(s[mm][np.argsort(tt[mm])])
    out = dict(rec=rec, fpv=rec[1], ev=f"{sum(ev.values())}/{len(ev)}", ev_rate=np.mean(list(ev.values())), fa_h=fa / hours, fa=fa)
    # 장치: speaker_10min 시험 창 (Step8과 같은 창 선택), 그 기체 fold의 문턱
    ph = (D["t"] - off) % 20.0
    for air in ("Fp", "3p", "A3"):
        m = (D["kind"] == "test") & (D["aircraft"] == air) & (ph >= 1.5) & (ph + 1.0 <= 18.5)
        hit = D["S"][m, j] >= thr[FOLD_OF[air]]
        out[f"dev_{air}"] = float(np.mean(hit & D["gate"][m])); out[f"dev_{air}_nogate"] = float(np.mean(hit))
        if air == "Fp":
            seg = np.floor((D["t"][m] - off) / 20).astype(int); hg = hit & D["gate"][m]
            out["dev_seg"] = f"{sum(t0.two_of_three(hg[seg == q][np.argsort(D['t'][m][seg == q])]) for q in np.unique(seg))}/{len(np.unique(seg))}"
    # 장치 경로 ESC (fold k 클립은 fold k 문턱)
    fp = np.array([(V["S"][i, j] >= thr[int(V["fold"][i])]) and V["gate"][i] for i in range(len(V["t"]))])
    clip = np.char.add(V["part"], V["idx"].astype(str)); nfa = 0; hrs = 0.0
    for c in np.unique(clip):
        mm = clip == c; hrs += (0.5 * mm.sum() + 0.5) / 3600; nfa += t0.two_of_three(fp[mm][np.argsort(V["t"][mm])])
    out.update(dev_fp=float(fp.mean()), dev_fa_h=nfa / hrs, dev_fa=nfa)
    # 배경: 다섯 fold 문턱 평균
    for c, key in (("device_quiet", "quiet"), ("device_fan", "fan"), ("device_ac", "ac")):
        m = D["category"] == c
        out[key] = float(np.mean([np.mean((D["S"][m, j] >= thr[k]) & D["gate"][m]) for k in range(1, 6)]))
    out["idle"] = float(np.mean([np.mean((I["S"][:, j] >= thr[k]) & I["gate"]) for k in range(1, 6)]))
    out["thr"] = thr
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    fl = floor_db()
    P = public()
    D, off, V, I = device(fl)
    np.savez_compressed(SCORES, fl=fl, off=off, **{f"P_{k}": v for k, v in P.items()}, **{f"D_{k}": v for k, v in D.items()},
                        **{f"V_{k}": v for k, v in V.items()}, **{f"I_{k}": v for k, v in I.items()})   # curve_b0.py가 다시 씀
    R = {name: evaluate(P, D, off, V, I, j) for j, name in enumerate(CONFIGS)}
    pc = lambda v: f"{v:.1%}"
    md = ["# Step8b 고조파 센서 B0 — Step8과 같은 시험셋", "",
          "> `Tools/harmonic/eval_b0.py`가 만든 파일. 수치만 적는다 (판정은 Steps/Step8b.md).",
          f"> 문턱 = 나머지 fold의 드론 창 재현율 0.9. 장치 창은 보드 잡음 바닥({fl:.1f} dBFS) + {GATE_DB:.0f} dB 미만이면 '없음'. "
          "v3m = 동결한 학습 모델 (Step8 채택 운용점).", "",
          "| 항목 | " + " | ".join(f"B0 {n}" for n in CONFIGS) + " | v3m (학습) |", "|---|" + "---|" * (len(CONFIGS) + 1)]
    rows = [("공개: 사건 검출 (21)", lambda r: r["ev"], V3M["ev"]),
            ("공개: FPV 창 재현율", lambda r: f"{r['fpv']:.2f}", f"{V3M['fpv']:.2f}"),
            ("공개: 기체별 창 재현율 (Fp / 3p / M3 / Yn / A3)", lambda r: " / ".join(f"{r['rec'][k]:.2f}" for k in range(1, 6)), "0.22 / — / — / — / —"),
            ("공개: ESC-50 오탐/시간 (클립)", lambda r: f"{r['fa_h']:.1f} ({r['fa']})", f"{V3M['fa']}"),
            ("장치: FPV 창 재현율 (조용한 창 규칙 / 없이)", lambda r: f"{r['dev_Fp']:.2f} / {r['dev_Fp_nogate']:.2f}", f"{V3M['dev_fpv']:.2f}"),
            ("장치: FPV 20 s 구간 검출", lambda r: r["dev_seg"], V3M["dev_seg"]),
            ("장치: Mini3 / Air3 창 재현율", lambda r: f"{r['dev_3p']:.2f} / {r['dev_A3']:.2f}", "0.06 / 0.01"),
            ("장치: ESC 창 오탐률", lambda r: pc(r["dev_fp"]), pc(V3M["dev_fp"])),
            ("장치: ESC 오탐/시간 (클립)", lambda r: f"{r['dev_fa_h']:.0f} ({r['dev_fa']})", f"{V3M['dev_fa']} (12)"),
            ("배경 창 오탐률: 조용함 / 선풍기 / 에어컨", lambda r: f"{pc(r['quiet'])} / {pc(r['fan'])} / {pc(r['ac'])}", f"{pc(V3M['quiet'])} / {pc(V3M['fan'])} / {pc(V3M['ac'])}"),
            ("배경 창 오탐률: devpath 재생 전·후", lambda r: pc(r["idle"]), pc(V3M["idle"]))]
    for name, f, v in rows:
        md.append(f"| {name} | " + " | ".join(f(R[n]) for n in CONFIGS) + f" | {v} |")
    md += ["", "문턱 (fold 1 ~ 5): " + "; ".join(f"{n}: " + ", ".join(f"{R[n]['thr'][k]:.2f}" for k in range(1, 6)) for n in CONFIGS), ""]
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, "b0_report.md"); open(p, "w", encoding="utf-8").write("\n".join(md))
    print("\n".join(md[5:])); print(f"→ {p}")


if __name__ == "__main__":
    main()
