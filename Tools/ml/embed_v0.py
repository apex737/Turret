"""Step8 첫 모델 입력: 공개 원음 → 장치와 같은 전처리 → 1 s 창 → PANNs CNN14(16 kHz) 임베딩.

    python ml/embed_v0.py                 → DataSet/_cache/emb_v0.npz

처리 순서 (창마다)
  원음 → 50 kHz 리샘플 → frontend FIR·↓4 (MCU와 같은 계수) → 12.5 kHz → 16 kHz 리샘플 → 1.0 s 창, 0.5 s 이동
  → RMS를 -30 dBFS로 맞춤 (녹음 레벨 차이를 지름길로 쓰지 못하게) → CNN14 → 2048차원 임베딩 + AudioSet 527 점수

라벨
  drone  : hover·호버 파일은 전부 1. 통과 비행·WS는 머리 위 근처(500 Hz 이상 대역 레벨이 최대치 −20 dB 이내)만 1, 나머지 −1(불확실, 제외)
  nondrone: 0. 디지털 무음 창(ESC-50의 패딩)은 버림
"""
import csv, os, sys, warnings
from math import gcd
import numpy as np
import torch
from scipy.signal import resample_poly, butter, sosfiltfilt, lfilter
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))   # Tools/ (폴더 간 import)
from audio.to_listen import load
import preproc.frontend as fe

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
CKPT = os.path.join(ROOT, "DataSet", "_models", "Cnn14_16k_mAP=0.438.pth")
OUT = os.path.join(ROOT, "DataSet", "_cache", "emb_v0.npz")
FS_M = 16000
WIN, HOP = 16000, 8000
NEAR_DB = 20.0


def rs(x, fs_in, fs_out):
    if fs_in == fs_out:
        return x
    g = gcd(int(fs_in), int(fs_out))
    return resample_poly(x, fs_out // g, fs_in // g)


def frontend_float(x, fs):
    """MCU와 같은 FIR·↓4를 실수로 (양자화 없이). 입력은 아무 샘플레이트."""
    x50 = rs(x, fs, fe.CFG["fs_in"])
    return lfilter(fe.B, [1.0], x50)[::fe.M]                            # 12.5 kHz


def load_ckpt():
    """weights_only 안전 모드로 연다. 체크포인트에 든 numpy 배열 복원 함수만 허용 (임의 코드 실행 방지)"""
    allow = [(np._core.multiarray._reconstruct, "numpy.core.multiarray._reconstruct"), np.ndarray, np.dtype,
             (np._core.multiarray.scalar, "numpy.core.multiarray.scalar"), np.dtypes.Float64DType, np.dtypes.Int64DType]
    with torch.serialization.safe_globals(allow):
        return torch.load(CKPT, map_location="cpu", weights_only=True)


def windows(y):
    n = 1 + (len(y) - WIN) // HOP if len(y) >= WIN else 0
    return np.stack([y[i * HOP: i * HOP + WIN] for i in range(n)]) if n else np.zeros((0, WIN))


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from panns_inference.models import Cnn14          # Cnn14_16k = 같은 구조에 16 kHz 설정
    model = Cnn14(sample_rate=16000, window_size=512, hop_size=160, mel_bins=64, fmin=50, fmax=8000, classes_num=527)
    model.load_state_dict(load_ckpt()["model"])
    model.eval()
    hp = butter(4, 500, "highpass", fs=FS_M, output="sos")

    rows = list(csv.DictReader(open(os.path.join(ROOT, "data", "dataset_manifest.csv"), encoding="utf-8")))
    E, C, meta = [], [], []
    for i, r in enumerate(rows):
        fs, x = load(os.path.join(ROOT, r["path"]), int(r["channel"]) + 1)
        t0, t1 = float(r["t0"]), float(r["t1"])
        if t1 > 0:
            x = x[int(t0 * fs): int(t1 * fs)]
        x = x - x.mean()
        y = rs(frontend_float(x, fs), fe.FS_OUT, FS_M)
        W = windows(y)
        if not len(W):
            continue
        rms = np.sqrt(np.mean(W ** 2, axis=1))
        # ESC-50 클립은 5 s를 무음으로 채운 것이 많다 → 파일 최대 대비 -60 dB 이하인 창은 버림
        keep = rms > rms.max() * 10 ** (-60 / 20) if r["source"] == "esc50" else rms > 0
        band = 20 * np.log10(np.sqrt(np.mean(sosfiltfilt(hp, W, axis=1) ** 2, axis=1)) + 1e-30)
        if r["label"] == "nondrone":
            lab = np.zeros(len(W), int)
        elif r["label_rule"] == "near_only":
            lab = np.where(band >= band.max() - NEAR_DB, 1, -1)
        else:
            lab = np.ones(len(W), int)
        W = W[keep]; lab = lab[keep]; band = band[keep]
        if not len(W):
            continue
        Wn = W / np.sqrt(np.mean(W ** 2, axis=1, keepdims=True)) * 10 ** (-30 / 20)
        with torch.no_grad():
            o = model(torch.from_numpy(Wn.astype(np.float32)))
        E.append(o["embedding"].numpy()); C.append(o["clipwise_output"].numpy())
        for k in range(len(W)):
            meta.append((i, k * HOP / FS_M, lab[k], int(r["fold"]), r["event"], r["category"], r["aircraft"], r["source"], band[k]))
        if i % 100 == 0:
            print(f"{i}/{len(rows)}  창 {len(meta)}")
    m = list(zip(*meta))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    np.savez_compressed(OUT, emb=np.concatenate(E), clip=np.concatenate(C), row=np.array(m[0]), t=np.array(m[1]),
                        label=np.array(m[2]), fold=np.array(m[3]), event=np.array(m[4]), category=np.array(m[5]),
                        aircraft=np.array(m[6]), source=np.array(m[7]), band_db=np.array(m[8]))
    print(f"창 {len(meta)}개 → {OUT}")


if __name__ == "__main__":
    main()
