"""MCU 방위 추정 코드(doa.c + CMSIS rfft)를 PC용 gcc로 빌드해 녹음 파일로 돌리고, PC 기준(doa_stream.py)과 비교한다.

    python doa/test_doa_host.py                                              # 기본: doa_bg → doa_az000
    python doa/test_doa_host.py --bg dumps/stream/doa_bg --rec dumps/stream/doa_az120 [--gcc PATH]

보드 없이 "MCU 코드 = PC 기준"을 확인하는 회귀 시험 (보드의 실제 출력 비교는 compare_mcu.py).
펌웨어와 같은 순서로 넣는다: --bg 녹음을 처음부터 (첫 프레임 = 재시작, 이후 10 s 동안 배경 학습) →
끊김 표시와 함께 --rec 녹음 (배경 유지, 창만 새로 시작). 결과 창마다 PC가 같은 구간·같은 배경으로 다시 계산한다.
"""
import argparse, json, os, re, shutil, struct, subprocess, sys, tempfile
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, HERE)
import doa_stream as ds
import compare_mcu as cm

GCC_DEFAULT = r"C:\Program Files\GNU Octave\Octave-11.3.0\mingw64\bin\gcc.exe"
N = 256
CMSIS = [("TransformFunctions", f) for f in ("arm_rfft_fast_f32.c", "arm_rfft_fast_init_f32.c", "arm_cfft_f32.c",
                                              "arm_cfft_init_f32.c", "arm_cfft_radix8_f32.c", "arm_bitreversal2.c")] + \
        [("CommonTables", f) for f in ("arm_common_tables.c", "arm_const_structs.c")]


def build(gcc, tmp):
    shutil.copy(os.path.join(HERE, "hosttest", "main.c"), tmp)
    shutil.copy(os.path.join(HERE, "hosttest", "def.h"), tmp)             # Core/app/inc/def.h 대신 (STM32 헤더 없이)
    for f in ("Core/app/inc/doa.h", "Core/app/src/doa.c"):
        shutil.copy(os.path.join(ROOT, f), tmp)
    dsp = os.path.join(ROOT, "Drivers", "CMSIS", "DSP")
    exe = os.path.join(tmp, "doa.exe")
    cmd = [gcc, "-O2", "-std=gnu11", "-D__GNUC_PYTHON__", "-I" + tmp, "-I" + os.path.join(dsp, "Include"),
           "-I" + os.path.join(dsp, "PrivateInclude"), "-I" + os.path.join(ROOT, "Drivers", "CMSIS", "Include"),
           os.path.join(tmp, "main.c"), os.path.join(tmp, "doa.c"),
           *[os.path.join(dsp, "Source", d, f) for d, f in CMSIS], "-lm", "-o", exe]
    subprocess.run(cmd, check=True, cwd=tmp, env=dict(os.environ, PATH=os.path.dirname(gcc) + os.pathsep + os.environ["PATH"]))
    return exe


def check_constants():
    """doa.h의 간격·채널 지연이 config/geometry.json과 같은지 (MCU는 상수로 박아 둠)"""
    h = open(os.path.join(ROOT, "Core", "app", "inc", "doa.h"), encoding="utf-8").read()
    val = lambda name: float(re.search(rf"#define\s+{name}\s+\(?(-?[\d.]+)f?\)?", h).group(1))
    gm = json.load(open(os.path.join(ROOT, "config", "geometry.json"), encoding="utf-8"))
    cd = gm.get("channel_delay_us", {})
    bad = [f"ch{k}: doa.h {val(f'DOA_DELAY_US_CH{k}')} vs geometry.json {cd.get(f'ch{k}', 0.0)}" for k in (1, 2, 3)
           if abs(val(f"DOA_DELAY_US_CH{k}") - float(cd.get(f"ch{k}", 0.0))) > 1e-6]
    sp = sum(gm[k] for k in ("d12_mm", "d13_mm", "d23_mm")) / 3000
    if abs(val("DOA_SPACING_M") - sp) > 1e-6:
        bad.append(f"간격: doa.h {val('DOA_SPACING_M')} vs geometry.json {sp}")
    if bool(int(val("DOA_MIC_CW"))) != bool(gm.get("cw", False)):
        bad.append("마이크 번호 방향(cw)이 다름")
    return bad


def frames(folder):
    """가장 긴 연속 구간을 프레임 경계에 맞춰 (frame_seq, pcm[3, 256]) 목록으로"""
    x, s0 = ds.load_folder(folder)
    skip = (-s0) % N                                  # 과도 구간을 버려 프레임 경계가 어긋난 구간
    x, s0 = x[:, skip:], s0 + skip
    nf = x.shape[1] // N
    return [(s0 // N + 1 + k, x[:, k * N:(k + 1) * N]) for k in range(nf)], (x[:, :nf * N], s0)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--bg", default=os.path.join(HERE, "..", "dumps", "stream", "doa_bg"))
    ap.add_argument("--rec", default=os.path.join(HERE, "..", "dumps", "stream", "doa_az000"))
    ap.add_argument("--gcc", default=GCC_DEFAULT)
    a = ap.parse_args()

    bad = check_constants()
    if bad:
        print("doa.h 상수가 config/geometry.json과 다르다 → doa.h를 고치고 펌웨어를 다시 빌드:\n  " + "\n  ".join(bad))
        sys.exit(1)
    fb, (xb, sb) = frames(a.bg)
    fr, (xr, sr) = frames(a.rec)
    stream = bytearray()
    for k, (seq, p) in enumerate(fb):
        stream += struct.pack("<IB", seq, k == 0) + p.astype("<i2").tobytes()
    for k, (seq, p) in enumerate(fr):
        stream += struct.pack("<IB", seq, k == 0) + p.astype("<i2").tobytes()

    tmp = tempfile.mkdtemp(prefix="doahost_")
    try:
        exe = build(a.gcc, tmp)
        out = subprocess.run([exe], input=bytes(stream), capture_output=True, check=True).stdout.decode()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    parts = [[]]
    for line in out.strip().splitlines():
        if line.startswith("#restart"):
            parts.append([])
            continue
        v = line.split(",")
        parts[-1].append(dict(s0=int(v[0]), tau=[float(t) for t in v[1:4]], peak=[float(t) for t in v[4:7]], angle=float(v[7]),
                              norm=float(v[8]), snr=float(v[9]), flags=int(v[10]), bg_s0=int(v[11]), bg_n=int(v[12])))
    rb, rr = parts[1], parts[2]                       # [첫 #restart 앞(비어 있음), --bg, --rec]

    def getter(x, s0):
        return lambda lo, hi: x[:, lo - s0:hi - s0] if s0 <= lo and hi <= s0 + x.shape[1] else None

    def get_rec(lo, hi):                              # 창은 --rec, 배경은 --bg에서
        return getter(xr, sr)(lo, hi) if hi - lo == cm.OBS else getter(xb, sb)(lo, hi)

    print(f"호스트 빌드 결과: --bg 구간 {len(rb)}개, --rec 구간 {len(rr)}개")
    print(f"[--bg {os.path.basename(os.path.normpath(a.bg))}] 배경 학습 중(D0) + 학습 후(D1, 자기 배경)")
    ok1 = cm.compare(rb, getter(xb, sb))
    print(f"[--rec {os.path.basename(os.path.normpath(a.rec))}] --bg로 배운 배경 사용 (D1)")
    ok2 = cm.compare(rr, get_rec)
    print("호스트 시험:", "통과" if ok1 and ok2 else "실패")
    sys.exit(0 if ok1 and ok2 else 1)


if __name__ == "__main__":
    main()
