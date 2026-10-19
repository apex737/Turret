"""Step7 지속음 방향 추정 PC 기준 구현 (D0: 고정 대역 GCC-PHAT + LSE). STREAM 녹음(12.5 kHz 3ch)을 입력으로 쓴다.

    python doa/doa_stream.py dumps/stream/speaker_10min                   # 시간별 방위 + 요약
    python doa/doa_stream.py dumps/stream/doa_az* --bg dumps/stream/doa_bg   # 폴더 이름의 az###가 정답 방위
    python doa/doa_stream.py dumps/stream/doa_az045 --obs 1.0 --band 300 2500

스냅(gcc_phat.analyze)과 다른 점
  - onset을 찾지 않는다. 소리가 계속 나므로 고정 길이 관측 창(--obs)을 --hop마다 민다.
  - 관측 창 안을 짧은 블록(--block)으로 나눠 교차 스펙트럼을 평균한 뒤 PHAT. 블록 하나보다 잡음에 강하다.
  - 결과마다 관측 구간의 샘플 번호(STREAM 시간축)와 유효성을 붙인다 (Step9A 결합용).

배경 빼기 (--bg, D1): 드론이 없을 때의 교차 스펙트럼을 평균해 두고 매 창에서 뺀다.
  7 cm 배열에서는 방 전체에 퍼진 소음과 보드 간섭이 세 마이크에 거의 같이 들어와 지연을 0 쪽으로 끌어당긴다 (norm 붕괴).
  계속 깔린 배경만 빼면 새로 나타난 음원의 지연만 남는다. 실시간에서는 '드론 없음' 동안 천천히 갱신한다.

유효 판정: 세 쌍의 상관 피크 ≥ --min-peak, 닫힘 오차 |τ12 + τ23 − τ13| ≤ --max-closure 샘플, norm이 범위 안.
고도각: norm = cos(고도각) (평면 배열이라 위/아래는 구분 못 함). norm으로 대략의 고도각을 같이 기록한다.
샘플레이트: 폴더에 packets.csv가 있으면 수신 시각으로 실제 값을 추정해 쓴다 (HSI 클럭 오차 보정). --fs로 직접 줄 수도 있다.
"""
import argparse, csv, glob, json, os, re, sys
import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gcc_phat as g

FS_NOM = 12500.0
GEOM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "config", "geometry.json")


def positions():
    """config/geometry.json의 실측 간격(세 변 평균)과 번호 방향으로 마이크 좌표를 만든다."""
    try:
        gm = json.load(open(GEOM, encoding="utf-8"))
        d = np.mean([gm["d12_mm"], gm["d13_mm"], gm["d23_mm"]]) / 1000
        return g.mic_positions(d, bool(gm.get("cw", False))), d
    except (OSError, KeyError, ValueError):
        return g.mic_positions(), g.SPACING


def channel_delays_us():
    """config/geometry.json의 채널 고유 지연 [us] (ch1, ch2, ch3). 없으면 0."""
    try:
        cd = json.load(open(GEOM, encoding="utf-8")).get("channel_delay_us", {})
    except (OSError, ValueError):
        cd = {}
    return np.array([float(cd.get(f"ch{k}", 0.0)) for k in (1, 2, 3)])


DELAY_US = channel_delays_us()


def effective_fs(folder, n_samples):
    """packets.csv의 수신 시각과 frame_seq로 실제 프레임률을 맞춰 샘플레이트를 구한다. 없으면 공칭값."""
    p = os.path.join(folder, "packets.csv")
    if not os.path.exists(p):
        return FS_NOM
    r = list(csv.DictReader(open(p)))
    t = np.array([float(x["t_rx"]) for x in r]); fseq = np.array([int(x["frame_seq"]) for x in r])
    if len(t) < 500:
        return FS_NOM
    k = len(t) // 10                                     # 시작 직후 버퍼에 쌓였던 패킷은 제외
    rate = np.polyfit(t[k:], fseq[k:], 1)[0]             # 프레임/초
    return float(rate * 256)


