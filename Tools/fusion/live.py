# Tools/.venv
"""Step10 STM32 + PC 실시간 결합 (스피드런 2026-11-04). 보드 STREAM 모드의 패킷을 받아 0.25 s마다 카메라 명령 하나를 낸다.

    python fusion/live.py --port COM8 [--label run1] [--minutes 30] [--lead 0.3]    # 실시간 (stream_capture처럼 raw.bin도 저장)
    python fusion/live.py --replay dumps/stream/<label>/raw.bin                     # 저장한 바이트로 다시
    python fusion/live.py --sim dumps/stream/<label>                                # B0 패킷이 없는 옛 녹음: 방향 = doa_mcu.csv, B0 = PC가 PCM으로 계산

흐름 (패킷 → 출력)
  PCM  (20 ms마다)   now = 받은 마지막 샘플 번호. RESYNC면 입력 끊김 → 결합기·움직임 판정·KF를 그 샘플에서 끊는다 (I1·I4)
  DOA  (0.25 s마다)  유효·present 방위 → 움직임 판정(track/motion.py) · 추적 KF(track/kf.py) · 결합기 on_doa → 출력 하나
  B0   (0.49 s마다)  고조파 점수 → 고도·움직임 규칙(고도각 < 10°면 후보에서 뺌, 고도각이 없으면 정지 3 s에 ×½, --no-motion이면 끔) → 조용한 창 거름 → 문턱 13.1 → 결합기 on_cls
                     조용한 창 = B0 창과 겹치는 방향 창 중 present(배경보다 6 dB 이상)가 절반 미만.
                     절대 dBFS(Step8b의 보드 바닥 + 6 dB)가 아니라 배경 대비로 본다 — 마이크·이득이 바뀌면 바닥이 달라져서
                     (T2_fpv MIC1 바닥 약 −62 dBFS 대 Step8b quiet_10min −51 dBFS). --quiet-db를 주면 절대 기준을 쓴다
  출력: ("none" | "drone", θ | "unknown") + 이유, 앞당긴 방위 θ + ω·lead (KF, 카메라·서보 구동 지연만큼)
  통신 단절: 실제 시간으로 LINK_TIMEOUT(0.5 s) 넘게 패킷이 없으면 "unknown (link)" (combine.py 규칙 5)
저장 (dumps/fusion/<label>/): fusion.csv (출력마다), summary.json (상태별 수, 최대 경과 시간, 끊김·단절 수)
"""
import argparse, csv, json, os, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, os.path.join(HERE, "..", "board")); sys.path.insert(0, os.path.join(HERE, "..", "doa"))
from dump_viewer import PacketParser, TYPE_PCM, TYPE_DOA, TYPE_B0, TYPE_STAT
import fusion.combine as cb
import track.motion as mo
import track.kf as kf

FS = 12500.0
N = 256
F_RESYNC = 0x02
DOA_OBS = 6250                   # 방향 창 길이 [샘플] (doa.h DOA_OBS)
B0_THR = 13.1                    # harm.h HARM_THR
QUIET_DB = None                  # 절대 기준 [dBFS] (None = 방향 창 present로 판단). Step8b 규칙은 −45.1 (그때 보드 바닥 −51.1 + 6 dB)
OUT = os.path.join(HERE, "..", "dumps", "fusion")


