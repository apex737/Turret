"""Step8 v1 입력: 증강 양성 + 장치 잡음 음성 + 장치 경로 시험 임베딩. 원본 창은 v0 캐시(emb_v0.npz)를 그대로 쓴다.

    python ml/embed_v1.py                 → DataSet/_cache/emb_v1_aug.npz, emb_v1_dev.npz  (약 10분, CPU)

증강 그룹 (드론 원본 하나마다 그룹별 1개씩, 무엇이 효과가 있는지 따로 보려고 나눔)
  S  속도 ±5~20%                       → 회전수·기체 크기
  D  통과 비행 (호버 녹음만)            → 도플러 + 거리 변화 (v 8~20 m/s, 최근접 5~20 m)
  E  주파수 응답 변화                    → 녹음기·마이크·거리 (기울기 ±6 dB, 봉우리/골 ±4 dB)
  N  배경 혼합 SNR 0~20 dB               → ESC-50(원본 기체와 같은 fold) 또는 장치 잡음
  A  S + D(호버면) + E + N
물리 순서: 속도·도플러는 원음에 → 장치 FIR·↓4 → 16 kHz → 주파수 응답·배경 혼합 (선형이라 전처리 뒤에 섞어도 같음)
라벨: v0과 같은 규칙 (통과 비행은 깨끗한 증강 신호의 500 Hz 이상 레벨이 최대 −20 dB 이내인 창만 양성)

누수 방지: 기체 a의 증강본은 a가 시험인 fold에서 쓰지 않는다 (train_v1.py). 그 증강본에 섞는 ESC 잡음은 ESC fold a에서만
고르므로, 증강본이 학습에 쓰이는 fold k(≠a)의 시험 ESC(fold k)와 겹치지 않는다.

장치 녹음 (Tools/dumps/stream, MIC1 채널)
  음성(학습 전용): quiet_10min, fan_10min(선풍기 켜진 455 s), doa_bg·doa_bg2(에어컨) → 보드 자체 잡음을 드론으로 착각하지 않게
  시험: speaker_10min (노트북 스피커로 20_drones_10min.wav 재생 → 보드 녹음). 재생 시작은 크기 포락선 상관으로 찾는다
"""
import csv, os, sys
import numpy as np
import soundfile as sf
import torch
from scipy.signal import butter, sosfiltfilt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, ".."))
import embed_v0 as e0
import augment as ag
from audio.to_listen import load
import preproc.frontend as fe

ROOT = e0.ROOT
DUMPS = os.path.join(HERE, "..", "dumps", "stream")
PLAY = os.path.join(ROOT, "DataSet", "_playback")
OUT_AUG = os.path.join(ROOT, "DataSet", "_cache", "emb_v1_aug.npz")
OUT_DEV = os.path.join(ROOT, "DataSet", "_cache", "emb_v1_dev.npz")
FS = e0.FS_M
GROUPS = ("S", "D", "E", "N", "A")
CLIP_AIR = {"11_fpv_ev1": "Fp", "12_fpv_ev2": "Fp", "13_fpv_ev3": "Fp", "14_mini3pro_hover": "3p", "15_air3": "A3"}
HP = butter(4, 500, "highpass", fs=FS, output="sos")


def to16(x, fs):
    return e0.rs(e0.frontend_float(x - x.mean(), fs), fe.FS_OUT, FS)


def pcm16(folder, seconds=None, ch=0):
    """장치 STREAM 녹음(12.5 kHz, 이미 전처리된 PCM) → 16 kHz"""
    x, fs = sf.read(os.path.join(DUMPS, folder, "seg_000.wav"), dtype="float64")
    x = x[:, ch] if x.ndim > 1 else x
    if seconds:
        x = x[:int(seconds * fs)]
    return e0.rs(x - x.mean(), fs, FS)


def band_db(W):
    return 20 * np.log10(np.sqrt(np.mean(sosfiltfilt(HP, W, axis=1) ** 2, axis=1)) + 1e-30)


def near_labels(clean16, rule):
    W = e0.windows(clean16)
    if not len(W):
        return W, np.zeros(0, int)
    b = band_db(W)
    lab = np.where(b >= b.max() - e0.NEAR_DB, 1, -1) if rule == "near_only" else np.ones(len(W), int)
    return W, lab


