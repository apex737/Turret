"""Step8 v3 입력: FSD50K 어려운 비드론 임베딩 (학습 전용). ml/fsd50k_fetch.py로 받은 클립을 v0과 같은 처리로.

    python ml/embed_v3.py      → DataSet/_cache/emb_v3_neg.npz

처리: 장치 FIR·↓4 → 16 kHz → 1 s 창 / 0.5 s 이동 → 파일 최대 대비 −60 dB 이하 창은 버림 (v0의 ESC 규칙) → −30 dBFS → CNN14
클립 하나가 창을 너무 많이 차지하지 않게 클립당 최대 10창 (긴 클립은 고르게 뽑음).
묶음(group) = 업로더. 같은 사람이 비슷한 장비·장소로 올린 녹음이 문턱 교차검증의 학습·검증에 갈라지지 않게.
"""
import csv, os, sys
import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, ".."))
import embed_v0 as e0
import embed_v1 as e1

BASE = os.path.join(e0.ROOT, "DataSet", "FSD50K")
OUT = os.path.join(e0.ROOT, "DataSet", "_cache", "emb_v3_neg.npz")
MAX_WIN = 10


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    emb = e1.Embedder()
    sel = list(csv.DictReader(open(os.path.join(BASE, "selected.csv"), encoding="utf-8")))
    E, C, meta, skipped = [], [], [], 0
    for k, r in enumerate(sel):
        p = os.path.join(BASE, "audio", r["fname"] + ".wav")
        if not os.path.exists(p):
            skipped += 1; continue
        x, fs = sf.read(p, dtype="float64")
        x = x.mean(axis=1) if x.ndim > 1 else x
        W = e0.windows(e1.to16(x, fs))
        if not len(W):
            skipped += 1; continue
        rms = np.sqrt(np.mean(W ** 2, axis=1))
        idx = np.flatnonzero(rms > rms.max() * 10 ** (-60 / 20))
        if len(idx) > MAX_WIN:
            idx = idx[np.linspace(0, len(idx) - 1, MAX_WIN).round().astype(int)]
        e, c = emb(W[idx]); E.append(e); C.append(c)
        meta += [(r["fname"], r["cls"], "fsd_" + r["uploader"], float(i * e0.HOP / e0.FS_M)) for i in idx]
        if k % 100 == 0:
            print(f"{k}/{len(sel)}  창 {len(meta)}")
    m = list(zip(*meta))
    np.savez_compressed(OUT, emb=np.concatenate(E), clip=np.concatenate(C), fname=np.array(m[0]), cls=np.array(m[1]),
                        group=np.array(m[2]), t=np.array(m[3]))
    print(f"비드론 창 {len(meta)}개 (클립 {len(sel) - skipped}, 건너뜀 {skipped}) → {OUT}")


if __name__ == "__main__":
    main()
