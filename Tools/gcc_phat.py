"""
GCC-PHAT 프로토타입: 덤프(npz)에서 마이크 쌍별 도달 시간차(TDOA)와 음원 방향을 구한다.

사용법
  python gcc_phat.py --selftest                 # 지연/각도를 아는 합성 신호로 구현 검증
  python gcc_phat.py dumps/99.npz               # 파일 1개: 결과 출력 + 그래프
  python gcc_phat.py dumps                      # 폴더 전체: 표 + 요약
  python gcc_phat.py dumps --sweep              # BPF 대역 x 분석 구간 길이 비교

부호 규칙
  tau_ij = (j 도달 시각) - (i 도달 시각) [샘플].  양수 = MIC j가 MIC i보다 늦게 들음.
  세 쌍은 tau12 + tau23 = tau13 을 만족해야 한다 (closure = tau12 + tau23 - tau13 ≈ 0).

마이크 배치와 각도 규칙 (가정: 한 변 --spacing 인 정삼각형, 위에서 내려다본 그림)
  중심에서 MIC1 방향이 0°. 반시계 방향이 +.  MIC2 = +120°, MIC3 = -120°.
  번호가 시계 방향으로 붙어 있으면 --cw.
  norm = 추정된 방향 벡터의 길이. 음원이 멀고 마이크와 같은 평면에 있으면 1.
         1보다 많이 작으면 음원이 위/아래에 있거나 가까운 것, 1보다 크면 배치 가정이 틀린 것.

처리 순서 (MCU 이식 대상)
  onset 탐색 → 공통 구간 자르기 → 평균 제거 + 창 → FFT → X_j·conj(X_i)
  → 대역 제한 + PHAT(크기 정규화) → IFFT → 최대 지연 범위 안에서 피크 → 2차 보간
  → 세 지연으로 방향 벡터 최소제곱 → 각도
"""
import argparse
import glob
import os

import numpy as np

FS = 50_000.0
SOUND_SPEED = 343.0                 # m/s (20°C)
SPACING = 0.07                      # 마이크 간격 [m]
PAIRS = ((0, 1), (0, 2), (1, 2))    # (i, j) → tau_ij
FLAG_CLIP = 0x01
FLAG_MANUAL = 0x02
FLAG_VALID = 0x08                   # (결과 패킷) MCU가 신뢰 가능으로 판정


def mic_positions(spacing=SPACING, cw=False):
    """정삼각형 꼭짓점 좌표 [m]. 중심이 원점, MIC1이 0° 방향."""
    ang = np.deg2rad([0.0, 120.0, -120.0])
    if cw:
        ang = -ang
    r = spacing / np.sqrt(3.0)
    return r * np.column_stack((np.cos(ang), np.sin(ang)))


def default_max_lag(spacing=SPACING, fs=FS):
    """물리적으로 가능한 최대 지연(간격 / 음속) + 여유 2샘플."""
    return float(np.ceil(spacing / SOUND_SPEED * fs) + 2)


def tdoa_to_angle(tau, fs, pos):
    """세 쌍의 지연 [샘플] → (각도 [deg], norm).

    평면파 가정: 음원 쪽 단위 벡터 u에 대해 (p_j - p_i)·u = -c·tau_ij.
    식 3개, 미지수 2개(u_x, u_y)이므로 최소제곱으로 푼다.
    """
    A = np.array([pos[j] - pos[i] for i, j in PAIRS])
    b = -SOUND_SPEED * np.asarray(tau, dtype=float) / fs
    u = np.linalg.lstsq(A, b, rcond=None)[0]
    return float(np.degrees(np.arctan2(u[1], u[0]))), float(np.hypot(u[0], u[1]))


def angle_to_tdoa(angle_deg, fs, pos):
    """각도 → 평면파일 때의 세 쌍 지연 [샘플] (tdoa_to_angle의 역)."""
    u = np.array([np.cos(np.deg2rad(angle_deg)), np.sin(np.deg2rad(angle_deg))])
    return [float(-(pos[j] - pos[i]) @ u / SOUND_SPEED * fs) for i, j in PAIRS]