class Embedder:
    def __init__(self):
        from panns_inference.models import Cnn14
        self.m = Cnn14(sample_rate=16000, window_size=512, hop_size=160, mel_bins=64, fmin=50, fmax=8000, classes_num=527)
        self.m.load_state_dict(e0.load_ckpt()["model"]); self.m.eval()

    def __call__(self, W):
        Wn = W / (np.sqrt(np.mean(W ** 2, axis=1, keepdims=True)) + 1e-30) * 10 ** (-30 / 20)   # v0과 같은 −30 dBFS
        E, C = [], []
        with torch.no_grad():
            for i in range(0, len(Wn), 64):
                o = self.m(torch.from_numpy(Wn[i:i + 64].astype(np.float32)))
                E.append(o["embedding"].numpy()); C.append(o["clipwise_output"].numpy())
        return np.concatenate(E), np.concatenate(C)


class NoiseBank:
    """배경 잡음: ESC-50 fold별 클립(전처리 후 16 kHz) + 장치 잡음"""
    def __init__(self, rows, device):
        self.esc = {}
        for r in rows:
            if r["source"] == "esc50":
                self.esc.setdefault(int(r["fold"]), []).append(r["path"])
        self.device = device

    def esc_noise(self, fold, n, rng):
        out = np.zeros(0)
        while len(out) < n:
            fs, x = load(os.path.join(ROOT, rng.choice(self.esc[fold])), 1)
            y = to16(x, fs)
            if np.sqrt(np.mean(y ** 2)) > 1e-5:              # 무음 클립은 건너뜀
                out = np.concatenate([out, y])
        return out[:n]

    def pick(self, fold, n, rng):
        if rng.random() < 0.5:
            return self.esc_noise(fold, n, rng), "esc"
        d = self.device[rng.integers(len(self.device))]
        s = rng.integers(0, max(1, len(d) - n))
        return d[s:s + n], "device"


def augment_row(r, x, fs, g, bank, rng):
    """원본 하나 → 그룹 g의 (깨끗한 증강 드론, 섞인 최종 신호, 설명)"""
    hover = r["op"] == "hover"
    info = []
    if g in ("S", "A"):
        f = rng.uniform(0.80, 0.95) if rng.random() < 0.5 else rng.uniform(1.05, 1.20)
        x = ag.speed(x, fs, f); info.append(f"speed {f:.2f}")
    if g in ("D", "A") and hover:
        v, d = rng.uniform(8, 20), rng.uniform(5, 20)
        x, _ = ag.flyby(x, fs, v, d); info.append(f"flyby v{v:.0f} d{d:.0f}")
    y = to16(x, fs)
    if g in ("E", "A"):
        y = ag.random_eq(y, FS, rng); info.append("eq")
    clean = y
    if g in ("N", "A"):
        _, lab = near_labels(clean, r["label_rule"])
        ref = np.zeros(len(clean), bool)                    # SNR 기준 = 확실한 양성 창 구간
        for k in np.flatnonzero(lab == 1):
            ref[k * e0.HOP:k * e0.HOP + e0.WIN] = True
        snr = rng.uniform(0, 20)
        noise, kind = bank.pick(int(r["fold"]), len(clean), rng)
        y = ag.mix(clean, noise, snr, ref); info.append(f"{kind} {snr:.0f} dB")
    return clean, y, ", ".join(info)


