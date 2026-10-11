"""
실시간 음원 방향 표시: 덤프 패킷을 받을 때마다 GCC-PHAT으로 각도를 구해 나침반에 그린다.

사용법
  python doa_live.py --port COM8                      # 실시간 측정
  python doa_live.py --port COM8 --truth 120          # 실제 각도를 알고 측정 (오차 통계 출력)
  python doa_live.py --replay dumps/20261010_153000   # 저장된 세션 다시 보기

실시간 측정은 실행할 때마다 dumps/<날짜_시각>/ 폴더를 새로 만들어
  f_<seq>.npz  원파형 (gcc_phat.py, dump_viewer.py --replay 로 다시 볼 수 있음)
  log.csv      캡처별 지연, 각도, 품질, MCU 결과와의 차이
을 저장한다. 종료는 Ctrl+C.

MCU 결과 비교 (펌웨어 CAPTURE_SEND_RAW 1)
  펌웨어가 결과 패킷(type 0x02)을 보내면, 같은 frame_seq의 원파형을 PC에서 MCU와 같은 조건(up=1)으로
  다시 계산해 차이를 출력한다. 구현이 같으면 지연 차이는 0.01 샘플 안쪽이어야 한다.

결과 전용 모드 (펌웨어 CAPTURE_SEND_RAW 0)
  원파형 없이 결과 패킷만 온다. MCU가 계산한 값을 그대로 나침반에 표시하고 log.csv에 src=mcu 로 남긴다.
  원파형이 없으므로 npz는 저장되지 않고 PC와의 비교도 없다.

나침반 읽는 법
  방향  : 중심에서 MIC1 쪽이 0°, 반시계가 +  (gcc_phat.py 의 각도 규칙)
  반지름: norm. 음원이 멀고 마이크와 같은 평면이면 1 근처, 위/아래에서 나면 작아진다.
  화살표: 가장 최근 캡처.  점: 최근의 신뢰 가능한 캡처들.
  신뢰 낮음(peak < --min-peak 이거나 norm이 --min-norm ~ --max-norm 밖)은 회색 점선 화살표로만 표시하고 통계에서 뺀다.
"""
import argparse
import csv
import os
import time

import numpy as np

import gcc_phat as g
from dump_viewer import TYPE_RESULT, PacketParser

INK, MUTED, SERIES = "#0b0b0b", "#8a8984", "#2a78d6"
R_MAX = 1.3


def wrap(deg):
    """각도를 -180 ~ +180 범위로."""
    return (deg + 180.0) % 360.0 - 180.0


def circ_stats(deg):
    """각도들의 원형 평균과 원형 표준편차 [deg]. (179°와 -179°의 평균이 0°가 되지 않게)"""
    z = np.exp(1j * np.deg2rad(deg)).mean()
    return float(np.degrees(np.angle(z))), float(np.degrees(np.sqrt(max(-2.0 * np.log(max(abs(z), 1e-12)), 0.0))))


def estimate(pkt, fs, kw, args):
    """패킷 하나 → 결과 한 줄."""
    r = g.analyze(pkt["data"], fs, **kw)
    flags = int(pkt["flags"])
    peak = float(min(r["peak"]))
    return dict(seq=int(pkt["seq"]), frame_seq=int(pkt["frame_seq"]), flags=flags,
                tau12=r["tau"][0], tau13=r["tau"][1], tau23=r["tau"][2], closure=r["closure"],
                peak=peak, angle=r["angle"], norm=r["norm"],
                ok=bool(g.is_reliable(r, args) and not flags & g.FLAG_MANUAL), src="pc")


def from_mcu(pkt):
    """원파형 없이 결과 패킷만 온 경우(펌웨어 CAPTURE_SEND_RAW 0): MCU 값으로 결과 한 줄을 만든다.
    신뢰 여부는 MCU의 판정(VALID 플래그)을 그대로 따른다."""
    m = pkt["result"]
    flags = int(pkt["flags"])
    peak = float(min(m["peak"]))
    return dict(seq=int(pkt["seq"]), frame_seq=int(pkt["frame_seq"]), flags=flags,
                tau12=m["tau"][0], tau13=m["tau"][1], tau23=m["tau"][2],
                closure=m["tau"][0] + m["tau"][2] - m["tau"][1],
                peak=peak, angle=m["angle"], norm=m["norm"],
                ok=bool(flags & g.FLAG_VALID and not flags & g.FLAG_MANUAL), src="mcu",
                mcu_valid=int(bool(flags & g.FLAG_VALID)), mcu_us=int(m["proc_us"]))


