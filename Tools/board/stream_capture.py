"""Step5 연속 수음 수신기. 펌웨어 APP_MODE_STREAM 과 짝 (PCM 패킷 v3, 12.5 kHz int16, 채널 수는 패킷 헤더 ch — Step8e부터 4ch).

    python board/stream_capture.py --port COM8 --label quiet_10min --minutes 10
    python board/stream_capture.py --replay Tools/dumps/stream/quiet_10min/raw.bin     # 저장한 바이트로 다시 계산

저장 (Tools/dumps/stream/<label>/)
  seg_000.wav ...   연속 구간마다 WAV 하나 (패킷의 채널 수: 4ch = MIC1 0° · MIC2 120° · MIC3 −120° · MIC4 위, 12.5 kHz, int16). 끊김(GAP)·필터 재시작(RESYNC)에서 새 파일
                    RESYNC 블록의 첫 19샘플(FIR 과도 구간)은 버린다
  packets.csv       패킷마다 수신 시각·번호·플래그·유실 카운터·CPU
  doa_mcu.csv       MCU 방위 추정 결과 (0.25 s마다, doa.c). PC 기준과 비교: python doa/compare_mcu.py dumps/stream/<label>
  raw.bin           받은 바이트 그대로 (나중에 --replay로 재현)
  summary.json      Step5 통과 기준 판정 (유실·OVR·CRC·클리핑 0, 시간 복원)

시간 복원: 블록의 첫 샘플 번호 = (frame_seq − 1) × 256 (12.5 kHz). 각 WAV의 시작 샘플 번호는 summary.json에 있다.
"""
import argparse, csv, json, os, sys, time, wave
import numpy as np
from dump_viewer import PacketParser, TYPE_PCM, TYPE_DOA

FS = 12500
N = 256
TRANSIENT = 19                      # preproc.h PREPROC_TRANSIENT_OUT
F_CLIP, F_RESYNC, F_VERIFY, F_GAP = 0x01, 0x02, 0x04, 0x08


