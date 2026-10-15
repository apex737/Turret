"""burst 녹음에서 보드 자신이 만드는 프레임 동기 간섭을 잰다 (Step5, 마이크 전원 대책 A/B 비교용).

    python board/frame_sync_noise.py quiet_eq quiet_rc

원리
  ADC 프레임(1024샘플 = 20.48 ms)마다 펌웨어가 같은 일을 한다 → 그 전류가 전원·접지로 신호에 들어가면
  모든 프레임의 같은 위치에 같은 파형이 생긴다. 프레임들을 위치별로 평균하면 잡음은 줄고 이 파형만 남는다.
  burst의 첫 프레임은 직전 프레임 처리가 없어서 간섭이 없으므로 평균에서 뺀다.

출력 (채널별)
  펄스 p-p : 프레임 시작 0~40샘플의 동기 평균 p-p [LSB]. 0에 가까울수록 좋음
  빗 선    : 48.8 Hz 배수(2~10번째) 선이 주변 바닥보다 몇 dB 위인지의 평균. 0 dB면 빗 없음
  잡음     : 프레임 동기 성분을 뺀 나머지 표준편차 [LSB]
"""
import argparse, glob, os, sys
import numpy as np
from scipy.signal import welch
from scipy.ndimage import median_filter

DUMPS = os.path.join(os.path.dirname(__file__), "..", "dumps", "step5")
FS, N = 50000, 1024
F_FRAME = FS / N                                    # 48.83 Hz


def measure(label):
    files = sorted(glob.glob(os.path.join(DUMPS, label, "b_*.npz")))
    if not files:
        sys.exit(f"녹음 없음: {os.path.join(DUMPS, label)}")
    B = np.array([np.load(f)["data"].astype(float) for f in files])          # [burst, ch, 8192]
    fr = B.reshape(len(B), B.shape[1], -1, N)[:, :, 1:, :]                   # 첫 프레임 제외
    fr = fr - fr.mean(axis=3, keepdims=True)
    sync = fr.mean(axis=(0, 2))                                              # [ch, 1024]
    pulse = np.ptp(sync[:, :40], axis=1)
    resid = (fr - sync[None, :, None, :]).std(axis=(0, 2, 3))
    x = (B - B.mean(axis=2, keepdims=True)) / 2048
    f, P = welch(x, FS, nperseg=8192, axis=2)
    L = 10 * np.log10(P.mean(axis=0) + 1e-30)
    floor = median_filter(L, size=(1, 41))
    comb = np.mean([(L - floor)[:, np.argmin(abs(f - k * F_FRAME)) - 1: np.argmin(abs(f - k * F_FRAME)) + 2].max(axis=1)
                    for k in range(2, 11)], axis=0)
    return len(B), pulse, comb, resid


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("labels", nargs="+", help="Tools/dumps/step5/ 아래 burst 폴더 이름 (재생 없는 녹음)")
    a = ap.parse_args()
    print(f"{'녹음':12s} {'burst':>5s}   {'펄스 p-p [LSB]':^22s}   {'빗 선 [dB]':^20s}   {'잡음 [LSB]':^20s}")
    for lab in a.labels:
        n, pulse, comb, resid = measure(lab)
        fmt = lambda v, p: " ".join(f"{x:6.{p}f}" for x in v)
        print(f"{lab:12s} {n:5d}   {fmt(pulse, 1)}   {fmt(comb, 1)}   {fmt(resid, 2)}")


if __name__ == "__main__":
    main()
