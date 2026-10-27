"""DOA 합성 실험: 대역 상한(3000 vs 2400)과 PHAT에 쓰는 칸(전체 / 선 마스크 / 정답 f0)이 유효율·오차에 주는 영향.
흐름과 그림은 Tools/notebooks/doa_mask_phat.ipynb. 이 파일은 계산만 한다.

    python doa/mask_phat.py                 # 전체 표 (12방향 × 8 s, 몇 분)
    python doa/mask_phat.py --quick         # 4방향 × 4 s

조건 (2026-10-27)
  배열     config/geometry.json (70 mm 정삼각형) · 12.5 kHz · 관측 0.5 s / 이동 0.25 s · 블록 512, NFFT 1024 (doa.h와 같음)
  유효     doa_stream.is_valid: 세 쌍 최소 피크 ≥ 0.15, |닫힘| ≤ 0.3샘플, 0.5 ≤ norm ≤ 1.3
  잡음     채널마다 독립 백색 잡음. SNR = 300 ~ 3000 Hz 대역 전력비
  음원     고조파 선(기본음 ±1% 천천히 흔들림) 또는 300 ~ 3000 Hz 넓은 대역 잡음. 반사 없음, 고도 0°
  칸 고르기
    full    대역 안 칸 전부 (지금 doa.c 방식)
    line    세 채널 자기 스펙트럼 평균이 대역 중앙값보다 10 dB 이상 큰 칸. 4칸 미만이면 full
    oracle  정답 f0의 k배 ±2칸 (고조파 센서가 f0를 정확히 줄 때의 상한)
"""
import argparse
import os
import sys
import types

import numpy as np
from scipy.signal import butter, sosfilt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import doa_stream as ds   # noqa: E402
import gcc_phat as g      # noqa: E402

ds.DELAY_US = np.zeros(3)                  # 합성 신호에는 채널 고유 지연이 없다
FS = ds.FS_NOM                             # 12,500 Hz
BLOCK, NFFT, UP, EPS = 512, 1024, 16, 0.01
POS, D = ds.positions()                    # 마이크 좌표 [m], 간격 [m]
C = g.SOUND_SPEED
F_ALIAS = C / (2 * D)                      # 공간 앨리어싱 한계 c/(2d) ≈ 2450 Hz
FREQ = np.fft.rfftfreq(NFFT, 1 / FS)       # 칸 k의 주파수 = k × 12.2 Hz
MAX_LAG = D / C * FS + 1.0                 # 지연 탐색 범위 ± [샘플]
SOS_BB = butter(6, [300, 3000], "bandpass", fs=FS, output="sos")


def args(band=(300, 3000)):
    """doa_stream의 판정 문턱 (doa.h DOA_MIN_PEAK 등과 같음)"""
    return types.SimpleNamespace(obs=0.5, hop=0.25, block=BLOCK, band=band, min_snr=6.0,
                                 min_peak=0.15, max_closure=0.3, min_norm=0.5, max_norm=1.3)


# ---------- 음원 ----------
def harmonic(rng, n, f0, amps):
    """기본음 f0의 고조파 선. amps[k-1] = k번째 선의 진폭"""
    t = np.arange(n) / FS
    ph = 2 * np.pi * np.cumsum(f0 * (1 + 0.01 * np.sin(2 * np.pi * 0.3 * t + rng.uniform(0, 6.28)))) / FS
    return sum(a * np.sin(k * ph + rng.uniform(0, 6.28)) for k, a in enumerate(amps, 1))


def broadband(rng, n):
    return sosfilt(SOS_BB, rng.standard_normal(n))


SOURCES = {                                # 이름: (만드는 함수, 정답 f0 또는 None)
    "고조파 400×7": (lambda r, n: harmonic(r, n, 400, [1] * 7), 400),
    "고조파 700×4": (lambda r, n: harmonic(r, n, 700, [1] * 4), 700),
    "700×4, 2800에 몰림": (lambda r, n: harmonic(r, n, 700, [.1, .1, .3, 1]), 700),
    "넓은 대역": (broadband, None),
}


# ---------- 배열에 도착 ----------
def true_tau(az):
    """방위 az [deg]에서 세 쌍 (1,2) (1,3) (2,3)의 정답 지연 [샘플]"""
    u = np.array([np.cos(np.radians(az)), np.sin(np.radians(az))])
    arrive = -(POS @ u) / C * FS
    return np.array([arrive[j] - arrive[i] for i, j in g.PAIRS])


