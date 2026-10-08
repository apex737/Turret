"""
STM32 프레임 덤프 수신기 + 시간파형 / FFT 뷰어

사용법
  pip install pyserial numpy matplotlib
  python dump_viewer.py --port COM5                 # 실시간 수신 (Windows)
  python dump_viewer.py --port /dev/ttyACM0         # 실시간 수신 (Linux)
  python dump_viewer.py --replay dumps/f_000003.npz # 저장한 프레임 다시 보기

수신한 프레임은 dumps/ 폴더에 npz로 저장된다 (GCC-PHAT 프로토타입의 입력 데이터).
패킷 형식은 dump.h 주석 참고.
"""
import argparse
import binascii
import os
import struct
import time

import numpy as np

SYNC = b"\xff\xff\xff\xff"
HDR_FMT = "<4sBBBBIIHH"           # sync ver type ch flags seq frame_seq n len
HDR_LEN = struct.calcsize(HDR_FMT)  # 20
VER = 2
TYPE_RAW = 0x01
MAX_PAYLOAD = 64 * 1024

FLAG_CLIP = 0x01
FLAG_MANUAL = 0x02
FLAG_PRETRIG = 0x04


class PacketParser:
    """바이트 스트림을 받아 완성된 패킷을 꺼낸다.

    UART는 패킷 경계가 없는 바이트 스트림이므로
    1) sync 위치 탐색 → 2) 헤더 값 검증 → 3) 길이만큼 모일 때까지 대기 → 4) CRC 검증
    순서로 처리한다. 검증 실패 시 1바이트만 버리고 다시 sync를 찾는다.
    """

    def __init__(self):
        self.buf = bytearray()
        self.stats = dict(ok=0, crc_fail=0, bad_hdr=0, seq_gap=0)
        self.last_seq = None

    def feed(self, data: bytes):
        self.buf += data
        out = []
        while True:
            i = self.buf.find(SYNC)
            if i < 0:
                del self.buf[:-3]           # sync가 경계에 걸쳐 있을 수 있으니 3바이트 남김
                break
            if i > 0:
                del self.buf[:i]
            if len(self.buf) < HDR_LEN:
                break

            _, ver, typ, ch, flags, seq, fseq, n, length = struct.unpack_from(HDR_FMT, self.buf, 0)
            if ver != VER or ch == 0 or length != ch * n * 2 or length > MAX_PAYLOAD:
                self.stats["bad_hdr"] += 1
                del self.buf[:1]
                continue

            total = HDR_LEN + length + 2
            if len(self.buf) < total:
                break                       # 나머지가 도착할 때까지 대기

            pkt = bytes(self.buf[:total])
            crc_rx = struct.unpack_from("<H", pkt, HDR_LEN + length)[0]
            crc = binascii.crc_hqx(pkt[4:HDR_LEN + length], 0xFFFF)
            if crc != crc_rx:
                self.stats["crc_fail"] += 1
                del self.buf[:1]
                continue
            del self.buf[:total]

            if self.last_seq is not None and seq != (self.last_seq + 1) & 0xFFFFFFFF:
                self.stats["seq_gap"] += 1
            self.last_seq = seq
            self.stats["ok"] += 1

            data_arr = np.frombuffer(pkt, dtype="<u2", count=ch * n, offset=HDR_LEN)
            out.append(dict(seq=seq, frame_seq=fseq, type=typ, flags=flags,
                            data=data_arr.reshape(ch, n).copy()))
        return out


def frame_stats(x):
    mean = x.mean(axis=1)
    ac = x - mean[:, None]
    rms = np.sqrt((ac ** 2).mean(axis=1))
    p2p = x.max(axis=1) - x.min(axis=1)
    clip = ((x <= 8) | (x >= 4087)).sum(axis=1)
    return mean, rms, p2p, clip


