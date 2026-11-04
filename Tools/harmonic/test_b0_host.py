# Tools/.venv
"""MCU 고조파 점수 코드(harm.c + CMSIS cfft)를 PC용 gcc로 빌드해 녹음으로 돌리고, PC 기준(b0_stream.py)과 비교한다 (I3).

    python harmonic/test_b0_host.py                                  # 기본: speaker_10min · quiet_10min 앞 120 s
    python harmonic/test_b0_host.py --rec dumps/stream/<녹음> [--seconds 0] [--gcc PATH]

펌웨어와 같은 순서로 넣는다: 녹음의 첫 프레임 = 재시작(버림), 이후 프레임마다 harm_push.
DOA 창이 끝나는 프레임(12프레임마다)을 흉내 내 defer를 켜서 미루는 길도 같이 시험한다.
통과: 창 수가 같고, 점수 차이 ≤ 0.02 (점수 단위 = 고조파 4개 SNR 합, 문턱 13.1) · 문턱 판정 일치 · 기본음 일치(동점 근처 제외) · RMS 차이 ≤ 0.01 dB.
같이 출력: PC 기준과 원래 score.py(1 s 창 평균을 빼는 방식)의 점수 차이 — 프레임마다 평균을 빼는 MCU 방식이 바꾸는 정도.
"""
import argparse, os, re, shutil, struct, subprocess, sys, tempfile
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, os.path.join(HERE, "..", "doa"))
import harmonic.score as hs
import harmonic.b0_stream as bs
import doa_stream as ds

GCC_DEFAULT = r"C:\Program Files\GNU Octave\Octave-11.3.0\mingw64\bin\gcc.exe"
N = 256
CMSIS = [("TransformFunctions", f) for f in ("arm_cfft_f32.c", "arm_cfft_radix8_f32.c", "arm_bitreversal2.c")] + \
        [("CommonTables", f) for f in ("arm_common_tables.c", "arm_const_structs.c")]


def build(gcc, tmp):
    for f in ("main.c", "def.h"):
        shutil.copy(os.path.join(HERE, "hosttest", f), tmp)
    for f in ("Core/app/inc/harm.h", "Core/app/inc/harm_hann.h", "Core/app/inc/doa.h", "Core/app/src/harm.c"):
        shutil.copy(os.path.join(ROOT, f), tmp)
    dsp = os.path.join(ROOT, "Drivers", "CMSIS", "DSP")
    exe = os.path.join(tmp, "harm.exe")
    cmd = [gcc, "-O2", "-std=gnu11", "-D__GNUC_PYTHON__", "-I" + tmp, "-I" + os.path.join(dsp, "Include"),
           "-I" + os.path.join(dsp, "PrivateInclude"), "-I" + os.path.join(ROOT, "Drivers", "CMSIS", "Include"),
           os.path.join(tmp, "main.c"), os.path.join(tmp, "harm.c"),
           *[os.path.join(dsp, "Source", d, f) for d, f in CMSIS], "-lm", "-o", exe]
    subprocess.run(cmd, check=True, cwd=tmp, env=dict(os.environ, PATH=os.path.dirname(gcc) + os.pathsep + os.environ["PATH"]))
    return exe


