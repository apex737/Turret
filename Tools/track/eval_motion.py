# Tools/.venv
"""Step8c 감점 규칙(track/motion.py)과 추적 KF(track/kf.py)를 기존 녹음으로 잰다 (스피드런 2026-11-04, 녹음 새로 없음).

    python track/eval_motion.py

녹음과 보는 것
  Step7 12방향 (doa_az*, 평면 3마이크, PC 방위 doa.csv) : 고정 음원 → 정지 판정 비율 (기준 ≥ 95%)
  fan_10min (선풍기, 3마이크, PC 방위 doa.csv)        : 감점된 창 비율 (기준 ≥ 80%), B0 드론 후보 중 감점으로 문턱 아래가 된 비율
  phone_rot_try1 (핸드폰 들고 배열 주위를 돎, MCU 방위) : 정지로 잘못 본 비율, KF ω
평면 3마이크 녹음은 고도각이 없어 "낮음"으로 본다 → 높이 있는 정지 음원 보존(≤ 5%)과 고도 기준은 4채널 녹음이 필요하다 (여기서 못 잼).
"""
import csv, glob, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, os.path.join(HERE, "..", "doa"))
import track.motion as mo
import track.kf as kf
import harmonic.b0_stream as bs
import doa_stream as ds

FS = 12500.0
DUMPS = os.path.join(HERE, "..", "dumps", "stream")


def load_doa(folder):
    """방향 결과 → [(t, angle 또는 None, elev 또는 None)] (t = 창 끝 [s])"""
    p = os.path.join(folder, "doa.csv")
    rows = []
    if os.path.exists(p):
        for r in csv.DictReader(open(p, encoding="utf-8")):
            ok = r["valid"] == "1" and r["present"] == "1"
            rows.append((int(r["s1"]) / FS, float(r["angle"]) if ok else None, None))
        return rows
    for r in csv.DictReader(open(os.path.join(folder, "doa_mcu.csv"), encoding="utf-8")):
        f = int(r["flags"]); ok = bool(f & 1) and bool(f & 2)
        el = float(r["elev"]) if "elev" in r else None
        rows.append(((int(r["s0"]) + 6250) / FS, float(r["angle"]) if ok else None, el if ok else None))
    return rows


def run_gate(rows):
    g = mo.MotionGate()
    return [g.update(t, a, e) for t, a, e in rows]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"규칙: 회귀 {mo.WIN_S} s · 정지 |ω| ≤ {mo.OMEGA_MAX}°/s · 최소 점 {mo.MIN_PTS} · 고도 경계 {mo.ELEV_EDGE}° · 지속 {mo.HOLD_S} s · 감점 ×{mo.PENALTY}")
    # 1) Step7 12방향: 정지 판정
    tot_n, tot_st = 0, 0
    for f in sorted(glob.glob(os.path.join(DUMPS, "doa_az*"))):
        out = run_gate(load_doa(f))
        judged = [o for o in out if not np.isnan(o["omega"])]
        st = sum(o["stationary"] for o in judged)
        tot_n += len(judged); tot_st += st
        print(f"  {os.path.basename(f):10s} 판정 창 {len(judged):4d} · 정지 {st / max(len(judged), 1) * 100:5.1f}% · |ω| p95 {np.percentile([abs(o['omega']) for o in judged], 95) if judged else float('nan'):.2f}°/s")
    print(f"12방향 합계: 정지 판정 {tot_st}/{tot_n} = {tot_st / max(tot_n, 1) * 100:.1f}% (기준 ≥ 95%)")

    # 2) 선풍기: 감점 비율 + B0 후보가 감점으로 문턱 아래가 되는 비율
    fan = os.path.join(DUMPS, "fan_10min")
    rows = load_doa(fan)
    rows = [r for r in rows if r[0] <= rows[0][0] + 455]          # Step8b와 같이 455 s까지 (그 뒤는 선풍기 끔)
    out = run_gate(rows)
    pen = np.array([o["penalize"] for o in out])
    print(f"fan_10min: 방향 창 {len(out)} · 감점 {pen.mean() * 100:.1f}% (기준 ≥ 80%) · 유효 방위 {sum(r[1] is not None for r in rows)}")
    x, s0 = ds.load_folder(fan)
    n455 = int(455 * FS)
    b0 = bs.stream_scores(x[0, :n455 - (s0 - s0)], base=s0)
    tg = np.array([o["t"] for o in out])
    pos = before = after = 0
    for w in b0:
        if not w["pos"]:
            continue
        pos += 1
        i = np.searchsorted(tg, (w["s0"] + w["n"]) / FS, side="right") - 1
        o = out[i] if i >= 0 else dict(penalize=False)
        if mo.penalized_score(w["score"], o) < bs.THR:
            after += 1
    print(f"  B0(MCU 방식) 드론 후보 창 {pos}/{len(b0)} → 감점 뒤 문턱 아래 {after} ({after / max(pos, 1) * 100:.1f}%)")

    # 3) 회전 녹음: 정지로 잘못 본 비율, KF 각속도
    rot = os.path.join(DUMPS, "phone_rot_try1")
    rows = load_doa(rot)
    out = run_gate(rows)
    judged = [o for o in out if not np.isnan(o["omega"])]
    tr = kf.track([r[0] for r in rows], [np.nan if r[1] is None else r[1] for r in rows])
    om = [abs(o["omega"]) for o in tr if o["status"] == "update"]
    print(f"phone_rot_try1: 판정 창 {len(judged)} · 정지로 봄 {sum(o['stationary'] for o in judged) / max(len(judged), 1) * 100:.1f}%"
          f" · 회귀 |ω| 중앙 {np.median([abs(o['omega']) for o in judged]) if judged else float('nan'):.1f}°/s · KF |ω| 중앙 {np.median(om) if om else float('nan'):.1f}°/s"
          f" · KF 상태 {dict((s, sum(o['status'] == s for o in tr)) for s in ('update', 'coast', 'reject', 'lost'))}")


if __name__ == "__main__":
    main()