def playback_offset(rec12, fs12):
    """speaker_10min 녹음에서 재생이 시작된 시각 [s]: 50 ms 크기 포락선의 정규화 상관"""
    fs, p = load(os.path.join(PLAY, "20_drones_10min.wav"), 1)
    ref = e0.frontend_float(p, fs)                          # 12.5 kHz
    def env(z, f):
        h = int(0.05 * f); n = len(z) // h
        return 10 * np.log10(np.mean(z[:n * h].reshape(n, h) ** 2, axis=1) + 1e-12)
    a, b = env(rec12, fs12), env(ref, fe.FS_OUT)
    a = (a - a.mean()) / a.std(); b = (b - b.mean()) / b.std()
    lags = range(0, min(len(a) - len(b) + 1, 1200))         # 0 ~ 60 s
    c = [np.mean(a[l:l + len(b)] * b) for l in lags]
    return int(np.argmax(c)) * 0.05, float(np.max(c))


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rng = np.random.default_rng(1)
    emb = Embedder()
    rows = list(csv.DictReader(open(os.path.join(ROOT, "data", "dataset_manifest.csv"), encoding="utf-8")))

    # 장치 잡음 (음성 + 배경 혼합용)
    dev = {"device_quiet": pcm16("quiet_10min"), "device_fan": pcm16("fan_10min", 455), "device_ac": np.concatenate([pcm16("doa_bg"), pcm16("doa_bg2")])}
    bank = NoiseBank(rows, list(dev.values()))

    E, Cl, meta = [], [], []
    drone = [(i, r) for i, r in enumerate(rows) if r["label"] == "drone"]
    for n, (i, r) in enumerate(drone):
        fs, x = load(os.path.join(ROOT, r["path"]), int(r["channel"]) + 1)
        t0, t1 = float(r["t0"]), float(r["t1"])
        if t1 > 0:
            x = x[int(t0 * fs): int(t1 * fs)]
        x = x - x.mean()
        for g in GROUPS:
            if g == "D" and r["op"] != "hover":
                continue
            clean, y, info = augment_row(r, x, fs, g, bank, rng)
            _, lab = near_labels(clean, r["label_rule"])
            W = e0.windows(y)[:len(lab)]
            keep = lab[:len(W)] == 1
            if not keep.any():
                continue
            e, c = emb(W[keep])
            E.append(e); Cl.append(c)
            for k in np.flatnonzero(keep):
                meta.append((i, g, k * e0.HOP / FS, int(r["fold"]), r["event"], r["aircraft"], r["op"], info))
        print(f"증강 {n + 1}/{len(drone)} {r['event']}  누적 창 {len(meta)}")
    m = list(zip(*meta))
    np.savez_compressed(OUT_AUG, emb=np.concatenate(E), clip=np.concatenate(Cl), row=np.array(m[0]), group=np.array(m[1]),
                        t=np.array(m[2]), fold=np.array(m[3]), event=np.array(m[4]), aircraft=np.array(m[5]), op=np.array(m[6]),
                        info=np.array(m[7]))
    print(f"증강 창 {len(meta)}개 → {OUT_AUG}")

    # 장치 음성 (학습 전용): 녹음마다 최대 200창
    DE, DC, dmeta = [], [], []
    for cat, y in dev.items():
        W = e0.windows(y)
        sel = np.sort(rng.choice(len(W), min(200, len(W)), replace=False))
        e, c = emb(W[sel]); DE.append(e); DC.append(c)
        dmeta += [("neg", cat, "", float(k * e0.HOP / FS)) for k in sel]

    # 장치 경로 시험: speaker_10min
    x12, fs12 = sf.read(os.path.join(DUMPS, "speaker_10min", "seg_000.wav"), dtype="float64")
    off, corr = playback_offset(x12.mean(axis=1), fs12)
    print(f"speaker_10min 재생 시작 {off:.2f} s (포락선 상관 {corr:.2f})")
    tl = list(csv.DictReader(open(os.path.join(PLAY, "20_drones_10min.csv"), encoding="utf-8")))
    y = e0.rs(x12[:, 0] - x12[:, 0].mean(), fs12, FS)
    W = e0.windows(y)
    t = np.arange(len(W)) * e0.HOP / FS
    lab = []
    for ts in t:
        a = ""
        for s in tl:                                         # 창 전체가 한 원음 구간 안 (경계 0.5 s 여유)
            if off + float(s["t0_s"]) + 0.5 <= ts and ts + 1.0 <= off + float(s["t1_s"]) - 0.5:
                a = CLIP_AIR[s["name"]]
        lab.append(a)
    lab = np.array(lab); keep = lab != ""
    e, c = emb(W[keep]); DE.append(e); DC.append(c)
    dmeta += [("test", "speaker_10min", a, float(ts)) for a, ts in zip(lab[keep], t[keep])]
    m = list(zip(*dmeta))
    np.savez_compressed(OUT_DEV, emb=np.concatenate(DE), clip=np.concatenate(DC), kind=np.array(m[0]), category=np.array(m[1]),
                        aircraft=np.array(m[2]), t=np.array(m[3]), offset=off, offset_corr=corr)
    print(f"장치 음성 {sum(k == 'neg' for k in m[0])}창, 장치 시험 {sum(k == 'test' for k in m[0])}창 → {OUT_DEV}")


if __name__ == "__main__":
    main()