class Fusion:
    def __init__(self, lead_s=0.0, out_csv=None, motion=True, quiet_db=QUIET_DB):
        self.comb = cb.Combiner(FS)
        self.gate = mo.MotionGate()
        self.kf = kf.AngleKF()
        self.lead = lead_s
        self.motion = motion
        self.quiet_db = quiet_db
        self.pres = []                                # 최근 방향 창 (s0, s1, present) — 조용한 창 판단용
        self.last_doa_s1 = None
        self.now = 0
        self.last_gate = dict(penalize=False, omega=float("nan"), elev_med=float("nan"))
        self.last_b0 = None
        self.last_kf = None
        self.n = dict(outputs=0, none=0, drone=0, unknown=0, gaps=0, link_lost=0, b0=0, b0_pos=0, b0_penalized=0, b0_quiet=0, doa=0)
        self.reasons = {}
        self.age_max = dict(cls=0.0, doa=0.0)
        self.csv = None
        if out_csv:
            self.csv = csv.writer(open(out_csv, "w", newline="", encoding="utf-8"))
            self.csv.writerow(["t_rx", "now", "state", "angle", "elev", "lead_angle", "reason", "b0_score", "b0_pen", "omega", "elev_med", "kf_status"])
        self.link_down = False
        self.stat = dict(packets=0, period_min=None, period_max=None, cpu_max=0, pcm_q_max=0, res_q_max=0, stack_free_min=None,
                         drop=0, ovr=0, qdrop=0)

    # ---- 입력 ----
    def on_pcm(self, frame_seq, flags):
        s = (frame_seq - 1) * N
        if flags & F_RESYNC:
            self.comb.on_gap(s + N)                   # 재시작 프레임은 MCU도 버린다 → 다음 프레임부터 새 창
            self.gate.reset()
            self.kf = kf.AngleKF()
            self.pres = []
            self.n["gaps"] += 1
        self.now = max(self.now, s + N)

    def on_doa(self, d, t_rx):
        ok = bool(d["flags"] & 1) and bool(d["flags"] & 2)
        s1 = d["s0"] + DOA_OBS
        t = s1 / FS
        el = d.get("elev")
        self.last_gate = self.gate.update(t, d["angle"] if ok else None, el if ok else None)
        self.last_kf = self.kf.step(t, d["angle"] if ok else None)
        self.comb.on_doa(dict(s0=d["s0"], s1=s1, angle=d["angle"], elev=el, valid=bool(d["flags"] & 1), present=bool(d["flags"] & 2),
                              snr=d.get("snr_db", 0.0)))
        self.pres.append((d["s0"], s1, bool(d["flags"] & 2)))
        self.pres = [q for q in self.pres if q[1] > s1 - 4 * FS]
        self.last_doa_s1 = s1
        self.now = max(self.now, s1)
        self.n["doa"] += 1
        return self.emit(t_rx)

    def on_b0(self, b, t_rx):
        score = mo.penalized_score(b["score"], self.last_gate) if self.motion else b["score"]
        if self.quiet_db is not None:
            quiet = b["rms_db"] < self.quiet_db
        else:
            ov = [q[2] for q in self.pres if q[0] >= b["s0"] and q[1] <= b["s0"] + b["n"]]
            quiet = not ov or sum(ov) < 0.5 * len(ov)
        pos = (not quiet) and score >= B0_THR
        self.n["b0"] += 1
        self.n["b0_pos"] += pos
        self.n["b0_penalized"] += self.motion and bool(self.last_gate["penalize"]) and not self.last_gate.get("drop") and b["score"] >= B0_THR
        self.n["b0_dropped_low"] = self.n.get("b0_dropped_low", 0) + (self.motion and bool(self.last_gate.get("drop")) and b["score"] >= B0_THR)
        self.n["b0_quiet"] += quiet
        self.last_b0 = dict(score=b["score"], pen=score, pos=pos)
        self.comb.on_cls(dict(s0=b["s0"], s1=b["s0"] + b["n"], score=score, positive=pos))

    def on_stat(self, s):
        """보드 상태 패킷 (약 1 s마다): Step10 운용 기록의 최댓값·최솟값을 모은다"""
        a = self.stat
        a["packets"] += 1
        if s["period_max"]:
            a["period_min"] = s["period_min"] if a["period_min"] is None else min(a["period_min"], s["period_min"])
            a["period_max"] = s["period_max"] if a["period_max"] is None else max(a["period_max"], s["period_max"])
        for k in ("cpu_max", "pcm_q_max", "res_q_max"):
            a[k] = max(a[k], s[k])
        a["stack_free_min"] = s["stack_free"] if a["stack_free_min"] is None else min(a["stack_free_min"], s["stack_free"])
        a["drop"], a["ovr"], a["qdrop"] = s["drop"], s["ovr"], s["qdrop"]

    # ---- 출력 ----
    def emit(self, t_rx, link_age=0.0):
        state, ang = self.comb.output(self.now, link_age)
        lead = None
        k = self.last_kf
        if state == "drone" and k is not None and k.get("status") in ("update", "coast", "reject", "start"):
            lead = (ang + k.get("omega", 0.0) * self.lead + 180.0) % 360.0 - 180.0
        if self.comb.cls:
            self.age_max["cls"] = max(self.age_max["cls"], (self.now - self.comb.cls[-1][0]) / FS)
        if self.last_doa_s1 is not None:                                    # 가장 최근 방향 창(유효 여부 무관)의 경과 = 방향 경로 지연
            self.age_max["doa"] = max(self.age_max["doa"], (self.now - self.last_doa_s1) / FS)
        self.n["outputs"] += 1
        self.n[state] += 1
        self.reasons[self.comb.reason] = self.reasons.get(self.comb.reason, 0) + 1
        if self.csv:
            b = self.last_b0 or {}
            elv = self.comb.elev if state == "drone" else None
            self.csv.writerow([f"{t_rx:.3f}", self.now, state, "" if ang is None else f"{ang:.2f}", "" if elv is None else f"{elv:.1f}",
                               "" if lead is None else f"{lead:.2f}",
                               self.comb.reason, f"{b.get('score', float('nan')):.2f}", f"{b.get('pen', float('nan')):.2f}",
                               f"{self.last_gate['omega']:.2f}", f"{self.last_gate['elev_med']:.1f}", (k or {}).get("status", "")])
        return state, ang, lead

    def tick(self, t_rx, last_rx):
        """패킷이 없을 때도 주기적으로: 통신 단절이면 "unknown (link)"를 낸다"""
        age = t_rx - last_rx
        if age > cb.LINK_TIMEOUT:
            if not self.link_down:
                self.n["link_lost"] += 1
                self.link_down = True
            return self.emit(t_rx, link_age=age)
        self.link_down = False
        return None

    def summary(self):
        return dict(counts=self.n, reasons=self.reasons, age_max_s={k: round(v, 3) for k, v in self.age_max.items()}, board=self.stat,
                    params=dict(b0_thr=B0_THR, quiet_db=self.quiet_db, motion=self.motion, lead_s=self.lead, confirm=f"{cb.CONFIRM_K}/{cb.CONFIRM_N}",
                                cls_max_age=cb.CLS_MAX_AGE, doa_max_age=cb.DOA_MAX_AGE, link_timeout=cb.LINK_TIMEOUT,
                                motion_rule=dict(win_s=mo.WIN_S, omega_max=mo.OMEGA_MAX, elev_edge=mo.ELEV_EDGE, hold_s=mo.HOLD_S, penalty=mo.PENALTY)))