def describe(row, truth):
    tags = ("CLIP " if row["flags"] & g.FLAG_CLIP else "") + ("MANUAL " if row["flags"] & g.FLAG_MANUAL else "")
    if row["src"] == "mcu":
        tags += f"[MCU {row['mcu_us'] / 1000:.1f} ms]"
    err = f"  err {wrap(row['angle'] - truth):+6.1f}°" if truth is not None and row["ok"] else ""
    return (f"seq {row['seq']:5d}  angle {row['angle']:+7.1f}°  norm {row['norm']:.2f}  peak {row['peak']:.2f}  "
            f"tau {row['tau12']:+6.2f} {row['tau13']:+6.2f} {row['tau23']:+6.2f}  "
            f"{'ok ' if row['ok'] else 'low'}{err}  {tags}")


def compare_mcu(x, fs, kw, mcu, flags, args):
    """MCU 결과와, 같은 원파형을 PC에서 MCU와 같은 조건(up=1)으로 계산한 값의 차이."""
    ref = g.analyze(x, fs, **{**kw, "up": 1})
    mcu_valid = bool(flags & g.FLAG_VALID)
    return dict(mcu_tau12=mcu["tau"][0], mcu_tau13=mcu["tau"][1], mcu_tau23=mcu["tau"][2],
                mcu_peak=float(min(mcu["peak"])), mcu_angle=mcu["angle"], mcu_norm=mcu["norm"],
                mcu_us=int(mcu["proc_us"]), mcu_valid=int(mcu_valid),
                d_valid=int(mcu_valid != g.is_reliable(ref, args)),
                d_tau=float(max(abs(m - p) for m, p in zip(mcu["tau"], ref["tau"]))),
                d_peak=float(max(abs(m - p) for m, p in zip(mcu["peak"], ref["peak"]))),
                d_angle=float(wrap(mcu["angle"] - ref["angle"])),
                d_onset=int(mcu["onset"]) - int(ref["onset"]))


def describe_mcu(row):
    return (f"      MCU  angle {row['mcu_angle']:+7.1f}°  norm {row['mcu_norm']:.2f}  peak {row['mcu_peak']:.2f}  "
            f"tau {row['mcu_tau12']:+6.2f} {row['mcu_tau13']:+6.2f} {row['mcu_tau23']:+6.2f}  "
            f"{row['mcu_us'] / 1000:.1f} ms  |  PC와 차이: tau {row['d_tau']:.3f}  peak {row['d_peak']:.3f}  "
            f"angle {row['d_angle']:+.2f}°  onset {row['d_onset']:+d}  "
            f"판정 {'valid' if row['mcu_valid'] else 'low'}{' (PC와 다름)' if row['d_valid'] else ''}")