def cross_spectra(x, block, nfft):
    """관측 창 x[3, n]을 50% 겹친 Hann 블록으로 나눠 평균한 스펙트럼 6개: 세 쌍의 교차 B·conj(A) + 세 채널의 자기 |X|²."""
    w = np.hanning(block)
    starts = range(0, x.shape[1] - block + 1, block // 2)
    X = np.array([np.fft.rfft((x[:, s:s + block] - x[:, s:s + block].mean(axis=1, keepdims=True)) * w, nfft, axis=1)
                  for s in starts])                      # [블록, ch, bin]
    return [(X[:, j] * np.conj(X[:, i])).mean(axis=0) for i, j in g.PAIRS] + [(np.abs(X[:, c]) ** 2).mean(axis=0) for c in range(3)]


def estimate(x, fs, pos, spacing, band, block, up=16, eps=0.01, bg=None):
    """관측 창 하나 → 세 쌍 지연, 피크, 방위, norm, 닫힘 오차. bg = background()의 배경 스펙트럼 (교차는 빼고 PHAT)
    snr: 배경 대비 대역 전력 [dB] (bg가 있을 때). 음원이 실제로 들리는 창인지 가르는 데 쓴다."""
    nfft = 2 * block                                     # 순환 상관이 겹치지 않게 2배 제로패딩
    max_lag = spacing / g.SOUND_SPEED * fs + 1.0
    S = cross_spectra(x, block, nfft)
    snr = np.nan
    if bg is not None:
        f = np.fft.rfftfreq(nfft, 1.0 / fs); m = (f >= band[0]) & (f <= band[1])
        snr = float(10 * np.log10(sum(S[3 + c][m].sum() for c in range(3)) / sum(bg[3 + c][m].sum() for c in range(3))))
    tau, peak = [], []
    for k, R in enumerate(S[:3]):
        if bg is not None:
            R = R - bg[k]
        t, p, _, _, _ = g.phat_peak(R, nfft, fs, band, max_lag, up, eps)
        i, j = g.PAIRS[k]
        tau.append(t - (DELAY_US[j] - DELAY_US[i]) * 1e-6 * fs); peak.append(p)      # 채널 고유 지연 보정
    ang, norm = g.tdoa_to_angle(tau, fs, pos)
    return dict(tau=tau, peak=peak, angle=ang, norm=norm, closure=tau[0] + tau[2] - tau[1], snr=snr,
                elev=float(np.degrees(np.arccos(min(norm, 1.0)))))


def is_valid(r, a):
    return bool(min(r["peak"]) >= a.min_peak and abs(r["closure"]) <= a.max_closure and a.min_norm <= r["norm"] <= a.max_norm)


def background(x, fs, a, seconds=60.0):
    """드론 없는 녹음 x[3, N]의 앞 seconds초로 배경 스펙트럼(교차 3 + 자기 3)을 만든다."""
    return cross_spectra(x[:, :int(seconds * fs)], a.block, 2 * a.block)


def run(x, fs, a, start_sample=0, bg=None):
    """연속 신호 x[3, N] → 관측 창마다 결과 목록. 시간은 STREAM 샘플 번호 기준."""
    pos, d = positions()
    n_obs, n_hop = int(round(a.obs * fs)), int(round(a.hop * fs))
    out = []
    for s in range(0, x.shape[1] - n_obs + 1, n_hop):
        r = estimate(x[:, s:s + n_obs], fs, pos, d, tuple(a.band), a.block, bg=bg)
        r.update(s0=start_sample + s, s1=start_sample + s + n_obs, valid=is_valid(r, a),
                 present=bool(np.isnan(r["snr"]) or r["snr"] >= a.min_snr))
        out.append(r)
    return out


def ang_err(est, truth):
    return np.abs((np.asarray(est) - truth + 180) % 360 - 180)


def summarize(res, truth=None):
    """평가 분모 = 음원이 들리는 창(present). 배경이 없으면 모든 창."""
    res = [r for r in res if r["present"]]
    v = np.array([r["valid"] for r in res]); ang = np.array([r["angle"] for r in res])
    s = dict(n=len(res), valid_rate=float(v.mean()) if len(v) else 0.0)
    if v.any():
        av = ang[v]
        c = np.degrees(np.angle(np.mean(np.exp(1j * np.radians(av)))))      # 원형 평균
        s.update(mean_angle=float(c), spread_p95=float(np.percentile(ang_err(av, c), 95)),
                 elev_median=float(np.median([r["elev"] for r, ok in zip(res, v) if ok])))
        if truth is not None:
            e = ang_err(av, truth)
            s.update(err_median=float(np.median(e)), err_p95=float(np.percentile(e, 95)), bias=float(((c - truth + 180) % 360) - 180))
    return s


def load_folder(folder):
    summ = json.load(open(os.path.join(folder, "summary.json"), encoding="utf-8"))
    segs = summ["segments"]
    seg = max(segs, key=lambda s: s["samples"])          # 가장 긴 연속 구간
    x, fs = sf.read(os.path.join(folder, seg["file"]), dtype="int16")
    return x.T.astype(np.float64), seg["start_sample"]


def load_segments(folder):
    """끊김으로 나뉜 연속 구간 전부 → [(x[3, N], 시작 샘플), ...]"""
    summ = json.load(open(os.path.join(folder, "summary.json"), encoding="utf-8"))
    out = []
    for seg in summ["segments"]:
        x, _ = sf.read(os.path.join(folder, seg["file"]), dtype="int16")
        out.append((x.T.astype(np.float64), seg["start_sample"]))
    return out


def add_args(ap):
    ap.add_argument("--obs", type=float, default=0.5, help="관측 창 길이 [s]")
    ap.add_argument("--hop", type=float, default=0.25, help="창 이동 [s]")
    ap.add_argument("--block", type=int, default=512, help="교차 스펙트럼 평균 블록 [샘플 @12.5 kHz]")
    ap.add_argument("--band", type=float, nargs=2, default=(300, 3000), help="사용 대역 [Hz]")
    ap.add_argument("--min-snr", type=float, default=6.0, help="배경 대비 대역 전력이 이 값 [dB] 이상인 창만 평가 (--bg 있을 때)")
    ap.add_argument("--min-peak", type=float, default=0.15)
    ap.add_argument("--max-closure", type=float, default=0.3, help="닫힘 오차 한계 [샘플 @12.5 kHz]")
    ap.add_argument("--min-norm", type=float, default=0.5)
    ap.add_argument("--max-norm", type=float, default=1.3)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("folders", nargs="+", help="Tools/dumps/stream/<label> (이름에 az###가 있으면 정답 방위)")
    ap.add_argument("--fs", type=float, default=0.0, help="샘플레이트 직접 지정 (0이면 packets.csv로 추정)")
    ap.add_argument("--csv", action="store_true", help="폴더마다 doa.csv 저장")
    ap.add_argument("--bg", help="배경 빼기용 드론 없는 녹음 폴더 (예: dumps/stream/quiet_10min). 앞 60 s 사용")
    ap.add_argument("--global-offset", action="store_true",
                    help="정답 있는 녹음들의 공통 회전(편향의 원형 평균)을 빼고 다시 판정. 음원의 0° 위치를 정확히 모를 때")
    add_args(ap)
    ap.add_argument("--no-delay-cal", action="store_true", help="채널 지연 보정을 끈다 (geometry.json channel_delay_us 무시)")
    a = ap.parse_args()
    global DELAY_US
    if a.no_delay_cal:
        DELAY_US = np.zeros(3)
    pos, d = positions()
    print(f"배열 간격 {d * 1000:.1f} mm, 관측 {a.obs} s / 이동 {a.hop} s / 블록 {a.block}, 대역 {a.band[0]:.0f}–{a.band[1]:.0f} Hz, "
          f"배경 빼기 {a.bg or '없음 (D0)'}, 채널 지연 보정 {np.round(DELAY_US, 1).tolist()} us")
    bg = None
    if a.bg:
        xb, _ = load_folder(a.bg)
        bg = background(xb, a.fs or effective_fs(a.bg, xb.shape[1]), a)
    rows, results = [], []
    folders = [f for pat in a.folders for f in (sorted(glob.glob(pat)) if any(c in pat for c in "*?") else [pat])]   # PowerShell은 * 를 펼치지 않음
    for folder in folders:
        segs = load_segments(folder)                     # 중간에 끊겨도 모든 구간을 평가 (관측 창보다 짧은 구간은 건너뜀)
        fs = a.fs or effective_fs(folder, sum(x.shape[1] for x, _ in segs))
        res = [r for x, s0 in segs for r in run(x, fs, a, s0, bg)]
        m = re.search(r"az(\d{1,3})", os.path.basename(os.path.normpath(folder)))
        truth = float(m.group(1)) if m else None
        s = summarize(res, truth)
        line = f"{os.path.basename(os.path.normpath(folder)):16s} fs {fs:8.1f}  평가 창 {s['n']:5d}/{len(res):5d}  유효 {s['valid_rate'] * 100:5.1f}%"
        if "mean_angle" in s:
            line += f"  평균 방위 {s['mean_angle']:7.1f}°  퍼짐 p95 {s['spread_p95']:5.1f}°  고도 중앙 {s['elev_median']:4.0f}°"
        if truth is not None and "err_median" in s:
            line += f"  | 정답 {truth:.0f}°  오차 중앙 {s['err_median']:.1f}° p95 {s['err_p95']:.1f}°  편향 {s['bias']:+.1f}°"
        print(line)
        rows.append(dict(folder=folder, truth=truth, fs=fs, **s))
        results.append(res)
        if a.csv:
            with open(os.path.join(folder, "doa.csv"), "w", newline="") as f:
                w = csv.writer(f); w.writerow(["s0", "s1", "valid", "present", "snr_db", "angle", "elev", "norm", "closure", "tau12", "tau13", "tau23", "peak12", "peak13", "peak23"])
                for r in res:
                    w.writerow([r["s0"], r["s1"], int(r["valid"]), int(r["present"]), f"{r['snr']:.1f}", f"{r['angle']:.2f}", f"{r['elev']:.1f}", f"{r['norm']:.3f}", f"{r['closure']:.3f}",
                                *[f"{t:.3f}" for t in r["tau"]], *[f"{p:.3f}" for p in r["peak"]]])
    t = [r for r in rows if r["truth"] is not None and "err_median" in r]
    if a.global_offset and len(t) > 1:
        off = float(np.degrees(np.angle(np.mean(np.exp(1j * np.radians([r["bias"] for r in t]))))))
        print(f"\n공통 회전 {off:+.1f}° 를 뺀 판정 (정답 + {off:+.1f}°와 비교):")
        for row, res in zip(rows, results):
            if row["truth"] is None or "err_median" not in row:
                continue
            s = summarize(res, (row["truth"] + off) % 360)
            row.update(err_median=s["err_median"], err_p95=s["err_p95"], bias=s["bias"])
            print(f"{os.path.basename(os.path.normpath(row['folder'])):16s} 정답 {row['truth']:5.0f}°  오차 중앙 {s['err_median']:4.1f}° p95 {s['err_p95']:4.1f}°  남은 편향 {s['bias']:+5.1f}°")
    if len(t) > 1:
        print(f"\n정답 있는 녹음 {len(t)}개: 오차 중앙값의 최대 {max(r['err_median'] for r in t):.1f}°, "
              f"p95의 최대 {max(r['err_p95'] for r in t):.1f}°, 유효율 최소 {min(r['valid_rate'] for r in t) * 100:.0f}%  "
              f"(Step7 기준: 중앙 ≤ 5°, p95 ≤ 10°, 유효 ≥ 80%)")


if __name__ == "__main__":
    main()