def check_constants():
    """harm.h 상수가 score.py · b0_stream.py와 같은지"""
    h = open(os.path.join(ROOT, "Core", "app", "inc", "harm.h"), encoding="utf-8").read()
    val = lambda name: float(re.search(rf"#define\s+{name}\s+\(?(-?[\d.]+)[uf]?\)?", h).group(1))
    pairs = [("HARM_NFFT", hs.NFFT), ("HARM_HOP", hs.HOP), ("HARM_H", hs.H), ("HARM_CAP", hs.CAP), ("HARM_FLOOR_BINS", hs.FLOOR_BINS),
             ("HARM_FS", hs.FS), ("HARM_NFR", 1 + (hs.FS - hs.NFFT) // hs.HOP), ("HARM_NFR", bs.NFR), ("HARM_WIN_HOP", bs.WIN_HOP),
             ("HARM_F0_MIN", bs.F0_MIN), ("HARM_F0_MAX", bs.F0_MAX), ("HARM_THR", bs.THR)]
    return [f"{n}: harm.h {val(n)} vs PC {v}" for n, v in pairs if abs(val(n) - v) > 1e-6]


def run(exe, x1, seq0):
    """x1: MIC1 샘플 (프레임 경계부터), seq0: 첫 프레임 번호 → MCU 결과 행"""
    nf = len(x1) // N
    stream = bytearray()
    for k in range(nf):
        defer = (k % 12) == 5                                   # DOA 창이 끝나는 프레임 흉내 (12프레임마다)
        stream += struct.pack("<IBB", seq0 + k, k == 0, defer) + x1[k * N:(k + 1) * N].astype("<i2").tobytes()
    out = subprocess.run([exe], input=bytes(stream), capture_output=True, check=True).stdout.decode()
    rows = []
    for line in out.strip().splitlines():
        v = line.split(",")
        rows.append(dict(s0=int(v[0]), n=int(v[1]), score=float(v[2]), f0=float(v[3]), rms_db=float(v[4]),
                         frames=int(v[5]), flags=int(v[6])))
    return rows


def compare(rec, exe, seconds):
    x, s0 = ds.load_folder(rec)
    x1 = x[0]
    skip = (-s0) % N
    x1, s0 = x1[skip:], s0 + skip
    if seconds:
        x1 = x1[:int(seconds * hs.FS)]
    x1 = x1[:len(x1) // N * N]
    seq0 = s0 // N + 1
    mcu = run(exe, x1, seq0)
    ref = bs.stream_scores(x1[N:], base=s0 + N)                 # 첫 프레임은 재시작 프레임이라 버림
    name = os.path.basename(os.path.normpath(rec))
    ok = len(mcu) == len(ref)
    print(f"{name}: 창 MCU {len(mcu)}개 · PC {len(ref)}개")
    n = min(len(mcu), len(ref))
    if n == 0:
        return False
    d_sc = np.array([abs(m["score"] - r["score"]) for m, r in zip(mcu, ref)])
    d_rms = np.array([abs(m["rms_db"] - r["rms_db"]) for m, r in zip(mcu, ref)])
    s0_ok = all(m["s0"] == r["s0"] for m, r in zip(mcu, ref))
    pos_bad = sum(bool(m["flags"] & 1) != r["pos"] for m, r in zip(mcu, ref))
    f0_bad = [(m, r) for m, r in zip(mcu, ref) if m["f0"] != r["f0"]]
    # 기본음이 갈린 창: PC 곡선에서 두 후보의 점수 차이가 작으면(동점 근처) 허용
    c, k, okm = hs.candidates(bs.F0_MIN, bs.F0_MAX)
    f0_real = 0
    for m, r in f0_bad:
        f0_real += abs(m["score"] - r["score"]) > 0.02
    print(f"  s0 일치 {s0_ok} · 점수 차이 최대 {d_sc.max():.5f} (중앙 {np.median(d_sc):.6f}) · RMS 차이 최대 {d_rms.max():.5f} dB"
          f" · 문턱 판정 불일치 {pos_bad} · 기본음 갈림 {len(f0_bad)} (점수까지 다른 것 {f0_real})")
    # 원래 score.py(1 s 창 평균 빼기)와의 차이: 같은 12500샘플 창으로 다시 계산
    xr = x1[N:]
    orig = []
    for r in ref[: min(len(ref), 200)]:
        a = r["s0"] - (s0 + N)
        w = xr[a:a + hs.FS]
        if len(w) == hs.FS:
            orig.append(abs(hs.score(w, [hs.candidates(bs.F0_MIN, bs.F0_MAX)])[0][0] - r["score"]))
    if orig:
        print(f"  참고: 프레임마다 평균 빼기 vs score.py(1 s 창 평균) 점수 차이 최대 {max(orig):.4f} · 중앙 {np.median(orig):.5f} (앞 {len(orig)}창)")
    pos = sum(bool(m["flags"] & 1) for m in mcu)
    print(f"  MCU 드론 후보 창 {pos}/{len(mcu)} · 점수 중앙 {np.median([m['score'] for m in mcu]):.2f}")
    return ok and s0_ok and d_sc.max() <= 0.02 and pos_bad == 0 and f0_real == 0 and d_rms.max() <= 0.01


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--rec", nargs="*", default=[os.path.join(HERE, "..", "dumps", "stream", r) for r in ("speaker_10min", "quiet_10min")])
    ap.add_argument("--seconds", type=float, default=120.0, help="녹음 앞 몇 초 (0 = 전부)")
    ap.add_argument("--gcc", default=GCC_DEFAULT)
    a = ap.parse_args()
    bad = check_constants()
    if bad:
        print("harm.h 상수가 PC 기준과 다르다:\n  " + "\n  ".join(bad)); sys.exit(1)
    tmp = tempfile.mkdtemp(prefix="b0host_")
    try:
        exe = build(a.gcc, tmp)
        ok = all([compare(r, exe, a.seconds) for r in a.rec])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("호스트 시험:", "통과" if ok else "실패")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
