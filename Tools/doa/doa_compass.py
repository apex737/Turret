"""
STREAM 모드 실시간 나침반: 보드(doa.c)가 0.25 s마다 보내는 방위 결과(type 0x04)를 그대로 그린다. PC는 계산하지 않는다.

사용법
  python doa/doa_compass.py --port COM8                       # 실시간 (데모)
  python doa/doa_compass.py --port COM8 --save demo1          # 받은 바이트도 dumps/stream/demo1/raw.bin에 저장
  python doa/doa_compass.py --port COM8 --offset -11.4        # 표시 각도에 보정을 더함 (Step7 공통 회전)
  python doa/doa_compass.py --replay dumps/stream/mcu_doa2    # 녹음의 doa_mcu.csv를 실제 시간 간격으로 다시 보기

--save로 저장한 raw.bin은 board/stream_capture.py --replay로 WAV·doa_mcu.csv를 다시 만들 수 있다.
포트는 한 프로그램만 열 수 있으므로 stream_capture.py와 동시에 실행하지 않는다.

읽는 법
  각도  : MIC1 쪽이 0°, 위에서 내려다볼 때 반시계가 +, 시계가 − (−180 ~ +180)
  굵은 화살표 : 가장 최근 결과가 유효 (계산 조건 통과 + 배경보다 6 dB 이상)
  회색 점선   : 소리는 있지만 계산 결과를 믿기 어려움
  화살표 없음 : 배경보다 큰 소리 없음
  점    : 최근 유효 결과들 (오래될수록 흐림)
  4채널(고도각이 실린 결과, Step8e)이면 하늘 지도로 그린다: 바깥 원 = 수평(고도 0°), 가운데 = 머리 위(90°),
         안쪽 점선 원 = 고도 30° · 60°. 화살표 끝과 점이 그 고도에 놓인다 (수평보다 아래는 바깥 원 밖)
  보드는 켜질 때(또는 B1 버튼) 10 s 동안 배경을 배운다. 그동안 나는 소리는 이후 무시된다.
"""
import argparse
import csv
import os
import sys
import time

import numpy as np

import gcc_phat as g
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))   # Tools/
from board.dump_viewer import TYPE_DOA, PacketParser

F_VALID, F_PRESENT, F_BG, F_LEARN = 0x01, 0x02, 0x04, 0x08
INK, MUTED, SERIES, WARN = "#0b0b0b", "#8a8984", "#2a78d6", "#c2410c"
STALE_S = 1.0                      # 이 시간 동안 결과가 없으면 "수신 없음"


def wrap(deg):
    return (deg + 180.0) % 360.0 - 180.0