def onset_index(x, mean):
    """3채널 중 가장 먼저 잡음 바닥을 크게 넘는 샘플 위치 (없으면 최대 진폭 위치)"""
    ac = np.abs(x - mean[:, None]).max(axis=0)
    q = max(len(ac) // 8, 16)
    noise = np.median(ac[:q]) + 1e-9
    thr = max(6 * noise, 0.2 * ac.max())
    idx = np.flatnonzero(ac > thr)
    return int(idx[0]) if idx.size else int(np.argmax(ac))


def spectrum_db(x, fs):
    """DC 제거 + Hann 창 → 단측 진폭 스펙트럼 [dBFS] (0 dBFS = 진폭 2048 LSB 사인)"""
    n = x.shape[1]
    w = np.hanning(n)
    ac = x - x.mean(axis=1, keepdims=True)
    X = np.fft.rfft(ac * w, axis=1)
    amp = 2.0 * np.abs(X) / w.sum()
    f = np.fft.rfftfreq(n, 1.0 / fs)
    return f, 20 * np.log10(amp / 2048.0 + 1e-12)


class Viewer:
    def __init__(self, fs, bpf):
        import matplotlib.pyplot as plt
        self.plt = plt
        self.fs, self.bpf = fs, bpf
        plt.ion()
        self.fig, (self.ax_t, self.ax_z, self.ax_f) = plt.subplots(3, 1, figsize=(11, 9))
        self.fig.tight_layout(pad=3)

    def show(self, pkt):
        x = pkt["data"].astype(np.float64)
        ch, n = x.shape
        pretrig = bool(pkt["flags"] & FLAG_PRETRIG)
        t0 = n // 2 if pretrig else 0              # t = 0 : 트리거 프레임 시작
        t_ms = (np.arange(n) - t0) / self.fs * 1e3
        mean, rms, p2p, clip = frame_stats(x)
        f, db = spectrum_db(x, self.fs)
        labels = [f"MIC{i + 1}" for i in range(ch)]

        ax = self.ax_t
        ax.clear()
        for i in range(ch):
            ax.plot(t_ms, x[i], lw=0.8, label=f"{labels[i]}  mean {mean[i]:.0f}  "
                                              f"rms {rms[i]:.0f}  p2p {p2p[i]:.0f}  clip {clip[i]}")
        ax.axhline(0, color="k", lw=0.5, ls=":")
        ax.axhline(4095, color="k", lw=0.5, ls=":")
        if pretrig:
            ax.axvline(0, color="r", lw=0.8, ls="--", label="trigger frame start")
        ax.set_xlim(t_ms[0], t_ms[-1])
        ax.set_ylabel("ADC [LSB]")
        names = [nm for b, nm in ((FLAG_CLIP, "CLIP"), (FLAG_MANUAL, "MANUAL"), (FLAG_PRETRIG, "PRETRIG"))
                 if pkt["flags"] & b]
        ax.set_title(f"seq {pkt['seq']}  frame {pkt.get('frame_seq', -1)}  [{' '.join(names)}]  "
                     f"({n} samples, {n / self.fs * 1e3:.2f} ms)")
        ax.legend(loc="upper right", fontsize=8)

        ax = self.ax_z                     # 소리 시작점 주변 확대: 채널 간 도달 시간차 육안 확인
        ax.clear()
        k = onset_index(x, mean)
        lo, hi = max(0, k - int(0.5e-3 * self.fs)), min(n, k + int(1.5e-3 * self.fs))
        for i in range(ch):
            ax.plot(t_ms[lo:hi], x[i, lo:hi] - mean[i], marker=".", ms=3, lw=0.8, label=labels[i])
        ax.set_ylabel("AC [LSB]")
        ax.set_xlabel("time [ms]  (1 sample = 20 µs at 50 kHz)")
        ax.axvline(t_ms[k], color="r", lw=0.8, ls="--")
        ax.set_title(f"zoom around onset ({t_ms[k]:+.2f} ms)")
        ax.grid(alpha=0.3)
        ax.legend(loc="upper right", fontsize=8)

        ax = self.ax_f
        ax.clear()
        for i in range(ch):
            ax.plot(f, db[i], lw=0.8, label=labels[i])
        ax.axvspan(*self.bpf, color="tab:green", alpha=0.12, label=f"BPF {self.bpf[0]}-{self.bpf[1]} Hz")
        ax.set_xscale("log")
        ax.set_xlim(f[1], self.fs / 2)
        ax.set_ylim(-110, 0)
        ax.set_xlabel(f"frequency [Hz]  (bin Δf = {self.fs / n:.2f} Hz)")
        ax.set_ylabel("dBFS")
        ax.grid(alpha=0.3, which="both")
        ax.legend(loc="upper right", fontsize=8)

        self.fig.canvas.draw_idle()
        self.plt.pause(0.01)


def run_serial(args):
    import serial

    os.makedirs(args.out, exist_ok=True)
    viewer = Viewer(args.fs, args.bpf)
    parser = PacketParser()
    with serial.Serial(args.port, args.baud, timeout=0.05) as ser:
        ser.reset_input_buffer()
        print(f"listening on {args.port} @ {args.baud} baud ... (Ctrl+C to quit)")
        t_last = time.time()
        try:
            while True:
                data = ser.read(ser.in_waiting or 1)
                for pkt in parser.feed(data):
                    path = os.path.join(args.out, f"f_{pkt['seq']:06d}.npz")
                    np.savez(path, data=pkt["data"], seq=pkt["seq"], frame_seq=pkt["frame_seq"],
                             flags=pkt["flags"], fs=args.fs)
                    dt = time.time() - t_last
                    t_last = time.time()
                    print(f"seq {pkt['seq']:6d}  saved {path}  ({dt:.2f} s since last)  {parser.stats}")
                    viewer.show(pkt)
                viewer.plt.pause(0.001)
        except KeyboardInterrupt:
            print("stopped.", parser.stats)


def run_replay(args):
    z = np.load(args.replay)
    fs = float(z["fs"]) if "fs" in z else args.fs
    viewer = Viewer(fs, args.bpf)
    viewer.show(dict(seq=int(z["seq"]), frame_seq=int(z["frame_seq"]) if "frame_seq" in z else -1,
                     flags=int(z["flags"]), data=z["data"]))
    viewer.plt.ioff()
    viewer.plt.show()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port")
    ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--fs", type=float, default=50_000)
    ap.add_argument("--bpf", type=float, nargs=2, default=(150, 2000))
    ap.add_argument("--out", default="dumps")
    ap.add_argument("--replay")
    args = ap.parse_args()
    if args.replay:
        run_replay(args)
    elif args.port:
        run_serial(args)
    else:
        ap.error("--port 또는 --replay 중 하나가 필요합니다")


if __name__ == "__main__":
    main()