def delayed(src, az):
    """평면파: 마이크마다 도착 시각만큼 늦춘 3채널 [3, n] (주파수 영역 위상 회전 → 분수 지연)"""
    u = np.array([np.cos(np.radians(az)), np.sin(np.radians(az))])
    n = len(src); nfft = 1 << int(np.ceil(np.log2(n + 64)))
    S = np.fft.rfft(src, nfft); f = np.fft.rfftfreq(nfft, 1 / FS)
    return np.array([np.fft.irfft(S * np.exp(-2j * np.pi * f * (-(p @ u) / C)), nfft)[:n] for p in POS])


def band_power(x):
    return np.mean(sosfilt(SOS_BB, x, axis=-1) ** 2)


def add_noise(rng, x, snr_db):
    nz = rng.standard_normal(x.shape)
    return x + nz * np.sqrt(band_power(x) / band_power(nz) / 10 ** (snr_db / 10))


def make_scene(name, az, snr_db, seconds=8.0, seed=7):
    """음원 하나 → 방위 az, SNR snr_db의 3채널 녹음. 같은 seed면 같은 신호·잡음"""
    rng = np.random.default_rng(seed)
    mk, _ = SOURCES[name]
    return add_noise(rng, delayed(mk(rng, int(seconds * FS)), az), snr_db)


# ---------- 칸 고르기와 PHAT ----------
def make_mask(S, method, f0=None, band=(300, 3000)):
    """PHAT에 쓸 칸 (True = 투표함). S = doa_stream.cross_spectra 결과 (교차 3 + 자기 3)"""
    inb = (FREQ >= band[0]) & (FREQ <= band[1])
    if method == "full":
        return inb
    if method == "oracle":
        m = np.zeros_like(inb)
        for k in range(1, 40):
            c = int(round(k * f0 * NFFT / FS))
            m[max(c - 2, 0):c + 3] = True
        return m & inb
    P = sum(S[3 + c] for c in range(3)).real
    m = inb & (P > np.median(P[inb]) * 10)                 # 대역 중앙값보다 10 dB 위
    return m if m.sum() >= 4 else inb


def phat_curve(R, mask):
    """교차 스펙트럼 R → 고른 칸만 크기 1로 맞춘 상관 곡선. 반환 (lags [샘플], cc, tau, peak)
    peak 1 = 고른 칸이 모두 같은 지연을 가리킴. 정규화가 '고른 칸 수'라서 칸을 줄이면 peak의 뜻이 바뀐다"""
    mag = np.abs(R)
    Rw = np.where(mask, R / (mag + EPS * mag[mask].max() + 1e-30), 0.0)
    big = NFFT * UP
    cc = np.fft.irfft(Rw, big) * big / (2.0 * mask.sum())
    m = int(round(MAX_LAG * UP))
    cc = np.concatenate((cc[-m:], cc[:m + 1])); lags = np.arange(-m, m + 1) / UP
    k = int(np.argmax(cc)); tau, pk = lags[k], cc[k]
    if 0 < k < len(cc) - 1:                                 # 포물선 보간 (gcc_phat.phat_peak와 같음)
        y0, y1, y2 = cc[k - 1], cc[k], cc[k + 1]; dd = y0 - 2 * y1 + y2
        if dd < 0:
            p = 0.5 * (y0 - y2) / dd; tau, pk = lags[k] + p / UP, y1 - 0.25 * (y0 - y2) * p
    return lags, cc, tau, pk


def estimate(x, method="full", f0=None, band=(300, 3000), keep=False):
    """관측 창 x[3, 6250] 하나 → 방위와 판정 값. keep=True면 그림용 중간 결과(S, mask, 곡선)도 담는다"""
    S = ds.cross_spectra(x, BLOCK, NFFT)
    mask = make_mask(S, method, f0, band)
    curves = [phat_curve(R, mask) for R in S[:3]]
    tau = [c[2] for c in curves]; peak = [c[3] for c in curves]
    ang, norm = g.tdoa_to_angle(tau, FS, POS)
    r = dict(tau=tau, peak=peak, angle=ang, norm=norm, closure=tau[0] + tau[2] - tau[1], nbins=int(mask.sum()))
    r["valid"] = ds.is_valid(r, args(band))
    if keep:
        r.update(S=S, mask=mask, curves=curves)
    return r


