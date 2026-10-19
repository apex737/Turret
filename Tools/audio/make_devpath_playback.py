"""Step8 v5 재생 파일: 학습용 FPV·비드론과 장치 경로 시험용 비드론을 노트북 스피커 → 보드로 녹음하기 위한 파일.

    python audio/make_devpath_playback.py     → DataSet/_playback/30_devpath_A.wav, 30_devpath_B.wav, 30_devpath.csv

왜: 공개 원음으로 배운 모델이 스피커 → MAX4466 → 보드를 거친 FPV를 거의 못 잡는다 (장치 경로 FPV 창 재현율 0.05, 분포 이동).
    학습 데이터 일부를 같은 경로로 녹음해 학습에 넣는다.
무엇을 재생하나 (Salford·Western Sydney 시험 원음은 넣지 않는다. 그 장치 녹음은 speaker_10min이 시험으로 이미 있음)
  학습 양성  DVIDS 사람 라벨 fpv·mix 구간, Freesound 5demayo(가까운 구간), TinyHawk 전부
  학습 음성  FSD50K 비드론 220 클립 (곤충 40, 새 30, 나머지 9범주 17씩), 클립마다 가장 큰 5 s
  시험 음성  ESC-50 150 클립 (범주마다 3개, fold마다 30개) → 장치 경로 오탐/시간. 학습에는 절대 넣지 않는다
섞는 이유: 양성과 음성을 따로 녹음하면 그날 방 잡음(에어컨 등)이 "드론 표시"가 된다. 모두 무작위로 섞어 두 파일로 나눈다.
같은 처리: 100 Hz 고역 통과 → 소리 나는 부분 RMS −20 dBFS (speaker_10min과 같은 음량), 피크 −1 dBFS 이하, 20 ms 페이드, 사이 1 s 무음.
구간표: t0_s·t1_s = 재생 파일 안 구간. 양성 구간은 앞뒤 0.5 s를 더 붙여 재생하므로, "창 전체가 [t0+0.5, t1−0.5] 안"
        (embed_v1·v5 규칙) = 원래 라벨 구간 안.
"""
import csv, glob, os, sys
from math import gcd
import numpy as np
import soundfile as sf
from scipy.io import wavfile
from scipy.signal import butter, sosfiltfilt, resample_poly

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "ml")); sys.path.insert(0, os.path.join(HERE, ".."))
FS = 48000
ROOT = os.path.join(HERE, "..", "..")
DS = os.path.join(ROOT, "DataSet")
OUT = os.path.join(DS, "_playback")
ESC = os.path.join(DS, "ESC-50", "ESC-50-master")
FSD_N = {"Insect": 40, "Bird_vocalization_and_bird_call_and_bird_song": 30}    # 나머지 범주는 17
SEG_FSD = 5.0
GAP = 1.0


