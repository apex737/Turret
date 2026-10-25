"""Step8b B1 특징: 1 s 창(12.5 kHz) → B0 점수 + 정수배 정확도 · 지속 · 기본음 출렁임.

  B0 점수 S, 기본음 f0: harmonic/score.py와 같다 (164 ms 조각 평균 곡선의 최댓값, 후보 40 ~ 700 Hz).
  조각마다 기본음 다시 찾기: 창 기본음의 ±5% 안에서 그 조각의 고조파 점수가 가장 큰 값 f0_t, 그 점수 S_t.
  지속 = S_t ≥ 0.5 · max(S_t)인 조각의 비율 (그 창에서 가장 뚜렷한 조각의 절반 이상). 문 두드림·시계 소리처럼 짧은 소리는 몇 조각에서만 뚜렷하다.
  출렁임 = 그 조각들의 (최대 f0_t − 최소 f0_t) ÷ f0. 울음소리처럼 기본음이 크게 움직이면 크다.
       도플러만으로는 머리 위에서 1 s에 34 Hz(520 Hz의 6.6%)까지 움직인다 (f0 · v² / (c · d), 15 m/s, 10 m).
  정수배 정확도 = 조각마다 k번째 고조파 봉우리(k = 1 ~ 4)를 k · f0_t 근처에서 찾아 포물선 보간으로 위치 f_k를 읽고,
       f0* = Σ w·k·f_k / Σ w·k² (가중 최소제곱, w = 봉우리 SNR, 상한 10)로 맞춘 뒤 Σ w·|f_k − k·f0*| / Σ w [Hz].
       봉우리 SNR ≥ 3인 고조파가 2개 이상인 조각만 쓰고, 조각들의 중앙값. 쓸 조각이 없으면 inf.
       찾는 범위는 ±(1 + 0.25·k)칸: 머리 위 통과 때 4번째 고조파가 164 ms 안에서 약 22 Hz(3.7칸) 움직인다.
       고조파는 함께 움직이므로(모두 k배) 조각 안에서 번져도 봉우리 중심끼리는 정수배를 유지한다. 공진이 만든 가짜 선은 아니다.
"""
import numpy as np
from scipy.ndimage import median_filter
import harmonic.score as hs

CAND = hs.candidates(40, 700)
REFINE = np.arange(0.95, 1.05 + 1e-9, 0.002)
NAMES = ("S", "f0", "dev_hz", "persist", "glide")


def frames(x):
    x = np.asarray(x, float) - np.mean(x)
    n = 1 + (len(x) - hs.NFFT) // hs.HOP
    F = np.stack([x[i * hs.HOP:i * hs.HOP + hs.NFFT] * hs.WIN for i in range(n)])
    P = np.abs(np.fft.rfft(F, axis=1)) ** 2
    floor = median_filter(P, size=(1, hs.FLOOR_BINS), mode="nearest") / np.log(2)
    snr = P / (floor + 1e-30)
    pk = np.maximum(snr, np.maximum(np.roll(snr, 1, axis=1), np.roll(snr, -1, axis=1)))
    return P, snr, np.clip(pk - 1.0, 0.0, hs.CAP - 1.0)


def harm_score(pk, f0s):
    """pk [조각, bin], f0s [후보] → [조각, 후보] 고조파 1 ~ H 합"""
    S = np.zeros((pk.shape[0], len(f0s)))
    for h in range(1, hs.H + 1):
        f = h * f0s; ok = f <= hs.F_MAX
        k = np.round(f / hs.DF).astype(int)
        S[:, ok] += pk[:, k[ok]]
    return S


def features(x):
    P, snr, pk = frames(x)
    c, k, ok = CAND
    S_all = np.zeros((pk.shape[0], c.size))
    for h in range(hs.H):
        S_all += np.where(ok[h], pk[:, k[h]], 0.0)
    curve = S_all.mean(axis=0); i = int(np.argmax(curve)); S, f0 = float(curve[i]), float(c[i])
    cand_t = f0 * REFINE
    St = harm_score(pk, cand_t); bi = St.argmax(axis=1)
    f0_t, S_t = cand_t[bi], St[np.arange(len(bi)), bi]
    strong = S_t >= 0.5 * S_t.max() if S_t.max() > 0 else np.zeros(len(S_t), bool)
    persist = float(strong.mean())
    glide = float((f0_t[strong].max() - f0_t[strong].min()) / f0) if strong.sum() >= 2 else 0.0
    devs = []
    lP = np.log(P + 1e-30)
    for t in np.flatnonzero(strong):
        ks, fk, w = [], [], []
        for h in range(1, hs.H + 1):
            fc = h * f0_t[t]
            if fc > hs.F_MAX:
                break
            half = int(np.ceil(1 + 0.25 * h)); kc = int(round(fc / hs.DF))
            lo, hi = max(kc - half, 1), min(kc + half, P.shape[1] - 2)
            j = lo + int(np.argmax(P[t, lo:hi + 1]))
            if snr[t, j] < 3.0:
                continue
            a, b, cc = lP[t, j - 1], lP[t, j], lP[t, j + 1]
            den = a - 2 * b + cc
            d = 0.5 * (a - cc) / den if den < 0 else 0.0
            ks.append(h); fk.append((j + d) * hs.DF); w.append(min(snr[t, j], hs.CAP))
        if len(ks) >= 2:
            ks, fk, w = map(np.asarray, (ks, fk, w))
            f0s = np.sum(w * ks * fk) / np.sum(w * ks * ks)
            devs.append(np.sum(w * np.abs(fk - ks * f0s)) / np.sum(w))
    dev = float(np.median(devs)) if devs else float("inf")
    return S, f0, dev, persist, glide