def windows(x, method="full", f0=None, band=(300, 3000)):
    """연속 3채널 → 0.25 s마다 0.5 s 창의 결과 목록"""
    n_obs, n_hop = int(0.5 * FS), int(0.25 * FS)
    return [estimate(x[:, s:s + n_obs], method, f0, band) for s in range(0, x.shape[1] - n_obs + 1, n_hop)]


# ---------- 지표 ----------
def why_invalid(r, a=None):
    """무효 사유 목록 (여러 개 동시 가능)"""
    a = a or args()
    out = []
    if min(r["peak"]) < a.min_peak: out.append("피크")
    if abs(r["closure"]) > a.max_closure: out.append("닫힘")
    if not (a.min_norm <= r["norm"] <= a.max_norm): out.append("norm")
    return out


def trial(name, method, snr_db, band=(300, 3000), angles=range(0, 360, 30), seconds=8.0, seed=7):
    """방향 여러 개 → 지표
    유효율       = 유효 창 ÷ 전체 창 (합성은 음원이 늘 있으므로 모든 창이 평가 대상)
    오차         = 유효 창의 |추정 − 정답| 방위
    유효 중 오답 = 유효 창 중 오차 > 10° 비율 (Step7 p95 기준 10°)"""
    _, f0 = SOURCES[name]
    tot = val = wrong = 0; errs = []; why = {"피크": 0, "닫힘": 0, "norm": 0}; nb = []; pk = []
    for i, az in enumerate(angles):
        x = make_scene(name, az, snr_db, seconds, seed + i)
        for r in windows(x, method, f0, band):
            tot += 1; nb.append(r["nbins"]); pk.append(min(r["peak"]))
            if r["valid"]:
                val += 1; e = float(ds.ang_err(r["angle"], az)); errs.append(e); wrong += e > 10
            else:
                for w in why_invalid(r): why[w] += 1
    e = np.array(errs)
    return dict(source=name, method=method, snr=snr_db, band=f"{band[0]} ~ {band[1]}", windows=tot,
                bins=float(np.median(nb)), min_peak=float(np.median(pk)), valid=val / tot * 100,
                err_med=float(np.median(e)) if len(e) else np.nan, err_p95=float(np.percentile(e, 95)) if len(e) else np.nan,
                wrong=wrong / val * 100 if val else np.nan, **{f"무효_{k}": v for k, v in why.items()})


def sweep(sources=None, methods=("full", "line", "oracle"), snrs=(12, 6, 0), bands=((300, 3000),), **kw):
    rows = []
    for name in sources or SOURCES:
        for snr in snrs:
            for band in bands:
                for m in methods:
                    if m == "oracle" and SOURCES[name][1] is None:
                        continue
                    rows.append(trial(name, m, snr, band, **kw))
    return rows


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="4방향 × 4 s")
    ap.add_argument("--bands", action="store_true", help="칸 고르기 대신 대역 상한 3000 vs 2400 비교 (full만)")
    a = ap.parse_args()
    kw = dict(angles=range(0, 360, 90), seconds=4.0) if a.quick else {}
    rows = (sweep(methods=("full",), bands=((300, 3000), (300, 2400)), **kw) if a.bands else sweep(**kw))
    print(f"간격 {D * 1000:.1f} mm → c/(2d) = {F_ALIAS:.0f} Hz")
    print("음원 | SNR | 대역 | 방법 | 쓴 칸 | 최소 피크 | 유효율 | 오차 중앙 / p95 | 유효 중 오답 | 무효 피크/닫힘/norm")
    for r in rows:
        print(f"{r['source']:16s} {r['snr']:3d} dB | {r['band']} | {r['method']:6s} | {r['bins']:4.0f} | {r['min_peak']:.2f} | "
              f"{r['valid']:5.1f}% | {r['err_med']:6.2f}° / {r['err_p95']:6.2f}° | {r['wrong']:5.1f}% | "
              f"{r['무효_피크']}/{r['무효_닫힘']}/{r['무효_norm']}")


if __name__ == "__main__":
    main()
