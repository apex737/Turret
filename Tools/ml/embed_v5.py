"""Step8 v5 입력: 장치 경로 녹음(30_devpath_A·B 재생 → 보드 STREAM) 임베딩.

    python ml/embed_v5.py      (Tools/dumps/stream/devpath_A, devpath_B 필요) → DataSet/_cache/emb_v5_dev.npz

정렬: 재생 파일과 녹음의 50 ms 크기 포락선 상관으로 시작 시각을 찾고(embed_v1과 같은 방법), 앞·뒤 4분을 10 ms 포락선으로
      다시 맞춰 두 시계의 속도 차이(drift)까지 보정한다. 녹음 시각 = 시작 + 재생 시각 × (1 + drift).
라벨: 창(1 s) 전체가 [t0 + 0.5, t1 − 0.5] 안에 있는 창만 그 구간의 라벨 (구간표 30_devpath.csv, embed_v1과 같은 규칙).
      유실 구간(세그먼트 사이)에 걸친 창은 버린다. 채널은 MIC1 (embed_v1 speaker_10min과 같음).
묶음(group): 원본과 같은 이름 (DVIDS 영상, FSD50K 업로더) → 같은 소리의 원본·장치 녹음이 문턱 교차검증에서 갈라지지 않게.
"""
import csv, json, os, sys
import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, ".."))
import embed_v0 as e0
import embed_v1 as e1
import embed_v2 as e2
from audio.to_listen import load
import preproc.frontend as fe

PLAY = e1.PLAY
OUT = os.path.join(e0.ROOT, "DataSet", "_cache", "emb_v5_dev.npz")
PARTS = ("A", "B")


def recording(folder):
    """세그먼트들을 start_sample 기준으로 한 줄에 놓는다 (유실 구간은 0, valid=False). 12.5 kHz, (n, 3)"""
    d = os.path.join(e1.DUMPS, folder)
    segs = json.load(open(os.path.join(d, "summary.json"), encoding="utf-8"))["segments"]
    s0 = segs[0]["start_sample"]
    n = segs[-1]["start_sample"] + segs[-1]["samples"] - s0
    x = np.zeros((n, 3)); valid = np.zeros(n, bool)
    for s in segs:
        y, fs = sf.read(os.path.join(d, s["file"]), dtype="float64", always_2d=True)
        a = s["start_sample"] - s0
        x[a:a + len(y)] = y; valid[a:a + len(y)] = True
    return x, valid, fs


def env(z, f, sec):
    h = int(sec * f); n = len(z) // h
    e = 10 * np.log10(np.mean(z[:n * h].reshape(n, h) ** 2, axis=1) + 1e-12)
    return (e - e.mean()) / (e.std() + 1e-12)


def best_lag(a, b, lags):
    c = [np.mean(a[l:l + len(b)] * b) if 0 <= l and l + len(b) <= len(a) else -9 for l in lags]
    i = int(np.argmax(c))
    return lags[i], float(c[i])


def align(rec12, fs12, part):
    fs, p = load(os.path.join(PLAY, f"30_devpath_{part}.wav"), 1)
    ref = e0.frontend_float(p, fs)                           # 12.5 kHz, 녹음과 같은 전처리
    a, b = env(rec12, fs12, 0.05), env(ref, fe.FS_OUT, 0.05)
    lag, corr = best_lag(a, b, list(range(0, max(1, min(len(a) - len(b) + 1, 2400)))))   # 0 ~ 120 s
    off = lag * 0.05
    a, b = env(rec12, fs12, 0.01), env(ref, fe.FS_OUT, 0.01)
    L = int(240 / 0.01)
    fine = []
    for c0 in (200, len(b) - L - 200):                       # 재생 앞 4분, 뒤 4분 (앞뒤 2 s 무음 제외)
        l, c = best_lag(a, b[c0:c0 + L], list(range(int(off / 0.01) + c0 - 100, int(off / 0.01) + c0 + 101)))
        fine.append(((l - c0) * 0.01, c, c0 * 0.01 + 120))   # (시작 시각 추정, 상관, 구간 중심 재생 시각)
    (o1, c1, m1), (o2, c2, m2) = fine
    drift = (o2 - o1) / (m2 - m1)
    off = o1 - m1 * drift
    return off, drift, corr, min(c1, c2)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    emb = e1.Embedder()
    tl = list(csv.DictReader(open(os.path.join(PLAY, "30_devpath.csv"), encoding="utf-8")))
    E, C, meta = [], [], []
    for part in PARTS:
        x12, valid, fs12 = recording(f"devpath_{part}")
        off, drift, corr, corr_f = align(x12.mean(axis=1), fs12, part)
        print(f"devpath_{part}: 녹음 {len(x12) / fs12 / 60:.1f}분, 유실 {np.mean(~valid) * 100:.2f}%, 재생 시작 {off:.2f} s, "
              f"시계 차이 {drift * 1e6:+.0f} ppm, 포락선 상관 {corr:.2f} / 정밀 {corr_f:.2f}")
        y = e0.rs(x12[:, 0] - x12[:, 0].mean(), fs12, e0.FS_M)
        W = e0.windows(y)
        t = np.arange(len(W)) * e0.HOP / e0.FS_M
        vi = np.r_[0, np.cumsum(~valid)]                     # 창 구간 [t, t+1]에 유실 샘플이 있으면 버림
        bad = vi[np.minimum(((t + 1.0) * fs12).astype(int), len(valid))] - vi[np.minimum((t * fs12).astype(int), len(valid))] > 0
        rows = [r for r in tl if r["part"] == part]
        a = off + np.array([float(r["t0_s"]) for r in rows]) * (1 + drift) + 0.5
        b = off + np.array([float(r["t1_s"]) for r in rows]) * (1 + drift) - 0.5
        j = np.searchsorted(a, t, side="right") - 1          # 창 시작 이전에 시작한 마지막 구간
        ok = (j >= 0) & ~bad
        ok[ok] &= t[ok] + 1.0 <= b[j[ok]]
        sel = np.flatnonzero(ok)
        e, c = emb(W[sel]); E.append(e); C.append(c)
        for i in sel:
            r = rows[j[i]]
            g = r["group"]
            if g.startswith("dvids:"):
                f = g[6:]; g = e2.VIDEO.get(f, "dvids_" + f[4:])   # embed_v2와 같은 묶음 이름
            meta.append((part, int(r["idx"]), int(r["label"]), r["role"], r["kind"], g, r["cls"], int(r["fold"]), r["item"], float(t[i])))
        n = {k: sum(1 for i in sel if rows[j[i]]["src"] == k) for k in ("dvids", "freesound", "fsd50k", "esc50")}
        print(f"  창 {len(sel)}  {n}")
    m = list(zip(*meta))
    np.savez_compressed(OUT, emb=np.concatenate(E), clip=np.concatenate(C), part=np.array(m[0]), idx=np.array(m[1]), label=np.array(m[2]),
                        role=np.array(m[3]), kind=np.array(m[4]), group=np.array(m[5]), cls=np.array(m[6]), fold=np.array(m[7]),
                        item=np.array(m[8]), t=np.array(m[9]))
    print(f"장치 경로 창 {len(meta)}개 → {OUT}")


if __name__ == "__main__":
    main()
