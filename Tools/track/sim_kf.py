"""Step8c KF 합성 시험: 정답 방위를 아는 가짜 방위열로 KF가 의도대로 도는지 본다 (녹음 없이).

    python track/sim_kf.py                      → reports/step8c/kf_synth.png, 수치는 화면에
    python track/sim_kf.py --sigma-a 10 --sigma-z 3

장면 (0.246 s마다 방위 하나, doa.c와 같은 주기)
  A 고정 음원     60°에 고정 (세탁기·엔진 역할). Step8c 기준: |ω| ≤ 3°/s인 시간 ≥ 95%
  B 일정 회전     30°/s로 돈다 (핸드폰을 들고 배열 주위를 걷는 녹음 역할)
  C 직선 통과     15 m/s, 최근접 10 m (정찰기·드론이 지나감). 최근접에서 각속도 약 86°/s
  D 측정 끊김     B와 같고 3 s 동안 방위가 없음 (VALID 아님)
측정 = 정답 + 가우스 잡음(--noise, 기본 3°). 10%는 무효(NaN), 3%는 엉뚱한 방위(균일 분포, 반사·다른 음원 흉내).
"""
import argparse
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import track.kf as kf   # noqa: E402

OUT = os.path.join(HERE, "..", "..", "reports", "step8c")


def scenes(T=30.0):
    t = np.arange(0, T, kf.DT)
    v, d, tc = 15.0, 10.0, T / 2
    return t, {
        "A 고정 음원 (60°)": np.full_like(t, 60.0),
        "B 일정 회전 (30°/s)": kf.wrap(30.0 * t),
        "C 직선 통과 (15 m/s, 10 m)": np.degrees(np.arctan2(v * (t - tc), d)),
        "D 3 s 끊김 (30°/s)": kf.wrap(30.0 * t),
    }


def measure(truth, t, rng, noise, p_invalid=0.10, p_outlier=0.03, gap=None):
    z = kf.wrap(truth + noise * rng.standard_normal(len(truth)))
    out = rng.random(len(z)) < p_outlier
    z[out] = rng.uniform(-180, 180, out.sum())
    z[rng.random(len(z)) < p_invalid] = np.nan
    if gap:
        z[(t >= gap[0]) & (t < gap[1])] = np.nan
    return z


def true_omega(truth, t):
    return np.gradient(np.unwrap(np.radians(truth)), t) * 180 / np.pi


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--sigma-a", type=float, default=kf.SIGMA_A)
    ap.add_argument("--sigma-z", type=float, default=kf.SIGMA_Z)
    ap.add_argument("--noise", type=float, default=3.0, help="합성 측정 잡음 표준편차 [deg]")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    for f in ("Malgun Gothic", "AppleGothic", "NanumGothic"):
        if any(f == x.name for x in matplotlib.font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = f; break
    plt.rcParams["axes.unicode_minus"] = False

    rng = np.random.default_rng(a.seed)
    t, S = scenes()
    fig, axes = plt.subplots(len(S), 2, figsize=(13, 11), sharex=True)
    print(f"σa = {a.sigma_a} deg/s², σz = {a.sigma_z} deg, 합성 잡음 {a.noise}°, 주기 {kf.DT:.3f} s")
    for row, (name, truth) in enumerate(S.items()):
        z = measure(truth, t, rng, a.noise, gap=(12, 15) if name.startswith("D") else None)
        r = kf.track(t, z, sigma_a=a.sigma_a, sigma_z=a.sigma_z)
        th = np.array([o.get("theta", np.nan) for o in r]); om = np.array([o.get("omega", np.nan) for o in r])
        sd = np.array([o.get("sd_theta", np.nan) for o in r]); sdw = np.array([o.get("sd_omega", np.nan) for o in r])
        st = [o["status"] for o in r]
        w_true = true_omega(truth, t)
        ok = ~np.isnan(th)
        err = np.abs(kf.wrap(th[ok] - truth[ok]))
        settle = t > 3.0                                     # 시작 3 s는 수렴 구간으로 빼고 셈
        msg = (f"{name}: 방위 오차 중앙 {np.median(err):.2f}° p95 {np.percentile(err, 95):.2f}° · "
               f"ω 오차 중앙 {np.nanmedian(np.abs(om - w_true)[settle]):.1f}°/s · "
               f"버림 {st.count('reject')} 놓침 {st.count('lost')} 예측만 {st.count('coast')}")
        if name.startswith("A"):
            msg += f" · |ω| ≤ 3°/s 시간 {np.mean(np.abs(om[settle & ok]) <= 3.0) * 100:.0f}% (기준 ≥ 95%)"
        print(msg)

        ax = axes[row, 0]
        ax.plot(t, z, ".", ms=4, color="#8a8984", label="측정 (무효·엉뚱한 값 포함)")
        ax.plot(t, truth, color="#1f2328", lw=1, label="정답")
        ax.plot(t, th, color="#2a78d6", lw=1.8, label="KF 방위")
        ax.fill_between(t, th - 2 * sd, th + 2 * sd, color="#2a78d6", alpha=0.15, label="±2σ")
        rj = np.array([s == "reject" for s in st])
        ax.plot(t[rj], z[rj], "x", color="#c0362c", ms=6, label="관문에서 버림")
        ax.set_ylim(-190, 190); ax.set_ylabel("방위 [°]"); ax.set_title(name, loc="left", fontsize=10)
        ax = axes[row, 1]
        ax.plot(t, w_true, color="#1f2328", lw=1, label="정답 ω")
        ax.plot(t, om, color="#eb6834", lw=1.8, label="KF ω")
        ax.fill_between(t, om - 2 * sdw, om + 2 * sdw, color="#eb6834", alpha=0.15)
        if name.startswith("A"):
            ax.axhspan(-3, 3, color="#1a7f4b", alpha=0.12, label="|ω| ≤ 3°/s")
            ax.set_ylim(-30, 30)
        ax.set_ylabel("각속도 [°/s]")
        if row == 0:
            axes[0, 0].legend(fontsize=7, loc="upper right"); ax.legend(fontsize=7, loc="upper right")
    for ax in axes[-1]:
        ax.set_xlabel("시간 [s]")
    fig.suptitle(f"Step8c KF 합성 시험 · σa {a.sigma_a} °/s², σz {a.sigma_z}° · 측정 잡음 {a.noise}°, 무효 10%, 엉뚱한 값 3%", fontsize=11)
    fig.tight_layout()
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, "kf_synth.png"); fig.savefig(p, dpi=90); print(f"→ {os.path.normpath(p)}")


if __name__ == "__main__":
    main()
