"""MCU 방향 추정(doa.c) 결과를 같은 PCM으로 계산한 PC 기준과 비교한다. 4채널(doa4.py, Step8e)과 예전 3채널(doa_stream.py) 모두.

    python doa/compare_mcu.py dumps/stream/<label>        # 보드 녹음: stream_capture.py가 저장한 doa_mcu.csv + WAV

MCU가 보낸 관측 창 첫 샘플(s0)과 배경 구간(bg_s0, bg_n)을 그대로 써서 PC가 같은 창을 다시 계산한다.
PC가 그 구간의 PCM을 다 받지 못했으면(큐 유실 등) 그 창은 건너뛴다. 샘플레이트는 MCU와 같은 공칭값 12500 Hz.
통과: 양쪽 모두 유효한 창에서 지연 차이 ≤ 0.02 샘플, 각도 차이 ≤ 0.2° (4채널은 고도각도), 유효·present 판정 일치 ≥ 99%.
(test_doa_host.py도 이 비교를 쓴다. 그쪽은 같은 C 코드를 PC용 gcc로 빌드해 보드 없이 확인한다)
"""
import argparse, csv, json, os, sys
import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import doa_stream as ds
import doa4

FS_MCU = 12500.0                                     # doa.h DOA_FS
OBS = 6250                                           # doa.h DOA_OBS
F_VALID, F_PRESENT, F_BG, F_LEARNING = 0x01, 0x02, 0x04, 0x08
TOL_TAU, TOL_ANG, TOL_FLAG = 0.02, 0.2, 0.99
FIELDS = ["s0", "tau12", "tau13", "tau23", "peak12", "peak13", "peak23", "angle", "norm", "snr_db", "flags", "bg_s0", "bg_n"]


def read_rows(path):
    rows = []
    rd = csv.DictReader(open(path))
    if "elev" in (rd.fieldnames or []):                  # 4채널 (stream_capture.py가 tau12 … tau34, elev, resid로 저장)
        P = ["12", "13", "23", "14", "24", "34"]
        for r in rd:
            rows.append(dict(s0=int(r["s0"]), tau=[float(r[f"tau{k}"]) for k in P], peak=[float(r[f"peak{k}"]) for k in P],
                             angle=float(r["angle"]), elev=float(r["elev"]), norm=float(r["norm"]), resid=float(r["resid"]),
                             snr=float(r["snr_db"]), flags=int(r["flags"]), bg_s0=int(r["bg_s0"]), bg_n=int(r["bg_n"])))
        return rows
    for r in rd:
        rows.append(dict(s0=int(r["s0"]), tau=[float(r[k]) for k in ("tau12", "tau13", "tau23")],
                         peak=[float(r[k]) for k in ("peak12", "peak13", "peak23")], angle=float(r["angle"]), norm=float(r["norm"]),
                         snr=float(r["snr_db"]), flags=int(r["flags"]), bg_s0=int(r["bg_s0"]), bg_n=int(r["bg_n"])))
    return rows


def folder_reader(folder):
    """녹음 폴더의 연속 구간들 → get(a, b): 샘플 번호 [a, b) 의 PCM [3, b−a] (없으면 None)"""
    segs = ds.load_segments(folder)

    def get(a, b):
        for x, s0 in segs:
            if s0 <= a and b <= s0 + x.shape[1]:
                return x[:, a - s0:b - s0]
        return None
    return get


def compare(rows, get, quiet=False):
    p = argparse.ArgumentParser(); ds.add_args(p); A = p.parse_args([])
    pos, d = ds.positions()
    bg_cache, out = {}, []
    for r in rows:
        x = get(r["s0"], r["s0"] + OBS)
        if x is None:
            continue
        bg = None
        if r["flags"] & F_BG:
            key = (r["bg_s0"], r["bg_n"])
            if key not in bg_cache:
                xb = get(key[0], key[0] + key[1])
                bg_cache[key] = None if xb is None else ds.cross_spectra(xb, A.block, 2 * A.block)
            bg = bg_cache[key]
            if bg is None:
                continue
        e = ds.estimate(x, FS_MCU, pos, d, tuple(A.band), A.block, bg=bg)
        pc_valid = ds.is_valid(e, A)
        pc_present = (e["snr"] >= A.min_snr) if bg is not None else True
        out.append(dict(s0=r["s0"], dtau=np.max(np.abs(np.array(e["tau"]) - r["tau"])), dpeak=np.max(np.abs(np.array(e["peak"]) - r["peak"])),
                        dang=float(ds.ang_err(e["angle"], r["angle"])), dsnr=abs(e["snr"] - r["snr"]) if bg is not None else 0.0,
                        both_valid=pc_valid and bool(r["flags"] & F_VALID),
                        flag_ok=(pc_valid == bool(r["flags"] & F_VALID)) and (pc_present == bool(r["flags"] & F_PRESENT)),
                        bg=bg is not None))
    if not out:
        print("비교할 창이 없다 (PC가 받은 PCM과 겹치는 창이 없음)")
        return False
    bv = [o for o in out if o["both_valid"]]
    flag_rate = np.mean([o["flag_ok"] for o in out])
    dtau = max(o["dtau"] for o in bv) if bv else float("nan")
    dang = max(o["dang"] for o in bv) if bv else float("nan")
    ok = flag_rate >= TOL_FLAG and (not bv or (dtau <= TOL_TAU and dang <= TOL_ANG))   # 음원이 없는 녹음은 판정 일치만 본다
    print(f"비교 창 {len(out)}개 (배경 빼기 {sum(o['bg'] for o in out)}개), 양쪽 유효 {len(bv)}개")
    if bv:
        print(f"  양쪽 유효 창: 지연 차이 최대 {dtau:.4f} 샘플, 피크 차이 최대 {max(o['dpeak'] for o in bv):.4f}, "
              f"각도 차이 중앙 {np.median([o['dang'] for o in bv]):.4f}° 최대 {dang:.4f}°, SNR 차이 최대 {max(o['dsnr'] for o in bv):.3f} dB")
    print(f"  유효·present 판정 일치 {flag_rate * 100:.2f}%  → {'통과' if ok else '실패'} "
          f"(기준: 지연 ≤ {TOL_TAU}, 각도 ≤ {TOL_ANG}°, 판정 일치 ≥ {TOL_FLAG * 100:.0f}%)")
    if not quiet:
        bad = sorted(out, key=lambda o: -o["dtau"])[:3]
        print("  지연 차이가 큰 창: " + ", ".join(f"s0 {o['s0']} Δτ {o['dtau']:.4f} 유효(양쪽) {o['both_valid']}" for o in bad))
    return ok


