"""4채널(평면 3 + 평면 밖 1) 방향 추정 — Step8e, D8c-2. MCU 이식 원본 (I3).

평면 3마이크(doa_stream.py)와 같은 흐름에 마이크 하나를 더한다.
  1) 관측 창 x[4, n]을 50% 겹친 Hann 블록으로 나눠 6쌍 교차 스펙트럼 평균
  2) 쌍마다 PHAT 상관 봉우리 = 시간차 τ_ij [샘플] (탐색 폭 = 그 쌍의 길이 ÷ c × fs + 1)
  3) 평면파: (p_j − p_i)·u = −c·τ_ij ÷ fs. 식 6개, 미지수 3개(u_x, u_y, u_z) → 최소제곱
  4) 방위 = atan2(u_y, u_x), 고도각 = atan2(u_z, √(u_x² + u_y²)), norm = |u|
     고도각은 u 성분의 비율이라 지연이 모두 같은 배율로 틀려도(Step7의 약 22%) 바뀌지 않는다.
     norm은 고도각과 상관없이 1 근처여야 한다 (평면 3마이크는 cos(고도각)로 줄었다).
  5) 유효: 봉우리 ≥ min_peak, 최소제곱 잔차(rms) ≤ max_resid 샘플, norm 범위 안

배치(PLACEMENTS)는 평면 3마이크 위치(gcc_phat.mic_positions, MIC1 = 0°)에 네 번째 마이크 좌표를 더한 것.
"""
import os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gcc_phat as g

FS = 12500.0
C = g.SOUND_SPEED
D = g.SPACING
R_TRI = D / np.sqrt(3.0)                                  # 중심에서 평면 마이크까지 [m]

# 네 번째 마이크 좌표 [m] (x = MIC1 방향, z = 위)
PLACEMENTS = {
    "tetra": (0.0, 0.0, D * np.sqrt(2.0 / 3.0)),          # 정사면체: 모든 쌍 70 mm (높이 57.2 mm)
    "c35": (0.0, 0.0, 0.035),
    "c70": (0.0, 0.0, 0.070),
    "c100": (0.0, 0.0, 0.100),
    "m1": (R_TRI, 0.0, 0.070),                            # MIC1 바로 위
}
PAIRS4 = ((0, 1), (0, 2), (1, 2), (0, 3), (1, 3), (2, 3))  # 앞 3쌍은 평면 3마이크와 같은 순서


def positions(place="tetra", spacing=D, cw=False):
    """마이크 4개 좌표 [4, 3]. 평면 3개는 doa_stream과 같은 번호·방향"""
    p2 = g.mic_positions(spacing, cw)
    return np.vstack((np.column_stack((p2, np.zeros(3))), np.asarray(PLACEMENTS[place], float)))


def max_lags(pos, fs=FS):
    """쌍마다 탐색 폭 [샘플] = 쌍 길이 ÷ c × fs + 1"""
    return [float(np.linalg.norm(pos[j] - pos[i]) / C * fs + 1.0) for i, j in PAIRS4]


def cross_spectra(x, block, nfft):
    """x[4, n] → 6쌍 교차 B·conj(A) 평균 + 4채널 자기 |X|² 평균 (doa_stream.cross_spectra의 4채널판)"""
    w = np.hanning(block)
    X = np.array([np.fft.rfft((x[:, s:s + block] - x[:, s:s + block].mean(axis=1, keepdims=True)) * w, nfft, axis=1)
                  for s in range(0, x.shape[1] - block + 1, block // 2)])
    return [(X[:, j] * np.conj(X[:, i])).mean(axis=0) for i, j in PAIRS4] + [(np.abs(X[:, c]) ** 2).mean(axis=0) for c in range(4)]


def solve(tau, pos, fs=FS, pairs=PAIRS4):
    """시간차 [샘플] → (방위 [deg], 고도각 [deg], norm, 잔차 rms [샘플]). 평면 3쌍만 주면 u_z = 0으로 푼다"""
    A = np.array([pos[j] - pos[i] for i, j in pairs])
    b = -C * np.asarray(tau, float) / fs
    if np.allclose(A[:, 2], 0):                            # 평면 배열: z를 풀 수 없다
        u2 = np.linalg.lstsq(A[:, :2], b, rcond=None)[0]; u = np.array([u2[0], u2[1], 0.0])
    else:
        u = np.linalg.lstsq(A, b, rcond=None)[0]
    resid = (A @ u - b) / C * fs
    h = np.hypot(u[0], u[1])
    return (float(np.degrees(np.arctan2(u[1], u[0]))), float(np.degrees(np.arctan2(u[2], h))),
            float(np.linalg.norm(u)), float(np.sqrt(np.mean(resid ** 2))))


def estimate(x, pos, fs=FS, band=(300, 3000), block=512, up=16, eps=0.01, bg=None,
             min_peak=0.15, max_resid=0.3, norm_range=(0.5, 1.3)):
    """관측 창 x[4, n] 하나 → dict(az, el, norm, resid, tau, peak, valid). bg = 같은 형식의 배경 스펙트럼 (교차는 빼고 PHAT)"""
    nfft = 2 * block
    S = cross_spectra(x, block, nfft)
    tau, peak = [], []
    for k, ml in enumerate(max_lags(pos, fs)):
        Rk = S[k] - bg[k] if bg is not None else S[k]
        t, p, _, _, _ = g.phat_peak(Rk, nfft, fs, band, ml, up, eps)
        tau.append(t); peak.append(p)
    az, el, norm, resid = solve(tau, pos, fs)
    valid = min(peak) >= min_peak and resid <= max_resid and norm_range[0] <= norm <= norm_range[1]
    return dict(az=az, el=el, norm=norm, resid=resid, tau=tau, peak=peak, valid=bool(valid))


def run(x, pos, fs=FS, obs=0.5, hop=0.25, **kw):
    """긴 녹음 x[4, N] → 창마다 estimate 결과 목록"""
    n, h = int(obs * fs), int(hop * fs)
    return [estimate(x[:, s:s + n], pos, fs, **kw) for s in range(0, x.shape[1] - n + 1, h)]


def selftest():
    """정답을 아는 평면파 지연으로 solve가 방위·고도각을 되돌리는지"""
    for place in PLACEMENTS:
        pos = positions(place)
        for az, el in ((0, 0), (30, 20), (-120, 45), (150, 75)):
            u = np.array([np.cos(np.radians(el)) * np.cos(np.radians(az)), np.cos(np.radians(el)) * np.sin(np.radians(az)), np.sin(np.radians(el))])
            arr = -(pos @ u) / C * FS
            tau = [arr[j] - arr[i] for i, j in PAIRS4]
            a, e, nrm, r = solve(tau, pos)
            assert abs((a - az + 180) % 360 - 180) < 1e-6 and abs(e - el) < 1e-6 and abs(nrm - 1) < 1e-9 and r < 1e-9, (place, az, el, a, e)
            a2, e2, n2, _ = solve(np.array(tau) * 0.78, pos)            # 같은 배율 오차 → 고도각 그대로
            assert abs(e2 - el) < 1e-6 and abs(n2 - 0.78) < 1e-9
    print("doa4 selftest: OK (배치 5개 × 방향 4개, 배율 0.78에서도 고도각 같음)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    selftest()