def find_onset(x, k=8, frac_div=20):
    """3채널 중 가장 먼저 잡음을 크게 넘는 샘플 위치.

    잡음 크기는 앞쪽 1/4 구간(트리거 직전 프레임의 앞부분)의 평균 편차로 추정한다.
    문턱 = max(k x 잡음, 최대 편차 / frac_div).
    정수 연산만 쓰므로 MCU(tdoa.c의 find_onset)와 결과가 정확히 같다.
    """
    xi = np.rint(x).astype(np.int64)
    n = xi.shape[1]
    ac = np.abs(n * xi - xi.sum(axis=1, keepdims=True)).max(axis=0)      # |x - 평균| x n
    q = max(n // 4, 16)
    thr = max(frac_div * k * int(ac[:q].sum()), int(ac.max()) * q)
    idx = np.flatnonzero(ac * (frac_div * q) > thr)
    return int(idx[0]) if idx.size else int(np.argmax(ac))


def taper(n, frac=0.2):
    """양 끝 frac 비율만 코사인으로 줄이는 창 (Tukey). 가운데는 1."""
    w = np.ones(n)
    m = int(n * frac)
    if m > 0:
        ramp = 0.5 - 0.5 * np.cos(np.pi * (np.arange(m) + 0.5) / m)
        w[:m], w[-m:] = ramp, ramp[::-1]
    return w


def cut_window(x, onset, fs, win_ms, pre_ms):
    """onset보다 pre_ms 앞에서 시작하는 win_ms 길이 구간. 3채널에 같은 구간을 쓴다."""
    n = int(round(win_ms * 1e-3 * fs))
    lo = onset - int(round(pre_ms * 1e-3 * fs))
    lo = max(0, min(lo, x.shape[1] - n))
    seg = x[:, lo:lo + n]
    seg = seg - seg.mean(axis=1, keepdims=True)
    return seg * taper(n), lo


def gcc_phat(a, b, fs, band, max_lag, up=16, eps=0.01):
    """b가 a보다 몇 샘플 늦는지 추정한다 (양수 = b가 늦음).

    up  : IFFT를 up배 촘촘하게 계산 (주파수 영역 제로패딩). 1이면 원래 샘플 간격.
    eps : PHAT 정규화의 바닥값 (대역 내 최대 크기 대비). 신호가 거의 없는 빈의 잡음 증폭을 막는다.
    반환: (tau, peak, second, lags, cc)
      peak   : 상관 피크 높이 (0~1, 1 = 대역 전체가 같은 지연으로 정렬)
      second : 두 번째로 높은 봉우리 / peak (작을수록 피크가 뚜렷함)
    """
    n = len(a)
    nfft = 1 << int(np.ceil(np.log2(2 * n)))
    A, B = np.fft.rfft(a, nfft), np.fft.rfft(b, nfft)
    R = B * np.conj(A)
    f = np.fft.rfftfreq(nfft, 1.0 / fs)
    in_band = (f >= band[0]) & (f <= band[1])
    mag = np.abs(R)
    R = np.where(in_band, R / (mag + eps * mag[in_band].max() + 1e-30), 0.0)

    big = nfft * up
    cc = np.fft.irfft(R, big) * big / (2.0 * in_band.sum())
    m = int(round(max_lag * up))
    cc = np.concatenate((cc[-m:], cc[:m + 1]))          # 지연 -max_lag ~ +max_lag
    lags = np.arange(-m, m + 1) / up

    k = int(np.argmax(cc))
    tau, peak = lags[k], cc[k]
    if 0 < k < len(cc) - 1:                              # 2차(포물선) 보간
        y0, y1, y2 = cc[k - 1], cc[k], cc[k + 1]
        d = y0 - 2 * y1 + y2
        if d < 0:
            p = 0.5 * (y0 - y2) / d
            tau, peak = lags[k] + p / up, y1 - 0.25 * (y0 - y2) * p

    is_max = (cc[1:-1] > cc[:-2]) & (cc[1:-1] >= cc[2:])
    others = [cc[i + 1] for i in np.flatnonzero(is_max) if abs(i + 1 - k) > up]
    second = max(max(others) / peak, 0.0) if others and peak > 0 else 0.0
    return tau, peak, second, lags, cc


def analyze(x, fs=FS, band=(500, 3000), win_ms=5.0, pre_ms=1.0, max_lag=None, up=16, eps=0.01, pos=None):
    """한 캡처(ch x n)에서 세 쌍의 지연과 방향을 구한다."""
    pos = mic_positions() if pos is None else pos
    max_lag = default_max_lag(fs=fs) if max_lag is None else max_lag
    onset = find_onset(x)
    seg, lo = cut_window(x.astype(np.float64), onset, fs, win_ms, pre_ms)
    res = dict(onset=onset, lo=lo, seg=seg, tau=[], peak=[], second=[], cc=[])
    for i, j in PAIRS:
        tau, peak, second, lags, cc = gcc_phat(seg[i], seg[j], fs, band, max_lag, up, eps)
        res["tau"].append(tau)
        res["peak"].append(peak)
        res["second"].append(second)
        res["cc"].append(cc)
    res["lags"] = lags
    res["closure"] = res["tau"][0] + res["tau"][2] - res["tau"][1]
    res["angle"], res["norm"] = tdoa_to_angle(res["tau"], fs, pos)
    return res


def is_reliable(r, args):
    """신뢰 판정. MCU(tdoa.c)의 valid 와 같은 규칙: 세 쌍의 peak가 모두 기준 이상이고 norm이 범위 안."""
    return bool(min(r["peak"]) >= args.min_peak and args.min_norm <= r["norm"] <= args.max_norm)


def load(path):
    z = np.load(path)
    return z["data"], float(z["fs"]) if "fs" in z else FS, int(z["flags"]), int(z["seq"])


def list_files(path):
    if os.path.isfile(path):
        return [path]
    files = glob.glob(os.path.join(path, "*.npz"))
    return sorted(files, key=lambda p: (len(os.path.basename(p)), os.path.basename(p)))


def add_analysis_args(ap):
    """분석 파라미터 옵션 (doa_live.py와 공유)."""
    ap.add_argument("--band", type=float, nargs=2, default=(500, 3000), help="사용할 주파수 대역 [Hz]")
    ap.add_argument("--win", type=float, default=5.0, help="분석 구간 길이 [ms]")
    ap.add_argument("--pre", type=float, default=1.0, help="onset보다 앞에서 시작하는 시간 [ms]")
    ap.add_argument("--spacing", type=float, default=SPACING, help="마이크 간격 [m] (정삼각형 한 변)")
    ap.add_argument("--cw", action="store_true", help="마이크 번호가 시계 방향으로 붙어 있을 때")
    ap.add_argument("--max-lag", type=float, help="탐색할 최대 지연 [샘플] (기본: 간격에서 계산 + 2)")
    ap.add_argument("--up", type=int, default=16, help="상관 곡선 업샘플 배수")
    ap.add_argument("--eps", type=float, default=0.01, help="PHAT 정규화 바닥값")
    ap.add_argument("--min-peak", type=float, default=0.5, help="이 값보다 peak가 낮은 캡처는 신뢰 낮음으로 표시")
    ap.add_argument("--min-norm", type=float, default=0.3, help="norm이 이보다 작으면 신뢰 낮음 (음원이 거의 위/아래)")
    ap.add_argument("--max-norm", type=float, default=1.2, help="norm이 이보다 크면 신뢰 낮음 (물리적으로 불가능)")


def kwargs_from(args):
    max_lag = default_max_lag(args.spacing) if args.max_lag is None else args.max_lag
    return dict(band=tuple(args.band), win_ms=args.win, pre_ms=args.pre, max_lag=max_lag,
                up=args.up, eps=args.eps, pos=mic_positions(args.spacing, args.cw))


# ---------------------------------------------------------------- 실행 모드


def run_file(args):
    x, fs, flags, seq = load(args.path)
    r = analyze(x, fs, **kwargs_from(args))
    print(f"{os.path.basename(args.path)}  seq {seq}  flags 0x{flags:02x}  "
          f"onset {r['onset']} (구간 시작 {r['lo']})  band {args.band[0]:.0f}-{args.band[1]:.0f} Hz  win {args.win} ms")
    for (i, j), tau, peak, second in zip(PAIRS, r["tau"], r["peak"], r["second"]):
        print(f"  tau{i + 1}{j + 1} = {tau:+7.2f} 샘플  {tau / fs * 1e6:+8.1f} us  "
              f"{tau / fs * SOUND_SPEED * 1e3:+7.1f} mm   peak {peak:.2f}  second {second:.2f}")
    print(f"  closure (tau12 + tau23 - tau13) = {r['closure']:+.2f} 샘플")
    print(f"  방향 = {r['angle']:+.1f}°   norm {r['norm']:.2f}")
    ok = is_reliable(r, args)
    print(f"  판정: {'신뢰 가능' if ok else '신뢰 낮음'} (세 쌍 중 최소 peak {min(r['peak']):.2f}, 기준 {args.min_peak} 이상 / "
          f"norm {r['norm']:.2f}, 기준 {args.min_norm} ~ {args.max_norm})")
    if not args.no_plot:
        plot(x, fs, r, args, os.path.basename(args.path))


def run_batch(args):
    files = list_files(args.path)
    kw = kwargs_from(args)
    print(f"{len(files)} files  band {args.band[0]:.0f}-{args.band[1]:.0f} Hz  win {args.win} ms  max_lag ±{kw['max_lag']:g}")
    print(f"{'file':14} {'flags':5} {'tau12':>7} {'tau13':>7} {'tau23':>7} {'closure':>8} {'peak':>5} {'angle':>7} {'norm':>5}  ok")
    rows = []
    for p in files:
        x, fs, flags, _ = load(p)
        r = analyze(x, fs, **kw)
        rows.append((flags, r))
        mark = ("C" if flags & FLAG_CLIP else "-") + ("M" if flags & FLAG_MANUAL else "-")
        print(f"{os.path.basename(p):14} {mark:5} {r['tau'][0]:+7.2f} {r['tau'][1]:+7.2f} {r['tau'][2]:+7.2f} "
              f"{r['closure']:+8.2f} {min(r['peak']):5.2f} {r['angle']:+7.1f} {r['norm']:5.2f}  "
              f"{'ok' if is_reliable(r, args) else '.'}")
    rows = [r for flags, r in rows if not flags & (FLAG_CLIP | FLAG_MANUAL)]
    print(summary_line(rows, "clip/manual 제외"))
    print(summary_line([r for r in rows if is_reliable(r, args)], "그중 신뢰 가능"))


def summary_line(rows, name):
    if not rows:
        return f"[{name}] 0 files"
    c = np.abs([r["closure"] for r in rows])
    norm = [r["norm"] for r in rows]
    return (f"[{name}] n={len(rows)}  |closure| 중앙값 {np.median(c):.2f}  "
            f"<0.5샘플 {100 * np.mean(c < 0.5):.0f}%  <1.0샘플 {100 * np.mean(c < 1.0):.0f}%  "
            f"norm 중앙값 {np.median(norm):.2f}")


def run_sweep(args):
    """대역 x 구간 길이 조합별 비교. 정답 없이 볼 수 있는 지표(수율, 세 쌍의 일관성)만 사용한다.

    kept : 신뢰 가능으로 판정된 캡처 수 (수율)
    <0.5 / <1.0 : kept 중 |closure|가 그 값보다 작은 비율
    """
    bands = ((150, 2000), (500, 3000), (1000, 4000), (2000, 5000), (1000, 8000))
    wins = (2.0, 3.0, 5.0, 10.0)
    data = [load(p) for p in list_files(args.path)]
    data = [(x, fs) for x, fs, flags, _ in data if not flags & (FLAG_CLIP | FLAG_MANUAL)]
    kw = kwargs_from(args)
    print(f"{len(data)} files (clip/manual 제외)  max_lag ±{kw['max_lag']:g}  min_peak {args.min_peak}")
    print(f"{'band [Hz]':>12} {'win':>5} {'kept':>5} {'|clo| med':>9} {'<0.5':>5} {'<1.0':>5}")
    for band in bands:
        for win in wins:
            kw.update(band=band, win_ms=win)
            rs = [analyze(x, fs, **kw) for x, fs in data]
            c = np.abs([r["closure"] for r in rs if is_reliable(r, args)])
            if c.size == 0:
                print(f"{band[0]:>5}-{band[1]:<6} {win:5.0f} {0:5d}")
                continue
            print(f"{band[0]:>5}-{band[1]:<6} {win:5.0f} {c.size:5d} {np.median(c):9.2f} "
                  f"{100 * np.mean(c < 0.5):4.0f}% {100 * np.mean(c < 1.0):4.0f}%")


def synth_capture(rng, delays, fs=FS, n=2048, onset=1100):
    """채널별 지연 [샘플]을 아는 스냅 모양 합성 캡처 (ADC 눈금, 잡음 3 LSB)."""
    m = 4096
    f = np.fft.rfftfreq(m, 1.0 / fs)
    S = np.fft.rfft(rng.standard_normal(m)) * ((f > 200) & (f < 8000))
    t = np.arange(m)
    env = np.where(t >= 1500, np.exp(-(t - 1500) / 150.0), 0.0)         # 갑자기 시작해 감쇠
    base = np.fft.rfft(np.fft.irfft(S, m) * env)
    x = np.empty((len(delays), n))
    for ch, d in enumerate(delays):
        delayed = np.fft.irfft(base * np.exp(-2j * np.pi * f * d / fs), m)
        x[ch] = delayed[1500 - onset:1500 - onset + n]
    x = 300.0 * x / np.abs(x).max() + 2048.0 + 3.0 * rng.standard_normal(x.shape)
    return np.clip(np.round(x), 0, 4095)


def run_selftest(args):
    """지연과 각도를 아는 합성 신호로 부호·크기·보간·각도 변환을 검증한다."""
    rng = np.random.default_rng(0)
    kw = kwargs_from(args)
    worst_tau = worst_ang = 0.0

    print("[지연] true (tau12, tau13)   est (tau12, tau13, tau23)   closure   max err")
    for true12, true13 in ((1.0, 3.0), (-4.3, 2.6), (7.75, -2.2), (0.0, 0.0), (9.4, 6.1)):
        r = analyze(synth_capture(rng, (0.0, true12, true13)), FS, **kw)
        true = (true12, true13, true13 - true12)
        err = max(abs(e - t_) for e, t_ in zip(r["tau"], true))
        worst_tau = max(worst_tau, err)
        print(f"       ({true12:+6.2f}, {true13:+6.2f})    ({r['tau'][0]:+6.2f}, {r['tau'][1]:+6.2f}, {r['tau'][2]:+6.2f})"
              f"   {r['closure']:+6.2f}   {err:6.3f}")

    print("[각도] true     est     norm    err")
    for true in (0.0, 45.0, 100.0, 120.0, -120.0, -150.0, 180.0):
        t12, t13, _ = angle_to_tdoa(true, FS, kw["pos"])
        r = analyze(synth_capture(rng, (0.0, t12, t13)), FS, **kw)
        err = abs((r["angle"] - true + 180.0) % 360.0 - 180.0)
        worst_ang = max(worst_ang, err)
        print(f"       {true:+6.1f}  {r['angle']:+6.1f}   {r['norm']:.2f}   {err:5.2f}")

    ok = worst_tau < 0.1 and worst_ang < 1.0
    print(f"최대 오차: 지연 {worst_tau:.3f} 샘플 (기준 0.1), 각도 {worst_ang:.2f}° (기준 1.0) → {'PASS' if ok else 'FAIL'}")
    return ok


def plot(x, fs, r, args, title):
    import matplotlib.pyplot as plt

    mic_colors = ("#2a78d6", "#eb6834", "#1baf7a")
    ink, muted = "#0b0b0b", "#52514e"
    fig = plt.figure(figsize=(11, 7))
    gs = fig.add_gridspec(2, 3, height_ratios=(1.1, 1.0))

    ax = fig.add_subplot(gs[0, :])
    n = r["seg"].shape[1]
    t_ms = (r["lo"] + np.arange(n) - r["onset"]) / fs * 1e3
    for ch in range(3):
        ax.plot(t_ms, r["seg"][ch], color=mic_colors[ch], lw=1.2, label=f"MIC{ch + 1}")
    ax.axvline(0, color=muted, lw=0.8, ls="--")
    ax.set_title(f"{title}   direction {r['angle']:+.1f}°  (norm {r['norm']:.2f})   "
                 f"window {args.win:g} ms, mean removed, tapered", color=ink)
    ax.set_xlabel("time from onset [ms]")
    ax.set_ylabel("AC [LSB]")
    ax.grid(alpha=0.25)
    ax.legend(loc="upper right", fontsize=8)

    first = None
    for col, ((i, j), tau, peak, cc) in enumerate(zip(PAIRS, r["tau"], r["peak"], r["cc"])):
        ax = fig.add_subplot(gs[1, col], sharey=first)
        first = first or ax
        ax.plot(r["lags"], cc, color=ink, lw=1.2)
        ax.axvline(tau, color=muted, lw=0.8, ls="--")
        ax.plot([tau], [peak], "o", color=ink, ms=6)
        ax.set_title(f"MIC{i + 1} → MIC{j + 1}:  {tau:+.2f} samples  ({tau / fs * 1e6:+.0f} µs)", fontsize=10, color=ink)
        ax.set_xlabel("lag [samples]")
        ax.grid(alpha=0.25)
        if col == 0:
            ax.set_ylabel(f"GCC-PHAT  ({args.band[0]:.0f}-{args.band[1]:.0f} Hz)")
        else:
            ax.tick_params(labelleft=False)
    fig.tight_layout()
    if args.save:
        fig.savefig(args.save, dpi=130)
        print(f"saved {args.save}")
    else:
        plt.show()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", help="npz 파일 또는 폴더")
    add_analysis_args(ap)
    ap.add_argument("--sweep", action="store_true", help="대역 x 구간 길이 비교")
    ap.add_argument("--selftest", action="store_true", help="합성 신호로 구현 검증")
    ap.add_argument("--no-plot", action="store_true")
    ap.add_argument("--save", help="그래프를 창에 띄우지 않고 이 파일로 저장")
    args = ap.parse_args()

    if args.selftest:
        raise SystemExit(0 if run_selftest(args) else 1)
    if not args.path:
        ap.error("npz 파일이나 폴더가 필요합니다 (또는 --selftest)")
    if args.sweep:
        run_sweep(args)
    elif os.path.isdir(args.path):
        run_batch(args)
    else:
        run_file(args)


if __name__ == "__main__":
    main()
