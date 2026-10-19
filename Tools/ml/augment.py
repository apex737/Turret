"""Step8 v1 증강 함수. 학습 fold의 드론 양성에만 쓴다 (시험 fold는 증강하지 않음, Step6).

각 함수가 흉내 내는 차이
  speed     : 로터 회전수·기체 크기 → 고조파 간격과 길이가 함께 바뀜 (리샘플)
  flyby     : 호버 녹음을 직선 통과 비행으로 → 도플러(음높이 하강) + 거리에 따른 크기 변화
  random_eq : 녹음기·마이크·거리의 주파수 응답 차이 → 완만한 기울기 + 봉우리/골 두 개
  mix       : 배경 소음과 SNR을 정해 섞음
"""
from math import gcd
import numpy as np
from scipy.signal import resample_poly

C_SOUND = 343.0


def speed(x, fs, r):
    """재생 속도 r배 (r > 1 = 빨라지고 높아짐). 같은 fs로 다시 읽으면 고조파가 r배."""
    up, down = int(round(1000 / r)), 1000
    g = gcd(up, down)
    return resample_poly(x, up // g, down // g)


def flyby(x, fs, v, d, t_cpa=None):
    """정지 음원 x를 속도 v [m/s]로 최근접 거리 d [m]를 지나가게 한다. 최근접 시각 = t_cpa (기본: 가운데).
    받는 시각 t의 소리 = 음원이 τ(t) = t − r(τ)/c 에 낸 소리 / r(τ).  τ는 고정점 반복으로 푼다."""
    n = len(x)
    t = np.arange(n) / fs
    t_cpa = t[-1] / 2 if t_cpa is None else t_cpa
    tau = t.copy()
    for _ in range(6):
        r = np.hypot(d, v * (tau - t_cpa))
        tau = t - r / C_SOUND
    tau = tau - tau.min()                                # 음원 시간축 안으로
    r = np.hypot(d, v * (tau + (t - tau)[0] - t_cpa))
    y = np.interp(tau * fs, np.arange(n), x, right=0.0)
    m = tau * fs <= n - 1                                # 음원 녹음이 끝난 뒤는 버림
    return (y / r * d)[m], (d / r)[m]                    # 최근접에서 크기 1


def random_eq(x, fs, rng, tilt_db=6.0, peak_db=4.0):
    """zero-phase 주파수 응답: 500 Hz~4 kHz 기울기 ±tilt_db (로그 주파수에 선형) + 300 Hz~4 kHz 봉우리/골 2개 (±peak_db, 1옥타브 폭)"""
    n = len(x)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / fs)
    lf = np.log2(np.maximum(f, 50.0) / 500.0)            # 500 Hz = 0, 4 kHz = 3 옥타브
    g = rng.uniform(-tilt_db, tilt_db) * np.clip(lf, 0, 3) / 3
    for _ in range(2):
        fc = np.log2(rng.uniform(300, 4000) / 500.0)
        g = g + rng.uniform(-peak_db, peak_db) * np.exp(-0.5 * ((lf - fc) / 0.5) ** 2)
    return np.fft.irfft(X * 10 ** (g / 20), n)


def mix(sig, noise, snr_db, ref=None):
    """sig에 noise를 SNR snr_db로 섞는다. ref = SNR 기준이 되는 sig의 샘플 마스크 (예: 확실한 양성 구간). noise는 반복·자름."""
    if len(noise) < len(sig):
        noise = np.tile(noise, int(np.ceil(len(sig) / len(noise))))
    noise = noise[:len(sig)]
    ps = np.mean(sig[ref] ** 2) if ref is not None and ref.any() else np.mean(sig ** 2)
    pn = np.mean(noise ** 2) + 1e-30
    return sig + noise * np.sqrt(ps / pn / 10 ** (snr_db / 10))


if __name__ == "__main__":                               # 자가 시험: 도플러 비율과 크기 포락선
    fs = 16000
    x = np.sin(2 * np.pi * 500 * np.arange(10 * fs) / fs)
    y, env = flyby(x, fs, v=20.0, d=10.0)
    def f0(seg):
        S = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 16)); return np.argmax(S) * fs / (1 << 16)
    a, b = f0(y[fs:2 * fs]), f0(y[-2 * fs:-fs])
    exp_a, exp_b = 500 / (1 - 20 / C_SOUND * 0.97), 500 / (1 + 20 / C_SOUND * 0.97)
    print(f"다가올 때 {a:.1f} Hz (약 {exp_a:.0f}), 멀어질 때 {b:.1f} Hz (약 {exp_b:.0f}), 크기 최대 {env.max():.2f} 최소 {env.min():.2f}")
    z = speed(x, fs, 1.2); print(f"speed 1.2: 길이 {len(z) / len(x):.3f}배, f0 {f0(z[:fs]) * 1.0:.1f} Hz (같은 fs로 읽음 → 600 기대)")
