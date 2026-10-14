"""burst 캡처 수신기 (Step5). 펌웨어 APP_MODE_BURST 1 과 짝.

    python burst_rx.py --port COM8 --label sweep_1m --count 60
    python burst_rx.py --port COM8 --label fpv_ev1 --seconds 30

- 받은 burst(3ch x 8192샘플, 50 kHz, 164 ms 연속)를 하나씩 npz로 저장: Tools/dumps/step5/<label>/b_<seq>.npz
- 화면에는 burst마다 채널별 RMS·피크(dBFS, 12비트 기준), 클리핑 여부, 패킷 통계를 출력
- 저장 형식: data [3, 8192] uint16, fs, seq, frame_seq, flags, label, t (수신 시각)
"""
import argparse, os, sys, time
import numpy as np
from dump_viewer import PacketParser, TYPE_RAW, FLAG_CLIP

FLAG_BURST = 0x10
FS = 50000


def level_db(x):
    """12비트 ADC 기준 dBFS (풀스케일 사인 = 0 dBFS가 되도록 2048로 나눔)."""
    a = x.astype(np.float64) - x.mean()
    rms = np.sqrt(np.mean(a ** 2)) / 2048 * np.sqrt(2)
    pk = np.abs(a).max() / 2048
    return 20 * np.log10(rms + 1e-12), 20 * np.log10(pk + 1e-12)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--label", required=True, help="녹음 이름 (폴더 이름이 됨)")
    ap.add_argument("--count", type=int, default=0, help="받을 burst 수 (0이면 --seconds 또는 Ctrl+C까지)")
    ap.add_argument("--seconds", type=float, default=0.0)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "dumps", "step5"))
    a = ap.parse_args()

    import serial
    out = os.path.join(a.out, a.label)
    os.makedirs(out, exist_ok=True)
    parser = PacketParser()
    got, last_fseq, t0 = 0, None, time.time()
    with serial.Serial(a.port, a.baud, timeout=0.05) as ser:
        ser.reset_input_buffer()
        print(f"{a.port} @ {a.baud} → {out}  (Ctrl+C로 종료)")
        try:
            while True:
                for pkt in parser.feed(ser.read(ser.in_waiting or 1)):
                    if pkt["type"] != TYPE_RAW or not (pkt["flags"] & FLAG_BURST):
                        continue
                    d = pkt["data"]
                    np.savez(os.path.join(out, f"b_{pkt['seq']:06d}.npz"), data=d, fs=FS, seq=pkt["seq"],
                             frame_seq=pkt["frame_seq"], flags=pkt["flags"], label=a.label, t=time.time())
                    lv = [level_db(d[c]) for c in range(d.shape[0])]
                    gap = "" if last_fseq is None else f"  +{pkt['frame_seq'] - last_fseq} frames"
                    last_fseq = pkt["frame_seq"]
                    got += 1
                    print(f"#{got:4d} seq {pkt['seq']:6d}{gap}  "
                          + "  ".join(f"ch{c + 1} {r:6.1f}/{p:5.1f}" for c, (r, p) in enumerate(lv))
                          + ("  CLIP!" if pkt["flags"] & FLAG_CLIP else "")
                          + f"   {parser.stats}")
                if (a.count and got >= a.count) or (a.seconds and time.time() - t0 >= a.seconds):
                    break
        except KeyboardInterrupt:
            pass
    print(f"끝: burst {got}개, {parser.stats}")


if __name__ == "__main__":
    main()
