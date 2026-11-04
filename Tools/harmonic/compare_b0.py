# Tools/.venv
"""보드가 보낸 B0 결과(b0_mcu.csv)를 같은 녹음 PCM으로 PC가 다시 계산한 값과 비교한다 (I3, Step8b MCU 이식).

    python harmonic/compare_b0.py dumps/stream/<label>

MCU 창마다 [s0, s0 + 12288) 구간을 b0_stream과 같은 방식(프레임마다 평균 빼기)으로 계산한다.
녹음 구간 밖이거나 PCM이 빠진 창은 건너뛴다. 통과: 점수 차이 ≤ 0.02 · 문턱 판정 일치 · RMS 차이 ≤ 0.1 dB.
RMS 허용치가 넓은 이유: 보드는 float32로 합·제곱합을 더한 뒤 빼서(E[x²] − E[x]²) 분산을 구하고, MIC1 DC(약 −1100 LSB)가 커서
자릿수가 많이 사라진다. -Ofast가 덧셈 순서를 바꾸면 보드마다 0.07 dB쯤 달라진다 (2026-11-04 hover_35 · ground_0 · rot_hover 실측 최대 0.068 dB).
RMS는 판정에 쓰지 않는다 (조용한 창은 fusion/live.py가 방향 창 present로 판단).
"""
import argparse, csv, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, os.path.join(HERE, "..", "doa"))
import harmonic.b0_stream as bs
import doa_stream as ds


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("rec")
    a = ap.parse_args()
    rows = list(csv.DictReader(open(os.path.join(a.rec, "b0_mcu.csv"), encoding="utf-8")))
    segs = ds.load_segments(a.rec)
    d_sc, d_rms, bad_pos, n, skipped = [], [], 0, 0, 0
    for r in rows:
        s0, length = int(r["s0"]), int(r["n"])
        seg = next(((x, st) for x, st in segs if st <= s0 and s0 + length <= st + x.shape[1]), None)
        if seg is None:
            skipped += 1
            continue
        x, st = seg
        ref = bs.stream_scores(x[0, s0 - st:s0 - st + length], base=s0)[0]
        d_sc.append(abs(float(r["score"]) - ref["score"]))
        d_rms.append(abs(float(r["rms_db"]) - ref["rms_db"]))
        bad_pos += (int(r["flags"]) & 1 == 1) != ref["pos"]
        n += 1
    if not n:
        print(f"비교한 창 없음 (B0 결과 {len(rows)}개, 녹음 밖 {skipped}개)"); sys.exit(1)
    d_sc, d_rms = np.array(d_sc), np.array(d_rms)
    proc = max(int(r["proc_us"]) for r in rows)
    print(f"B0 창 {len(rows)}개 중 비교 {n}개 (녹음 밖 {skipped}개) · 점수 차이 최대 {d_sc.max():.5f} · RMS 차이 최대 {d_rms.max():.4f} dB"
          f" · 문턱 판정 불일치 {bad_pos} · 드론 후보 {sum(int(r['flags']) & 1 for r in rows)}개 · 프레임 계산 최대 {proc} us")
    ok = d_sc.max() <= 0.02 and d_rms.max() <= 0.1 and bad_pos == 0
    print("보드 = PC:", "일치" if ok else "불일치")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
