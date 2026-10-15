"""Step5 전처리 PC = MCU 검증 (보드). 펌웨어 APP_MODE_VERIFY 와 짝.

    python board/verify_preproc.py --port COM8 --pairs 20

MCU는 같은 8프레임(164 ms)을 원본(burst, 50 kHz)과 PCM(12.5 kHz) 두 가지로 보낸다 (Core/app/test/verify.c).
PC는 원본에 frontend.py의 기준 전처리(상태 0에서 시작)를 돌려 MCU PCM과 비교한다.
통과: 모든 쌍에서 최대 차이 ≤ 2 LSB.  (보드 없이 코드만 확인하려면 test_preproc_host.py)
"""
import argparse, os, sys
import numpy as np
from dump_viewer import PacketParser, TYPE_RAW, TYPE_PCM
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))   # Tools/ (폴더 간 import)
from preproc.frontend import preproc_reference

FLAG_VERIFY_RAW = 0x20      # dump.h DUMP_FLAG_VERIFY
FLAG_VERIFY_PCM = 0x04      # stream.h STREAM_FLAG_VERIFY
FRAMES, N_OUT = 8, 256


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True); ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--pairs", type=int, default=20)
    a = ap.parse_args()
    import serial
    parser = PacketParser()
    raw, pcm, results = None, {}, []
    with serial.Serial(a.port, a.baud, timeout=0.05) as ser:
        ser.reset_input_buffer()
        print(f"{a.port} @ {a.baud}: 원본·PCM 쌍 {a.pairs}개를 받습니다")
        while len(results) < a.pairs:
            for p in parser.feed(ser.read(ser.in_waiting or 1)):
                if p["type"] == TYPE_RAW and p["flags"] & FLAG_VERIFY_RAW:
                    raw, pcm = p, {}
                elif p["type"] == TYPE_PCM and p["flags"] & FLAG_VERIFY_PCM and raw is not None:
                    pcm[p["frame_seq"]] = p["data"]
                    last = raw["frame_seq"]
                    want = range(last - FRAMES + 1, last + 1)
                    if all(k in pcm for k in want):
                        mcu = np.concatenate([pcm[k] for k in want], axis=1)
                        ref = preproc_reference(raw["data"])
                        d = np.abs(mcu.astype(int) - ref.astype(int))
                        results.append(d.max())
                        lv = 20 * np.log10(np.std(raw["data"].astype(float), axis=1) / 2048 * np.sqrt(2) + 1e-12)
                        print(f"#{len(results):3d} frame {last - FRAMES + 1}~{last}: 최대 차이 {d.max()} LSB "
                              f"(차이 있는 샘플 {np.mean(d > 0) * 100:.2f}%)  입력 레벨 " + " ".join(f"{v:.0f}" for v in lv) + " dBFS")
                        raw, pcm = None, {}
    worst = max(results)
    print(f"\n쌍 {len(results)}개, 최대 차이 {worst} LSB → {'통과' if worst <= 2 else '실패'} (기준 ≤ 2 LSB)   {parser.stats}")


if __name__ == "__main__":
    main()