def fmt(state, ang, lead, fu):
    b = fu.last_b0 or {}
    el = fu.comb.elev if state == "drone" else None
    s = f"{state:7s}" + (f" 방위 {ang:+6.1f}°" if ang is not None else "        ") + (f" 고도 {el:4.1f}°" if el is not None else "") + (f" (앞당김 {lead:+6.1f}°)" if lead is not None else "")
    return s + f"  [{fu.comb.reason}]  B0 {b.get('score', float('nan')):5.1f}→{b.get('pen', float('nan')):5.1f}  ω {fu.last_gate['omega']:+5.1f}°/s"


def feed_packets(fu, parser, data, t_rx):
    out = None
    for p in parser.feed(data):
        if p["type"] == TYPE_PCM:
            fu.on_pcm(p["frame_seq"], p["flags"])
        elif p["type"] == TYPE_DOA:
            out = fu.on_doa(p["doa"], t_rx)
        elif p["type"] == TYPE_B0:
            fu.on_b0(p["b0"], t_rx)
        elif p["type"] == TYPE_STAT:
            fu.on_stat(p["stat"])
    return out


def sim_events(folder, cls_lat=0.3, doa_lat=0.05):
    """옛 녹음: doa_mcu.csv의 방향 + PC가 PCM으로 계산한 B0 → 도착 샘플 순서의 사건 목록"""
    import doa_stream as ds
    import harmonic.b0_stream as bs
    ev = []
    for r in csv.DictReader(open(os.path.join(folder, "doa_mcu.csv"), encoding="utf-8")):
        d = dict(s0=int(r["s0"]), angle=float(r["angle"]), flags=int(r["flags"]), snr_db=float(r["snr_db"]))
        if "elev" in r:
            d["elev"] = float(r["elev"])
        ev.append((d["s0"] + DOA_OBS + doa_lat * FS, "doa", d))
    for x, s0 in ds.load_segments(folder):
        for w in bs.stream_scores(x[0], base=s0):
            ev.append((w["s0"] + w["n"] + cls_lat * FS, "b0", dict(s0=w["s0"], n=w["n"], score=w["score"], f0=w["f0"], rms_db=w["rms_db"])))
        ev.append((s0, "gap", s0))
    ev.sort(key=lambda e: e[0])
    return ev


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--port"); ap.add_argument("--baud", type=int, default=1500000)
    ap.add_argument("--replay", help="stream_capture가 저장한 raw.bin")
    ap.add_argument("--sim", help="B0 패킷이 없는 옛 녹음 폴더 (doa_mcu.csv + wav)")
    ap.add_argument("--label"); ap.add_argument("--minutes", type=float, default=0.0)
    ap.add_argument("--lead", type=float, default=0.0, help="카메라·서보 구동 지연 [s]: 이만큼 앞당긴 방위도 낸다 (KF θ + ω·lead)")
    ap.add_argument("--quiet", action="store_true", help="출력마다 줄을 찍지 않는다 (요약만)")
    ap.add_argument("--no-motion", action="store_true", help="움직임·고도 감점을 끈다 (고정 스피커로 시험할 때 — 감점 대상과 같은 조건이라)")
    ap.add_argument("--quiet-db", type=float, default=None, help="조용한 창을 절대 기준 [dBFS]으로 (기본: 방향 창 present)")
    ap.add_argument("--truth", type=float, default=None, help="정답 방위 [deg]: drone 출력의 방위 오차를 요약에 넣는다")
    a = ap.parse_args()
    src = a.port or a.replay or a.sim
    if not src:
        ap.error("--port, --replay, --sim 중 하나")
    label = a.label or (os.path.basename(os.path.dirname(a.replay)) + "_replay" if a.replay else
                        os.path.basename(os.path.normpath(a.sim)) + "_sim" if a.sim else time.strftime("%Y%m%d_%H%M%S"))
    out = os.path.join(OUT, label)
    os.makedirs(out, exist_ok=True)
    fu = Fusion(a.lead, os.path.join(out, "fusion.csv"), motion=not a.no_motion, quiet_db=a.quiet_db)
    show = (lambda r: None) if a.quiet else (lambda r: r and print(fmt(*r, fu)))

    if a.sim:
        for t, kind, d in sim_events(a.sim):
            if kind == "gap":
                fu.comb.on_gap(d); fu.gate.reset(); fu.kf = kf.AngleKF(); fu.now = max(fu.now, d)
            elif kind == "b0":
                fu.now = max(fu.now, int(t)); fu.on_b0(d, t / FS)
            else:
                fu.now = max(fu.now, int(t)); show(fu.on_doa(d, t / FS))
    elif a.replay:
        parser = PacketParser()
        data = open(a.replay, "rb").read()
        for i in range(0, len(data), 4096):
            show(feed_packets(fu, parser, data[i:i + 4096], fu.now / FS))
    else:
        import serial, threading, queue
        raw = open(os.path.join(out, "raw.bin"), "wb")
        parser = PacketParser()
        with serial.Serial(a.port, a.baud, timeout=0.05) as ser:
            try:
                ser.set_buffer_size(rx_size=1 << 20)
            except (AttributeError, ValueError, serial.SerialException):
                pass
            ser.reset_input_buffer()
            q, stop = queue.Queue(), threading.Event()

            def reader():
                while not stop.is_set():
                    d = ser.read(ser.in_waiting or 1)
                    if d:
                        q.put((d, time.time()))
            th = threading.Thread(target=reader, daemon=True); th.start()
            t0 = last_rx = time.time()
            print(f"{a.port} @ {a.baud} → {out}  (Ctrl+C로 종료)")
            try:
                while not (a.minutes and time.time() - t0 >= a.minutes * 60):
                    try:
                        data, t_rx = q.get(timeout=0.1)
                        raw.write(data); last_rx = t_rx
                        show(feed_packets(fu, parser, data, t_rx - t0))
                    except queue.Empty:
                        show(fu.tick(time.time() - t0, last_rx - t0))
            except KeyboardInterrupt:
                pass
            stop.set(); th.join(timeout=1.0)
        raw.close()
    s = fu.summary()
    if a.truth is not None:
        ang = [float(r["angle"]) for r in csv.DictReader(open(os.path.join(out, "fusion.csv"), encoding="utf-8")) if r["state"] == "drone"]
        if ang:
            e = np.abs((np.array(ang) - a.truth + 180) % 360 - 180)
            s["truth"] = dict(deg=a.truth, drone_outputs=len(ang), within_10deg=round(float(np.mean(e <= 10)), 3),
                              err_median=round(float(np.median(e)), 2), err_p95=round(float(np.percentile(e, 95)), 2))
    json.dump(s, open(os.path.join(out, "summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(s, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
