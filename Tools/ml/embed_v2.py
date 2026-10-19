"""Step8 v2 입력: Salford 밖의 FPV 양성 (DVIDS 영상 + Freesound) 임베딩. 학습 전용 (시험 fold는 v0과 같음).

    python ml/embed_v2.py      → DataSet/_cache/emb_v2_fpv.npz

출처 (Steps/step/Step5_공개원음_재생녹음_고조파구조.md 끝 표)
  DVIDS B-roll (공공 영역): DataSet/DVIDS_FPV*/*.mp4 → ffmpeg로 소리만 → DataSet/_extract/DVIDS_FPV*/*.wav
    사람이 들은 라벨 DataSet/_listen/FPV_candidates*/labels.csv: fpv(깨끗), mix(FPV + 말소리·잡음). no·unk는 버림
  Freesound (CC0): 524331 5인치 통과 비행 (통과 비행이라 v0과 같은 near_only 규칙), 677833 TinyHawk 2 실내 호버 (전부)
처리는 v0과 같다: 장치 FIR·↓4 → 16 kHz → 1 s 창 / 0.5 s 이동 → −30 dBFS → CNN14.
묶음(group): 영상·파일 하나 = 묶음 하나 (같은 날·같은 기종이라 독립 사건으로 세지 않음)
"""
import csv, glob, os, sys
import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, ".."))
import embed_v0 as e0
import embed_v1 as e1

DS = os.path.join(e0.ROOT, "DataSet")
LABELS = sorted(glob.glob(os.path.join(DS, "_listen", "FPV_candidates*", "labels.csv")))   # 후보 묶음마다 하나 (ml/fpv_candidates.py)
OUT = os.path.join(DS, "_cache", "emb_v2_fpv.npz")
VIDEO = {"DOD_111697845": "dvids_24meu", "DOD_111864642": "dvids_predator26", "DOD_111931131": "dvids_26meu"}


def load16(path):
    x, fs = sf.read(path, dtype="float64")
    x = x.mean(axis=1) if x.ndim > 1 else x
    return e1.to16(x, fs)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    emb = e1.Embedder()
    E, C, meta = [], [], []

    lab = [r for p in LABELS for r in csv.DictReader(open(p, encoding="utf-8-sig")) if r["label"] in ("fpv", "mix")]
    for f in sorted({r["file"] for r in lab}):
        y = load16(glob.glob(os.path.join(DS, "_extract", "*", f + ".wav"))[0])
        W = e0.windows(y)
        t = np.arange(len(W)) * e0.HOP / e0.FS_M
        sel, kind = [], []
        for r in (r for r in lab if r["file"] == f):
            m = np.flatnonzero((t >= float(r["t0"])) & (t + 1.0 <= float(r["t1"]) + 1e-6))
            sel += m.tolist(); kind += [r["label"]] * len(m)
        sel = np.array(sel)
        e, c = emb(W[sel]); E.append(e); C.append(c)
        g = VIDEO.get(f, "dvids_" + f[4:])
        meta += [(g, k, float(t[i])) for i, k in zip(sel, kind)]
        print(f"{g}: 창 {len(sel)} (fpv {kind.count('fpv')}, mix {kind.count('mix')})")

    for name, path, rule in (("fs_5demayo", os.path.join(DS, "_extract", "Freesound_FPV", "524331_5demayo.wav"), "near_only"),
                             ("fs_tinyhawk", os.path.join(DS, "Freesound_FPV", "677833__sadiquecat__tiny-hawk-2-short-flight.wav"), "all")):
        y = load16(path)
        W, l = e1.near_labels(y, rule)
        keep = l == 1
        e, c = emb(W[keep]); E.append(e); C.append(c)
        meta += [(name, "fpv", k * e0.HOP / e0.FS_M) for k in np.flatnonzero(keep)]
        print(f"{name}: 창 {keep.sum()} / {len(W)}")

    m = list(zip(*meta))
    np.savez_compressed(OUT, emb=np.concatenate(E), clip=np.concatenate(C), group=np.array(m[0]), kind=np.array(m[1]), t=np.array(m[2]))
    print(f"FPV 창 {len(meta)}개 → {OUT}")


if __name__ == "__main__":
    main()