class Compass:
    def __init__(self, keep, offset, headless=False):
        import matplotlib
        if headless:
            matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.colors import to_rgba
        for f in ("Malgun Gothic", "AppleGothic", "NanumGothic"):
            if any(f == x.name for x in matplotlib.font_manager.fontManager.ttflist):
                plt.rcParams["font.family"] = f; break
        plt.rcParams["axes.unicode_minus"] = False
        self.plt, self.keep, self.offset = plt, keep, offset
        self.rgba = np.array(to_rgba(SERIES))
        self.hist = []                   # (시각, 방위, 반지름)
        self.sky = False                 # 고도각이 실린 결과를 받으면 하늘 지도 모드
        self.n = dict(total=0, valid=0)
        self.last_t = None
        if not headless:
            plt.ion()
        self.fig = plt.figure(figsize=(6.4, 7.6))
        if not headless:
            self.fig.canvas.manager.set_window_title("DOA compass (MCU)")
        ax = self.ax = self.fig.add_axes((0.13, 0.12, 0.74, 0.64), projection="polar")
        ax.set_theta_zero_location("N")                       # 0° (MIC1) 위쪽, 반시계 +
        labels = {a: "0°" if a == 0 else "±180°" if a == 180 else f"{wrap(a):+.0f}°" for a in range(0, 360, 30)}
        for ch, p in enumerate(g.mic_positions()):
            a = int(round(np.degrees(np.arctan2(p[1], p[0])))) % 360
            labels[a] = f"MIC{ch + 1}\n{labels[a]}"
            ax.plot([np.deg2rad(a)], [1.15], "o", mfc="white", mec=INK, mew=1.6, ms=9, clip_on=False, zorder=5)
        ax.set_thetagrids(sorted(labels), [labels[a] for a in sorted(labels)])
        ax.set_rlim(0, 1.15); ax.set_rticks([]); ax.grid(alpha=0.3)
        ax.tick_params(colors=MUTED, labelsize=9); ax.tick_params(axis="x", pad=12)
        ax.spines["polar"].set_color(MUTED)
        self.dots = ax.scatter([], [], s=55, color=SERIES, edgecolors="white", linewidths=1.0, zorder=3)
        self.arrow, = ax.plot([], [], color=INK, lw=4, solid_capstyle="round", zorder=4)
        self.head, = ax.plot([], [], "o", color=INK, ms=10, zorder=4)
        self.big = self.fig.text(0.5, 0.94, "수신 대기", ha="center", va="center", fontsize=34, color=INK)
        self.sub = self.fig.text(0.5, 0.875, "", ha="center", va="center", fontsize=11, color=MUTED)
        self.fig.text(0.5, 0.03, f"MIC1 = 0°, 위에서 볼 때 반시계 +  /  파란 점 = 최근 {keep:g} s 유효 결과"
                      + (f"  /  보정 {offset:+.1f}°" if offset else ""), ha="center", fontsize=9, color=MUTED)

    def _sky_on(self):
        """처음 고도각을 받았을 때 고도 30° · 60° 원과 표시를 그린다"""
        self.sky = True
        th = np.linspace(0, 2 * np.pi, 200)
        for el in (30, 60):
            r = 1 - el / 90
            self.ax.plot(th, np.full_like(th, r), color=MUTED, lw=0.8, ls=":", zorder=1)
            self.ax.text(np.deg2rad(-90), r, f" 고도 {el}°", color=MUTED, fontsize=8, va="bottom")
        self.ax.text(0, 0, "머리 위", color=MUTED, fontsize=8, ha="center", va="top")

    @staticmethod
    def radius(d):
        """하늘 지도 반지름: 수평 1, 머리 위 0. 고도각이 없으면(3채널) 0.88에 고정"""
        if "elev" not in d:
            return 0.88
        return float(np.clip(1 - d["elev"] / 90, 0.0, 1.12))

    def add(self, d, t):
        """d: angle, norm, snr_db, flags (+ elev: 4채널)"""
        if "elev" in d and not self.sky:
            self._sky_on()
        rad = self.radius(d)
        self.n["total"] += 1; self.last_t = t
        f = int(d["flags"]); ang = wrap(d["angle"] + self.offset)
        learning = bool(f & F_LEARN) and not f & F_BG       # 첫 배경 학습 중: 배경이 없어 PRESENT가 항상 1
        ok = bool(f & F_VALID) and bool(f & F_PRESENT) and not learning
        self.n["valid"] += ok
        if ok:
            self.hist.append((t, ang, rad))
        if learning:
            big, col, arrow = "배경 학습 중, 조용히", WARN, None
        elif ok:
            big, col, arrow = f"{ang:+.0f}°", INK, "solid"
        elif f & F_PRESENT:
            big, col, arrow = f"{ang:+.0f}° ?", MUTED, "dashed"
        else:
            big, col, arrow = "소리 없음", MUTED, None
        self.big.set_text(big); self.big.set_color(col)
        el = f"고도 {d['elev']:+.0f}°  /  " if "elev" in d else ""      # 4채널 (Step8e)
        self.sub.set_text(f"{el}배경 대비 {d['snr_db']:+.1f} dB  /  norm {d['norm']:.2f}  /  "
                          f"유효 {self.n['valid']}/{self.n['total']}")
        th = np.deg2rad(ang)
        if arrow:
            c = INK if arrow == "solid" else MUTED
            self.arrow.set_data([th, th], [0, rad]); self.arrow.set_color(c); self.arrow.set_linestyle(arrow)
            self.arrow.set_linewidth(4 if arrow == "solid" else 2)
            self.head.set_data([th], [rad]); self.head.set_color(c)
        else:
            self.arrow.set_data([], []); self.head.set_data([], [])
        self._dots(t)

    def _dots(self, now):
        """최근 keep 초 안의 유효 결과만 점으로 (오래될수록 흐림)"""
        self.hist = [h for h in self.hist if now - h[0] <= self.keep]
        if not self.hist:
            self.dots.set_offsets(np.empty((0, 2))); return
        t, a, r = np.array(self.hist).T
        rgba = np.tile(self.rgba, (len(a), 1)); rgba[:, 3] = np.clip(1.0 - (now - t) / self.keep, 0.12, 1.0)
        self.dots.set_offsets(np.column_stack((np.deg2rad(a), r if self.sky else np.ones_like(a))))
        self.dots.set_facecolors(rgba)

    def tick(self, now):
        self._dots(now)
        if self.last_t is not None and now - self.last_t > STALE_S:
            self.big.set_text("수신 없음"); self.big.set_color(WARN)
            self.arrow.set_data([], []); self.head.set_data([], [])

    def alive(self):
        return self.plt.fignum_exists(self.fig.number)

    def draw(self, pause=0.03):
        self.fig.canvas.draw_idle(); self.plt.pause(pause)