def read(path, t0=None, t1=None):
    x, fs = sf.read(path, dtype="float64", always_2d=True)
    x = x.mean(axis=1)
    if t0 is not None:
        x = x[max(0, int(t0 * fs)):int(t1 * fs)]
    if fs != FS:
        g = gcd(fs, FS); x = resample_poly(x, FS // g, fs // g)
    return x


HP = butter(4, 100, "highpass", fs=FS, output="sos")


def level(x):
    """100 Hz 고역 통과 → 소리 나는 50 ms 구간(최대 대비 −40 dB 이상)의 RMS를 −20 dBFS로, 피크는 −1 dBFS 이하로"""
    x = sosfiltfilt(HP, x - x.mean())
    h = int(0.05 * FS); n = max(1, len(x) // h)
    e = np.mean(x[:n * h].reshape(n, h) ** 2, axis=1) if len(x) >= h else np.array([np.mean(x ** 2)])
    act = e[e >= e.max() * 1e-4]
    g = min(10 ** (-20 / 20) / np.sqrt(np.mean(act) + 1e-20), 10 ** (-1 / 20) / (np.abs(x).max() + 1e-20))
    x = x * g
    f = np.minimum(1, np.minimum(np.arange(len(x)), np.arange(len(x))[::-1]) / (0.02 * FS))
    return x * f


def fpv_items():
    import embed_v0 as e0, embed_v1 as e1
    items = []
    lab = [r for p in sorted(glob.glob(os.path.join(DS, "_listen", "FPV_candidates*", "labels.csv")))
           for r in csv.DictReader(open(p, encoding="utf-8-sig")) if r["label"] in ("fpv", "mix")]
    for r in lab:
        path = glob.glob(os.path.join(DS, "_extract", "*", r["file"] + ".wav"))[0]
        t0, t1 = float(r["t0"]) - 0.5, float(r["t1"]) + 0.5
        items.append(dict(src="dvids", kind=r["label"], label=1, role="train", group="dvids:" + r["file"], cls="fpv",
                          fold=0, item=f"{r['file']}@{float(r['t0']):.1f}", x=read(path, max(0.0, t0), t1)))
    # Freesound 5demayo: 통과 비행이라 v0 near_only 규칙으로 고른 창들의 구간만
    p = os.path.join(DS, "_extract", "Freesound_FPV", "524331_5demayo.wav")
    y, fs = sf.read(p, dtype="float64", always_2d=True)
    W, l = e1.near_labels(e1.to16(y.mean(axis=1), fs), "near_only")
    k = np.flatnonzero(l == 1)
    t0, t1 = k.min() * e0.HOP / e0.FS_M, k.max() * e0.HOP / e0.FS_M + 1.0
    items.append(dict(src="freesound", kind="fpv", label=1, role="train", group="fs_5demayo", cls="fpv", fold=0,
                      item=f"524331@{t0:.1f}", x=read(p, max(0.0, t0 - 0.5), t1 + 0.5)))
    p = os.path.join(DS, "Freesound_FPV", "677833__sadiquecat__tiny-hawk-2-short-flight.wav")
    items.append(dict(src="freesound", kind="fpv", label=1, role="train", group="fs_tinyhawk", cls="fpv", fold=0, item="677833", x=read(p)))
    return items


def loudest(x, sec):
    n = int(sec * FS)
    if len(x) <= n:
        return x
    c = np.r_[0, np.cumsum(x ** 2)]
    st = np.arange(0, len(x) - n + 1, FS // 2)
    s = st[np.argmax(c[st + n] - c[st])]
    return x[s:s + n]


def fsd_items(rng):
    rows = list(csv.DictReader(open(os.path.join(DS, "FSD50K", "selected.csv"), encoding="utf-8")))
    items = []
    for cls in sorted({r["cls"] for r in rows}):
        c = [r for r in rows if r["cls"] == cls and os.path.exists(os.path.join(DS, "FSD50K", "audio", r["fname"] + ".wav"))]
        for r in (c[i] for i in sorted(rng.choice(len(c), min(FSD_N.get(cls, 17), len(c)), replace=False))):
            x = loudest(sosfiltfilt(HP, read(os.path.join(DS, "FSD50K", "audio", r["fname"] + ".wav"))), SEG_FSD)
            if len(x) < 2.5 * FS:
                continue
            items.append(dict(src="fsd50k", kind="neg", label=0, role="train", group="fsd_" + r["uploader"], cls=cls, fold=0,
                              item=r["fname"], x=x))
    return items


def esc_items(rng):
    rows = list(csv.DictReader(open(os.path.join(ESC, "meta", "esc50.csv"), encoding="utf-8")))
    cats = sorted({r["category"] for r in rows})
    items = []
    for ci, cat in enumerate(cats):
        for j in range(3):                                  # 범주 ci의 j번째 → fold (3ci + j) % 5 + 1 : fold마다 30 클립
            fold = (3 * ci + j) % 5 + 1
            c = [r for r in rows if r["category"] == cat and int(r["fold"]) == fold]
            r = c[rng.integers(len(c))]
            items.append(dict(src="esc50", kind="neg", label=0, role="test", group="esc_" + r["src_file"], cls=cat, fold=fold,
                              item=r["filename"], x=read(os.path.join(ESC, "audio", r["filename"]))))
    return items


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rng = np.random.default_rng(0)
    items = fpv_items() + fsd_items(rng) + esc_items(rng)
    for it in items:
        it["x"] = level(it["x"])
    order = rng.permutation(len(items))
    total = sum(len(it["x"]) / FS + GAP for it in items)
    parts, rows, acc = {"A": [], "B": []}, [], 0.0
    for i in order:
        it = items[i]
        part = "A" if acc < total / 2 else "B"
        acc += len(it["x"]) / FS + GAP
        parts[part].append(it)
    for part, its in parts.items():
        out, t = [np.zeros(int(2 * FS))], 2.0              # 앞 2 s 무음
        for k, it in enumerate(its):
            d = len(it["x"]) / FS
            rows.append(dict(part=part, idx=k, src=it["src"], kind=it["kind"], label=it["label"], role=it["role"], group=it["group"],
                             cls=it["cls"], fold=it["fold"], item=it["item"], t0_s=f"{t:.4f}", t1_s=f"{t + d:.4f}"))
            out += [it["x"], np.zeros(int(GAP * FS))]
            t += d + GAP
        x = np.concatenate(out + [np.zeros(int(2 * FS))])
        wavfile.write(os.path.join(OUT, f"30_devpath_{part}.wav"), FS, (np.clip(x, -1, 1) * 32767).astype(np.int16))
        n = {s: sum(r["src"] == s for r in rows if r["part"] == part) for s in ("dvids", "freesound", "fsd50k", "esc50")}
        print(f"30_devpath_{part}.wav  {len(x) / FS / 60:.1f}분  {n}")
    with open(os.path.join(OUT, "30_devpath.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    sec = {}
    for it in items:
        sec[it["src"]] = sec.get(it["src"], 0) + len(it["x"]) / FS
    print("재생 시간(s): " + ", ".join(f"{k} {v:.0f}" for k, v in sec.items()) + f" → {os.path.join(OUT, '30_devpath.csv')}")


if __name__ == "__main__":
    main()
