"""Step8b 고조파 점수 B0 (학습 없음). 12.5 kHz PCM의 1 s 창 하나 → 점수와 기본음.

점수 S(f0): 164 ms 프레임(2048점, Hann, 절반 겹침)마다
  1. 파워 스펙트럼 P, 바닥 = 이웃 약 200 Hz의 중앙값 (선은 좁아서 바닥에 섞이지 않는다)
  2. SNR = P / 바닥, 빗살마다 ±1칸 허용 (선이 칸 사이에 걸칠 때)
  3. 고조파 1 ~ H번 자리의 (SNR − 1)을 CAP − 1에서 자르고 더한다 → 잡음만이면 0 근처
프레임 평균 곡선의 최댓값이 창의 점수, 그 f0가 기본음.
이웃 대비 비율이라 스피커·마이크처럼 주파수에 따라 완만하게 변하는 이득은 선과 바닥에 같이 곱해져 상쇄된다 (기대).
H = 4: DJI FPV는 쓸 만한 고조파가 4개 (Step5 harmonics.md). 모든 f0에서 같은 개수를 써야 점수가 비교된다.
"""
import numpy as np
from scipy.ndimage import median_filter

FS = 12500
NFFT, HOP = 2048, 1024
H, CAP = 4, 10.0
F_MAX = 5000.0                  # f_use (Step5pre)
WIN = np.hanning(NFFT)
DF = FS / NFFT
FLOOR_BINS = int(round(200 / DF)) | 1


def snr_frames(x):
    n = 1 + (len(x) - NFFT) // HOP
    F = np.stack([x[i * HOP:i * HOP + NFFT] * WIN for i in range(n)])
    P = np.abs(np.fft.rfft(F, axis=1)) ** 2
    floor = median_filter(P, size=(1, FLOOR_BINS), mode="nearest") / np.log(2)     # 중앙값 → 평균 환산 (지수 분포)
    snr = P / (floor + 1e-30)
    return np.maximum(snr, np.maximum(np.roll(snr, 1, axis=1), np.roll(snr, -1, axis=1)))


def candidates(fmin, fmax, step=1.0):
    c = np.arange(fmin, fmax + 1e-9, step)
    k = np.stack([np.round(h * c / DF).astype(int) for h in range(1, H + 1)])        # [H, 후보]
    ok = (np.arange(1, H + 1)[:, None] * c[None, :]) <= F_MAX
    return c, k, ok


def score(x, cands):
    """x: 1 s (12500샘플), cands: candidates() 목록 → [(점수, 기본음 Hz), ...] (후보 범위마다)"""
    pk = np.clip(snr_frames(np.asarray(x, float) - np.mean(x)) - 1.0, 0.0, CAP - 1.0)  # [프레임, bin]
    out = []
    for c, k, ok in cands:
        S = np.zeros((pk.shape[0], c.size))
        for h in range(H):
            S += np.where(ok[h], pk[:, k[h]], 0.0)
        curve = S.mean(axis=0)
        i = int(np.argmax(curve))
        out.append((float(curve[i]), float(c[i])))
    return out