def print_summary(rows, truth):
    ok = [r for r in rows if r["ok"]]
    print(f"\n캡처 {len(rows)}개 중 신뢰 가능 {len(ok)}개")
    cmp = [r for r in rows if "d_tau" in r]
    if cmp:
        same = [r for r in cmp if r["d_onset"] == 0]
        print(f"  MCU 비교 {len(cmp)}개: onset 일치 {len(same)}개,  MCU 계산 시간 중앙값 "
              f"{np.median([r['mcu_us'] for r in cmp]) / 1000:.1f} ms (최대 {max(r['mcu_us'] for r in cmp) / 1000:.1f} ms)")
        print(f"    신뢰 판정이 PC와 다른 캡처 {sum(r['d_valid'] for r in cmp)}개")
        if same:
            print(f"    onset이 일치한 캡처에서 최대 차이: 지연 {max(r['d_tau'] for r in same):.4f} 샘플,  "
                  f"peak {max(r['d_peak'] for r in same):.4f},  각도 {max(abs(r['d_angle']) for r in same):.3f}°")
    only = [r for r in rows if r["src"] == "mcu"]
    if only:
        print(f"  MCU 결과만 받은 캡처 {len(only)}개: 계산 시간 중앙값 "
              f"{np.median([r['mcu_us'] for r in only]) / 1000:.1f} ms (최대 {max(r['mcu_us'] for r in only) / 1000:.1f} ms)")
        gap = np.diff([r["frame_seq"] for r in only]) * 1024 / g.FS           # 프레임 번호 차이 → 초
        gap = gap[gap > 0]                                                    # MCU가 리셋되면 번호가 되돌아감
        if gap.size:
            print(f"    결과 사이 간격: 최소 {gap.min():.2f} s, 중앙값 {np.median(gap):.2f} s")
    if not ok:
        return
    ang = np.array([r["angle"] for r in ok])
    mean, std = circ_stats(ang)
    print(f"  |closure| 중앙값 {np.median(np.abs([r['closure'] for r in ok])):.2f} 샘플  "
          f"norm 중앙값 {np.median([r['norm'] for r in ok]):.2f}")
    print(f"  각도 평균 {mean:+.1f}°  흩어짐(원형 표준편차) {std:.1f}°"
          + ("" if truth is not None else "   ← 음원이 한 자리에 있었을 때만 의미 있음"))
    if truth is not None:
        err = wrap(ang - truth)
        print(f"  실제 {truth:+.1f}° 대비: 평균 오차 {wrap(mean - truth):+.1f}°  최대 |오차| {np.abs(err).max():.1f}°")


class Session:
    """세션 폴더에 npz와 log.csv를 저장한다."""

    FIELDS = ("time", "seq", "frame_seq", "flags", "tau12", "tau13", "tau23", "closure",
              "peak", "angle", "norm", "ok", "truth", "src",
              "mcu_tau12", "mcu_tau13", "mcu_tau23", "mcu_peak", "mcu_angle", "mcu_norm", "mcu_us", "mcu_valid",
              "d_tau", "d_peak", "d_angle", "d_onset", "d_valid")

    def __init__(self, root, truth):
        name = time.strftime("%Y%m%d_%H%M%S") + ("" if truth is None else f"_truth{truth:+04.0f}")
        self.dir = os.path.join(root, name)
        os.makedirs(self.dir)
        self.truth = truth
        self.file = open(os.path.join(self.dir, "log.csv"), "w", newline="", encoding="utf-8")
        self.writer = csv.DictWriter(self.file, fieldnames=self.FIELDS)
        self.writer.writeheader()

    def save_raw(self, pkt, fs):
        np.savez(os.path.join(self.dir, f"f_{pkt['seq']:06d}.npz"), data=pkt["data"], seq=pkt["seq"],
                 frame_seq=pkt["frame_seq"], flags=pkt["flags"], fs=fs)

    def log(self, row):
        out = {k: (f"{v:.4f}" if isinstance(v, float) else v) for k, v in row.items()}
        out.update(ok=int(row["ok"]), truth="" if self.truth is None else self.truth)
        out.setdefault("time", time.strftime("%H:%M:%S"))
        self.writer.writerow(out)
        self.file.flush()

    def close(self):
        self.file.close()