def run_serial(a):
    import queue, serial, threading
    raw = None
    if a.save:
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dumps", "stream", a.save)
        os.makedirs(out, exist_ok=True); raw = open(os.path.join(out, "raw.bin"), "wb")
        print(f"저장 → {os.path.normpath(out)}\\raw.bin  (나중에 board/stream_capture.py --replay)")
    cp, parser, q, stop = Compass(a.keep, a.offset), PacketParser(), queue.Queue(), threading.Event()
    with serial.Serial(a.port, a.baud, timeout=0.05) as ser:
        try:
            ser.set_buffer_size(rx_size=1 << 20)
        except (AttributeError, ValueError, serial.SerialException):
            pass
        ser.reset_input_buffer()

        def reader():                                   # 그리기가 멈춰도 포트 읽기는 계속
            while not stop.is_set():
                d = ser.read(ser.in_waiting or 1)
                if d:
                    q.put(d)
        threading.Thread(target=reader, daemon=True).start()
        print(f"{a.port} @ {a.baud}  (창을 닫거나 Ctrl+C로 종료)")
        try:
            while cp.alive():
                while True:
                    try:
                        data = q.get_nowait()
                    except queue.Empty:
                        break
                    if raw:
                        raw.write(data)
                    for p in parser.feed(data):
                        if p["type"] == TYPE_DOA:
                            cp.add(p["doa"], time.time())
                cp.tick(time.time()); cp.draw()
        except KeyboardInterrupt:
            pass
        stop.set()
    if raw:
        raw.close()


def run_replay(a):
    rows = list(csv.DictReader(open(os.path.join(a.replay, "doa_mcu.csv"), encoding="utf-8")))
    rows = [dict(t=float(r["t_rx"]), angle=float(r["angle"]), norm=float(r["norm"]), snr_db=float(r["snr_db"]),
                 flags=int(r["flags"]), **({"elev": float(r["elev"])} if "elev" in r else {})) for r in rows]
    if a.snapshot:                                      # 창 없이 n번째 결과까지 그려 PNG로 (검증용)
        cp = Compass(a.keep, a.offset, headless=True)
        for r in rows[:a.snapshot_at]:
            cp.add(r, r["t"])
        cp.fig.savefig(a.snapshot, dpi=100); print(f"→ {a.snapshot}"); return
    cp = Compass(a.keep, a.offset)
    t0, w0 = rows[0]["t"], time.time()
    for r in rows:
        while cp.alive() and (time.time() - w0) * a.speed < r["t"] - t0:
            cp.tick(t0 + (time.time() - w0) * a.speed); cp.draw(0.02)
        if not cp.alive():
            return
        cp.add(r, r["t"])
    print("재생 끝 (창을 닫으면 종료)")
    while cp.alive():
        cp.draw(0.1)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port"); ap.add_argument("--baud", type=int, default=1500000)   # Step8e 4채널 펌웨어
    ap.add_argument("--save", metavar="LABEL", help="받은 바이트를 dumps/stream/LABEL/raw.bin에 저장")
    ap.add_argument("--offset", type=float, default=0.0, help="표시 각도에 더할 보정 [deg]")
    ap.add_argument("--keep", type=float, default=3.0, help="최근 유효 결과를 점으로 남길 시간 [s]")
    ap.add_argument("--replay", help="dumps/stream/<label> 폴더 (doa_mcu.csv)")
    ap.add_argument("--speed", type=float, default=1.0, help="재생 배속")
    ap.add_argument("--snapshot", help=argparse.SUPPRESS); ap.add_argument("--snapshot-at", type=int, default=200, help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.replay:
        run_replay(a)
    elif a.port:
        run_serial(a)
    else:
        ap.error("--port 또는 --replay가 필요하다")


if __name__ == "__main__":
    main()