class Recorder:
    def __init__(self, out):
        self.out = out
        self.wav = None
        self.segs = []
        self.last_fseq = None
        self.last = None
        self.n = dict(packets=0, frame_gaps=0, frames_missing=0, gap_flags=0, resync=0, clip_packets=0, verify_packets=0)
        self.cpu_max = 0
        self.first_ctr = None
        self.lv = None; self.lv_n = 0; self.nch = None
        self.csv = csv.writer(open(os.path.join(out, "packets.csv"), "w", newline=""))
        self.csv.writerow(["t_rx", "seq", "frame_seq", "flags", "drop", "ovr", "qdrop", "cpu"])
        self.doa_csv = None
        self.doa_n = dict(results=0, valid=0, bg=0); self.doa_last = None; self.proc_max = 0

    def add_doa(self, p, t_rx):
        d = p["doa"]
        four = "elev" in d                                # 4채널 결과 (DOA 패킷 ver 4)
        if self.doa_csv is None:
            self.doa_csv = csv.writer(open(os.path.join(self.out, "doa_mcu.csv"), "w", newline=""))
            P = ["12", "13", "23", "14", "24", "34"] if four else ["12", "13", "23"]
            self.doa_csv.writerow(["t_rx", "frame_seq", "s0", *[f"tau{k}" for k in P], *[f"peak{k}" for k in P], "angle"]
                                  + (["elev", "norm", "resid"] if four else ["norm"]) + ["snr_db", "flags", "proc_us", "bg_s0", "bg_n"])
        self.doa_csv.writerow([f"{t_rx:.4f}", p["frame_seq"], d["s0"], *[f"{t:.6f}" for t in d["tau"]], *[f"{v:.6f}" for v in d["peak"]],
                               f"{d['angle']:.4f}"] + ([f"{d['elev']:.4f}", f"{d['norm']:.5f}", f"{d['resid']:.5f}"] if four else [f"{d['norm']:.5f}"])
                              + [f"{d['snr_db']:.3f}", d["flags"], d["proc_us"], d["bg_s0"], d["bg_n"]])
        self.doa_n["results"] += 1
        self.doa_n["valid"] += bool(d["flags"] & 0x01) and bool(d["flags"] & 0x02)
        self.doa_n["bg"] += bool(d["flags"] & 0x04)
        self.proc_max = max(self.proc_max, d["proc_us"])
        self.doa_last = d

    def doa_status(self):
        d = self.doa_last
        if d is None:
            return ""
        state = "배경학습" if d["flags"] & 0x08 and not d["flags"] & 0x04 else ("D1" if d["flags"] & 0x04 else "D0")
        ok = d["flags"] & 0x01 and d["flags"] & 0x02
        el = f" 고도 {d['elev']:+5.1f}°" if "elev" in d else ""
        return f"  방위 {d['angle']:+6.1f}°{el} {'유효' if ok else '----'} {state} snr {d['snr_db']:4.1f}"

    def _new_seg(self, start_sample):
        if self.wav: self.wav.close()
        path = os.path.join(self.out, f"seg_{len(self.segs):03d}.wav")
        self.wav = wave.open(path, "wb"); self.wav.setnchannels(self.nch); self.wav.setsampwidth(2); self.wav.setframerate(FS)
        self.segs.append(dict(file=os.path.basename(path), start_sample=int(start_sample), samples=0))

    def add(self, p, t_rx):
        self.n["packets"] += 1
        f = p["flags"]
        self.csv.writerow([f"{t_rx:.4f}", p["seq"], p["frame_seq"], f, p["drop"], p["ovr"], p["qdrop"], p["cpu"]])
        if f & F_VERIFY:
            self.n["verify_packets"] += 1; return
        ctr = (p["drop"], p["ovr"], p["qdrop"])
        if self.first_ctr is None: self.first_ctr = ctr
        self.last = ctr
        self.cpu_max = max(self.cpu_max, p["cpu"])
        self.n["clip_packets"] += bool(f & F_CLIP)
        self.n["gap_flags"] += bool(f & F_GAP)
        self.n["resync"] += bool(f & F_RESYNC)
        jump = self.last_fseq is not None and p["frame_seq"] != self.last_fseq + 1
        if jump:
            self.n["frame_gaps"] += 1
            self.n["frames_missing"] += max(0, p["frame_seq"] - self.last_fseq - 1)
        self.last_fseq = p["frame_seq"]
        d = p["data"]                                   # [ch, 256] int16
        if self.nch is None:
            self.nch = d.shape[0]; self.lv = np.zeros(self.nch)
        elif d.shape[0] != self.nch:                    # 채널 수가 바뀐 패킷 (펌웨어가 다름) → 새 파일
            self.nch = d.shape[0]; self.lv = np.zeros(self.nch); self.lv_n = 0; jump = True
        start = (p["frame_seq"] - 1) * N
        if self.wav is None or jump or (f & (F_GAP | F_RESYNC)):
            skip = TRANSIENT if f & F_RESYNC else 0
            self._new_seg(start + skip)
            d = d[:, skip:]
        self.wav.writeframes(np.ascontiguousarray(d.T).astype("<i2").tobytes())
        self.segs[-1]["samples"] += d.shape[1]
        self.lv += np.mean(d.astype(np.float64) ** 2, axis=1); self.lv_n += 1

    def levels(self):
        if self.lv is None:
            return np.zeros(0)
        v = 10 * np.log10(self.lv / max(self.lv_n, 1) / 32768 ** 2 * 2 + 1e-12)   # 사인 기준 dBFS
        self.lv[:] = 0; self.lv_n = 0
        return v

    def close(self, parser, seconds):
        if self.wav: self.wav.close()
        dc = [((b - a) & 0xFF) for a, b in zip(self.first_ctr or (0, 0, 0), self.last or (0, 0, 0))]
        st = parser.stats
        crit = dict(loss=self.n["frame_gaps"] == 0 and st["seq_gap"] == 0 and dc[0] == 0 and dc[2] == 0,
                    ovr=dc[1] == 0, crc=st["crc_fail"] == 0, clip=self.n["clip_packets"] == 0,
                    time_restore=all(s["samples"] > 0 for s in self.segs))
        summ = dict(seconds=round(seconds, 1), packets=self.n, parser=st, delta_drop_ovr_qdrop=dc, cpu_max_pct=self.cpu_max,
                    doa=dict(self.doa_n, proc_us_max=self.proc_max),
                    segments=self.segs, criteria=crit, passed=all(crit.values()),
                    note="crc_fail에는 PCM 안의 FF FF FF FF를 sync로 잘못 잡았다가 버린 것도 포함될 수 있다. seq_gap이 0이면 실제 손실은 없음")
        json.dump(summ, open(os.path.join(self.out, "summary.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        return summ


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--port"); ap.add_argument("--baud", type=int, default=1500000)   # Step8e 4채널: 2074 B × 48.8 패킷/s ≈ 101 kB/s (921600은 최대 92 kB/s라 부족)
    ap.add_argument("--label"); ap.add_argument("--minutes", type=float, default=0.0)
    ap.add_argument("--replay", help="raw.bin 경로 (포트 대신)")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "dumps", "stream"))
    a = ap.parse_args()

    label = a.label or (os.path.basename(os.path.dirname(a.replay)) + "_replay" if a.replay else time.strftime("%Y%m%d_%H%M%S"))
    out = os.path.join(a.out, label)
    if not a.replay and os.path.exists(os.path.join(out, "raw.bin")):   # 같은 라벨로 녹음을 덮어쓰지 않는다 (T_mini3 손실 재발 방지)
        print(f"이미 있는 라벨: {label} — 다른 --label을 쓰거나 폴더를 먼저 옮긴다"); sys.exit(1)
    os.makedirs(out, exist_ok=True)
    parser, rec = PacketParser(), Recorder(out)
    t0 = time.time(); t_show = t0; nbytes = 0

    def handle(data, t_rx):
        for p in parser.feed(data):
            if p["type"] == TYPE_PCM:
                rec.add(p, t_rx)
            elif p["type"] == TYPE_DOA:
                rec.add_doa(p, t_rx)

    if a.replay:
        data = open(a.replay, "rb").read()
        for i in range(0, len(data), 4096):
            handle(data[i:i + 4096], 0.0)
        seconds = rec.n["packets"] * N / FS
    else:
        import serial, threading, queue
        raw = open(os.path.join(out, "raw.bin"), "wb")
        with serial.Serial(a.port, a.baud, timeout=0.05) as ser:
            try:
                ser.set_buffer_size(rx_size=1 << 20)         # Windows: OS 수신 버퍼 1 MB (약 13 s분). 기본 4 KB는 50 ms만 멈춰도 넘친다
            except (AttributeError, ValueError, serial.SerialException):
                pass
            ser.reset_input_buffer()
            # 수신은 별도 스레드: 화면 출력·파일 쓰기가 잠깐 멈춰도(콘솔 선택 모드 등) 포트 읽기는 계속된다
            q, stop = queue.Queue(), threading.Event()

            def reader():
                while not stop.is_set():
                    d = ser.read(ser.in_waiting or 1)
                    if d:
                        q.put((d, time.time() - t0))
            th = threading.Thread(target=reader, daemon=True); th.start()
            print(f"{a.port} @ {a.baud} → {out}  (Ctrl+C로 종료)")
            try:
                while not (a.minutes and time.time() - t0 >= a.minutes * 60):
                    try:
                        data, t_rx = q.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    raw.write(data); nbytes += len(data)
                    handle(data, t_rx)
                    if time.time() - t_show >= 2.0:
                        lv = rec.levels(); dt = time.time() - t_show; t_show = time.time()
                        print(f"{time.time() - t0:7.1f}s  {nbytes / dt / 1000:5.1f} KB/s  "
                              + " ".join(f"ch{c + 1} {v:6.1f}" for c, v in enumerate(lv))
                              + f"  cpu≤{rec.cpu_max}%  gaps {rec.n['frame_gaps']}  clip {rec.n['clip_packets']}  {parser.stats}" + rec.doa_status())
                        nbytes = 0
            except KeyboardInterrupt:
                pass
            stop.set(); th.join(timeout=1.0)
            while not q.empty():                             # 멈추기 전에 받아 둔 것까지 처리
                data, t_rx = q.get_nowait(); raw.write(data); handle(data, t_rx)
        raw.close()
        seconds = time.time() - t0
    s = rec.close(parser, seconds)
    print(json.dumps({k: s[k] for k in ("seconds", "packets", "parser", "delta_drop_ovr_qdrop", "cpu_max_pct", "doa", "criteria", "passed")},
                     ensure_ascii=False, indent=1))
    print(f"WAV {len(s['segments'])}개 → {out}")


if __name__ == "__main__":
    main()