class Compass:
    def __init__(self, pos, truth, keep, headless):
        import matplotlib
        if headless:
            matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.colors import to_rgba
        from matplotlib.lines import Line2D

        self.plt, self.keep, self.truth, self.headless = plt, keep, truth, headless
        self.series_rgba = np.array(to_rgba(SERIES))
        self.history = []                                  # 신뢰 가능한 캡처의 (angle, norm)
        self.arrow = None
        if not headless:
            plt.ion()
        self.fig = plt.figure(figsize=(6.6, 8.0))
        ax = self.ax = self.fig.add_axes((0.14, 0.17, 0.72, 0.62), projection="polar")
        ax.set_theta_zero_location("N")
        labels = {a: "0°" if a == 0 else "±180°" if a == 180 else f"{wrap(a):+.0f}°" for a in range(0, 360, 30)}
        for ch, p in enumerate(pos):                                   # 마이크가 있는 방향을 눈금 이름에 표시
            a = int(round(np.degrees(np.arctan2(p[1], p[0])))) % 360
            labels[a] = f"MIC{ch + 1}\n{labels[a]}"
            ax.plot([np.deg2rad(a)], [R_MAX], "o", mfc="white", mec=INK, mew=1.6, ms=9, clip_on=False, zorder=5)
        ax.set_thetagrids(sorted(labels), [labels[a] for a in sorted(labels)])
        ax.set_rlim(0, R_MAX)
        ax.set_rticks([0.5, 1.0])
        ax.set_rlabel_position(22)
        ax.tick_params(colors=MUTED, labelsize=9)
        ax.tick_params(axis="x", pad=12)                               # 테두리의 마이크 표시와 겹치지 않게
        ax.grid(alpha=0.3)
        ax.spines["polar"].set_color(MUTED)
        theta = np.linspace(0, 2 * np.pi, 361)
        ax.plot(theta, np.ones_like(theta), color=MUTED, lw=1.0)       # norm = 1 기준 원
        handles = [Line2D([], [], color=INK, lw=2.4, label="latest capture"),
                   Line2D([], [], color=SERIES, marker="o", ls="", ms=7, label=f"reliable captures (last {keep})"),
                   Line2D([], [], color=MUTED, lw=1.6, ls="--", label="latest, low confidence")]
        if truth is not None:
            ax.plot([np.deg2rad(truth)] * 2, [0, R_MAX], color=INK, lw=1.0, ls=":")
            handles.append(Line2D([], [], color=INK, lw=1.0, ls=":", label=f"truth {truth:+.0f}°"))
        self.dots = ax.scatter([], [], s=45, color=SERIES, edgecolors="white", linewidths=1.0, zorder=3)
        self.fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.04), ncol=2, fontsize=9, frameon=False)
        self.fig.text(0.5, 0.02, "radius = norm  (1.0: far source in the mic plane, smaller: source above/below)",
                      ha="center", va="center", fontsize=8.5, color=MUTED)
        self.big = self.fig.text(0.5, 0.95, "waiting for sound…", ha="center", va="center", fontsize=30, color=INK)
        self.sub = self.fig.text(0.5, 0.9, "", ha="center", va="center", fontsize=11, color=MUTED)
        self.mcu = self.fig.text(0.5, 0.872, "", ha="center", va="center", fontsize=10, color=MUTED)
        self.refresh()

    def show(self, row):
        if row["ok"]:
            self.history = (self.history + [(row["angle"], row["norm"])])[-self.keep:]
        if self.history:
            ang, norm = np.array(self.history).T
            age = np.arange(len(ang))[::-1]                            # 0 = 가장 최근
            rgba = np.tile(self.series_rgba, (len(ang), 1))
            rgba[:, 3] = np.clip(1.0 - age / self.keep, 0.15, 1.0)     # 오래될수록 흐리게
            self.dots.set_offsets(np.column_stack((np.deg2rad(ang), np.minimum(norm, R_MAX))))
            self.dots.set_facecolors(rgba)
        if self.arrow is not None:
            self.arrow.remove()
        style = dict(arrowstyle="-|>", lw=2.4, color=INK) if row["ok"] else \
            dict(arrowstyle="-|>", lw=1.6, color=MUTED, ls="--")
        self.arrow = self.ax.annotate("", xy=(np.deg2rad(row["angle"]), min(row["norm"], R_MAX)), xytext=(0, 0),
                                      arrowprops=dict(mutation_scale=18, **style), zorder=4)
        self.big.set_text(f"{row['angle']:+.1f}°")
        self.big.set_color(INK if row["ok"] else MUTED)
        note = "" if row["ok"] else "low confidence   "
        if self.truth is not None and row["ok"]:
            note = f"error {wrap(row['angle'] - self.truth):+.1f}°   "
        self.sub.set_text(f"{note}seq {row['seq']}   peak {row['peak']:.2f}   norm {row['norm']:.2f}")
        self.mcu.set_text(f"computed on MCU   {row['mcu_us'] / 1000:.1f} ms" if row["src"] == "mcu" else "")
        self.refresh()

    def show_mcu(self, row):
        """방금 표시한 캡처에 대한 MCU 결과를 한 줄 덧붙인다."""
        self.mcu.set_text(f"MCU {row['mcu_angle']:+.1f}°   diff {row['d_angle']:+.2f}°   "
                          f"tau diff {row['d_tau']:.3f} samples   {row['mcu_us'] / 1000:.1f} ms")
        self.refresh()

    def refresh(self):
        if not self.headless:
            self.fig.canvas.draw_idle()
            self.plt.pause(0.01)