def compare4(rows, get, quiet=False):
    """4채널 결과 rows (doa.c) ↔ doa4.estimate (같은 창·같은 배경·같은 채널 지연)"""
    pos, dly = doa4.config_positions(), doa4.channel_delays_us()
    bg_cache, out = {}, []
    for r in rows:
        x = get(r["s0"], r["s0"] + OBS)
        if x is None:
            continue
        bg = None
        if r["flags"] & F_BG:
            key = (r["bg_s0"], r["bg_n"])
            if key not in bg_cache:
                xb = get(key[0], key[0] + key[1])
                bg_cache[key] = None if xb is None else doa4.background(xb)
            bg = bg_cache[key]
            if bg is None:
                continue
        e = doa4.estimate(x, pos, FS_MCU, bg=bg, delay_us=dly)
        out.append(dict(s0=r["s0"], dtau=np.max(np.abs(np.array(e["tau"]) - r["tau"])), dpeak=np.max(np.abs(np.array(e["peak"]) - r["peak"])),
                        dang=float(ds.ang_err(e["az"], r["angle"])), del_=abs(e["el"] - r["elev"]),
                        dsnr=abs(e["snr"] - r["snr"]) if bg is not None else 0.0,
                        both_valid=e["valid"] and bool(r["flags"] & F_VALID),
                        flag_ok=(e["valid"] == bool(r["flags"] & F_VALID)) and (e["present"] == bool(r["flags"] & F_PRESENT)),
                        bg=bg is not None))
    if not out:
        print("비교할 창이 없다 (PC가 받은 PCM과 겹치는 창이 없음)")
        return False
    bv = [o for o in out if o["both_valid"]]
    flag_rate = np.mean([o["flag_ok"] for o in out])
    dtau = max(o["dtau"] for o in bv) if bv else float("nan")
    dang = max(max(o["dang"], o["del_"]) for o in bv) if bv else float("nan")
    ok = flag_rate >= TOL_FLAG and (not bv or (dtau <= TOL_TAU and dang <= TOL_ANG))
    print(f"비교 창 {len(out)}개 (배경 빼기 {sum(o['bg'] for o in out)}개), 양쪽 유효 {len(bv)}개")
    if bv:
        print(f"  양쪽 유효 창: 지연 차이 최대 {dtau:.4f} 샘플, 피크 차이 최대 {max(o['dpeak'] for o in bv):.4f}, "
              f"방위 차이 최대 {max(o['dang'] for o in bv):.4f}°, 고도각 차이 최대 {max(o['del_'] for o in bv):.4f}°, "
              f"SNR 차이 최대 {max(o['dsnr'] for o in bv):.3f} dB")
    print(f"  유효·present 판정 일치 {flag_rate * 100:.2f}%  → {'통과' if ok else '실패'} "
          f"(기준: 지연 ≤ {TOL_TAU}, 방위·고도각 ≤ {TOL_ANG}°, 판정 일치 ≥ {TOL_FLAG * 100:.0f}%)")
    if not quiet:
        bad = sorted(out, key=lambda o: -o["dtau"])[:3]
        print("  지연 차이가 큰 창: " + ", ".join(f"s0 {o['s0']} Δτ {o['dtau']:.4f} 유효(양쪽) {o['both_valid']}" for o in bad))
    return ok


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", help="Tools/dumps/stream/<label> (doa_mcu.csv가 있는 녹음)")
    a = ap.parse_args()
    rows = read_rows(os.path.join(a.folder, "doa_mcu.csv"))
    print(f"MCU 결과 {len(rows)}개: 유효 {sum(r['flags'] & F_VALID > 0 for r in rows)}, 배경 빼기 {sum(r['flags'] & F_BG > 0 for r in rows)}")
    four = bool(rows) and len(rows[0]["tau"]) == 6
    sys.exit(0 if (compare4 if four else compare)(rows, folder_reader(a.folder)) else 1)


if __name__ == "__main__":
    main()
