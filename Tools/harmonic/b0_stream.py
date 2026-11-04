# Tools/.venv — Step8b B0의 연속 스트림 판 (MCU harm.c의 PC 기준 구현, I3)
"""harm.c와 같은 틀로 B0를 계산한다: 재시작 뒤 첫 샘플부터 1024샘플마다 2048점 프레임, 프레임 11개 = 창 하나,
창은 프레임 6개(6144샘플 ≈ 0.49 s)마다 시작. 점수 계산은 score.py와 같고, 다른 점은 평균(DC)을 1 s 창이 아니라
프레임마다 뺀다는 것뿐이다 (MCU가 창 전체를 기다리지 않고 프레임마다 계산하기 때문).

    stream_scores(x, base) → [dict(s0, n, score, f0, rms_db, pos)]   x = MIC1 int16 값(재시작 뒤 첫 샘플부터)
"""
import numpy as np
from scipy.ndimage import median_filter

import harmonic.score as hs

NFR = 11                         # 창 하나의 프레임 수 (harm.h HARM_NFR)
WIN_HOP = 6                      # 창 시작 간격 [프레임] (HARM_WIN_HOP)
F0_MIN, F0_MAX = 40, 700         # 기본음 후보 [Hz] (HARM_F0_MIN, HARM_F0_MAX)
THR = 13.1                       # 드론 후보 문턱 (HARM_THR) = Step8b fold 문턱 5개 평균
WIN_N = hs.NFFT + (NFR - 1) * hs.HOP   # 12288


def frame_pk(seg):
    """2048샘플 한 프레임 → 빈별 pk = clip(±1빈 최대 SNR − 1, 0, CAP − 1) (1025빈)"""
    f = (seg - seg.mean()) * hs.WIN
    P = np.abs(np.fft.rfft(f)) ** 2
    floor = median_filter(P, size=hs.FLOOR_BINS, mode="nearest") / np.log(2)
    snr = P / (floor + 1e-30)
    snr = np.maximum(snr, np.maximum(np.roll(snr, 1), np.roll(snr, -1)))
    return np.clip(snr - 1.0, 0.0, hs.CAP - 1.0)


def stream_scores(x, base=0):
    """x: MIC1 샘플 (재시작 뒤 첫 샘플부터, int16 값 그대로의 float), base: x[0]의 샘플 번호 → 창 결과 목록"""
    x = np.asarray(x, float)
    c, k, ok = hs.candidates(F0_MIN, F0_MAX)
    nfr = 0 if len(x) < hs.NFFT else 1 + (len(x) - hs.NFFT) // hs.HOP
    pk = [frame_pk(x[j * hs.HOP:j * hs.HOP + hs.NFFT]) for j in range(nfr)]
    out = []
    w = 0
    while w * WIN_HOP + NFR <= nfr:
        P = np.stack(pk[w * WIN_HOP:w * WIN_HOP + NFR])
        S = np.zeros(c.size)
        for h in range(hs.H):
            S += np.where(ok[h], P[:, k[h]].sum(axis=0), 0.0)
        curve = S / NFR
        i = int(np.argmax(curve))
        seg = x[w * WIN_HOP * hs.HOP:w * WIN_HOP * hs.HOP + WIN_N]
        var = max(np.mean((seg - seg.mean()) ** 2), 1e-6)
        out.append(dict(s0=base + w * WIN_HOP * hs.HOP, n=WIN_N, score=float(curve[i]), f0=float(c[i]),
                        rms_db=float(10 * np.log10(var) - 20 * np.log10(32768)), pos=bool(curve[i] >= THR)))
        w += 1
    return out