def run_serial(args, kw):
    import serial

    session = Session(args.out, args.truth)
    compass = Compass(kw["pos"], args.truth, args.keep, headless=False)
    parser = PacketParser()
    rows = []
    pending = None                 # (row, 원파형): MCU 결과 패킷을 기다리는 캡처. 로그는 결과가 오거나 다음 캡처가 올 때 쓴다
    print(f"saving to {session.dir}")
    with serial.serial_for_url(args.port, args.baud, timeout=0.05) as ser:
        ser.reset_input_buffer()
        print(f"listening on {args.port} @ {args.baud} baud ... (Ctrl+C to quit)")
        try:
            while True:
                data = ser.read(ser.in_waiting or 1)
                for pkt in parser.feed(data):
                    if pkt["type"] == TYPE_RESULT:
                        if pending and pending[0]["frame_seq"] == pkt["frame_seq"]:
                            row, x = pending                      # 방금 받은 원파형의 짝 → 비교
                            row.update(compare_mcu(x, args.fs, kw, pkt["result"], int(pkt["flags"]), args))
                            print(describe_mcu(row))
                            compass.show_mcu(row)
                        else:                                     # 원파형 없이 결과만 옴 → MCU 값을 그대로 표시
                            if pending:
                                session.log(pending[0])
                                pending = None
                            row = from_mcu(pkt)
                            row["time"] = time.strftime("%H:%M:%S")
                            rows.append(row)
                            session.log(row)
                            print(describe(row, args.truth))
                            compass.show(row)
                        continue
                    if pending:
                        session.log(pending[0])
                    row = estimate(pkt, args.fs, kw, args)
                    row["time"] = time.strftime("%H:%M:%S")
                    rows.append(row)
                    session.save_raw(pkt, args.fs)
                    print(describe(row, args.truth))
                    compass.show(row)
                    pending = (row, pkt["data"])
                compass.plt.pause(0.001)
        except KeyboardInterrupt:
            pass
    if pending:
        session.log(pending[0])
    session.close()
    print("stopped.", parser.stats)
    print_summary(rows, args.truth)
    print(f"saved to {session.dir}")


def run_replay(args, kw):
    compass = Compass(kw["pos"], args.truth, args.keep, headless=bool(args.save))
    rows = []
    for path in g.list_files(args.replay):
        x, fs, flags, seq = g.load(path)
        z = np.load(path)
        pkt = dict(data=x, flags=flags, seq=seq, frame_seq=int(z["frame_seq"]) if "frame_seq" in z else -1)
        row = estimate(pkt, fs, kw, args)
        rows.append(row)
        print(describe(row, args.truth))
        compass.show(row)
        if not args.save and args.delay > 0:
            compass.plt.pause(args.delay)
    print_summary(rows, args.truth)
    if args.save:
        compass.fig.savefig(args.save, dpi=130)
        print(f"saved {args.save}")
    else:
        compass.plt.ioff()
        compass.plt.show()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", help="시리얼 포트 (예: COM8)")
    ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--fs", type=float, default=g.FS)
    ap.add_argument("--out", default="dumps", help="세션 폴더를 만들 위치")
    ap.add_argument("--truth", type=float, help="실제 음원 각도 [deg]. 주면 오차를 같이 표시")
    ap.add_argument("--keep", type=int, default=30, help="나침반에 남길 최근 캡처 수")
    ap.add_argument("--replay", help="저장된 세션 폴더(또는 npz 파일) 다시 보기")
    ap.add_argument("--delay", type=float, default=0.3, help="다시 보기에서 캡처 사이 간격 [s]")
    ap.add_argument("--save", help="다시 보기의 마지막 화면을 창 없이 이 파일로 저장")
    g.add_analysis_args(ap)
    args = ap.parse_args()
    kw = g.kwargs_from(args)
    if args.replay:
        run_replay(args, kw)
    elif args.port:
        run_serial(args, kw)
    else:
        ap.error("--port 또는 --replay 중 하나가 필요합니다")


if __name__ == "__main__":
    main()
