"""MCU 방향 추정 코드(doa.c + CMSIS rfft, 4채널)를 PC용 gcc로 빌드해 녹음 파일로 돌리고, PC 기준(doa4.py)과 비교한다.

    python doa/test_doa_host.py                                   # 기본: dumps/stream/ch4_gain
    python doa/test_doa_host.py --rec dumps/stream/<4채널 녹음> [--gcc PATH]

보드 없이 "MCU 코드 = PC 기준"을 확인하는 회귀 시험 (I3). 보드의 실제 출력 비교는 compare_mcu.py.
펌웨어와 같은 순서로 넣는다: 녹음의 첫 프레임 = 재시작, 이후 10 s 동안 배경 학습(그동안 D0), 그 뒤 D1.
결과 창마다 PC가 같은 구간·같은 배경으로 다시 계산한다.
(3채널 doa.c 시절의 시험은 git 기록에 있다. 4채널 녹음만 받는다)
"""
import argparse, json, os, re, shutil, struct, subprocess, sys, tempfile
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, HERE)
import doa_stream as ds
import doa4
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
    """doa.h의 배치·채널 지연이 config/geometry.json과 같은지 (MCU는 상수로 박아 둠)"""
    h = open(os.path.join(ROOT, "Core", "app", "inc", "doa.h"), encoding="utf-8").read()
    val = lambda name: float(re.search(rf"#define\s+{name}\s+\(?(-?[\d.]+)f?\)?", h).group(1))
    gm = json.load(open(doa4.GEOM, encoding="utf-8"))
    cd = gm.get("channel_delay_us", {})
    bad = [f"ch{k}: doa.h {val(f'DOA_DELAY_US_CH{k}')} vs geometry.json {cd.get(f'ch{k}', 0.0)}" for k in (1, 2, 3, 4)
           if abs(val(f"DOA_DELAY_US_CH{k}") - float(cd.get(f"ch{k}", 0.0))) > 1e-6]
    sp = sum(gm[k] for k in ("d12_mm", "d13_mm", "d23_mm")) / 3000
    if abs(val("DOA_SPACING_M") - sp) > 1e-6:
        bad.append(f"간격: doa.h {val('DOA_SPACING_M')} vs geometry.json {sp}")
    if abs(val("DOA_MIC4_Z_M") - gm.get("mic4_z_mm", 0) / 1000) > 1e-6:
        bad.append(f"MIC4 높이: doa.h {val('DOA_MIC4_Z_M')} vs geometry.json {gm.get('mic4_z_mm')} mm")
    if bool(int(val("DOA_MIC_CW"))) != bool(gm.get("cw", False)):
        bad.append("마이크 번호 방향(cw)이 다름")
    return bad


def frames(folder):
    """가장 긴 연속 구간을 프레임 경계에 맞춰 (frame_seq, pcm[4, 256]) 목록으로"""
    x, s0 = ds.load_folder(folder)
    if x.shape[0] != 4:
        sys.exit(f"{folder}: {x.shape[0]}채널 녹음. 4채널 녹음이 필요하다")
    skip = (-s0) % N
    x, s0 = x[:, skip:], s0 + skip
    nf = x.shape[1] // N
    return [(s0 // N + 1 + k, x[:, k * N:(k + 1) * N]) for k in range(nf)], (x[:, :nf * N], s0)


def parse(out):
    rows = []
    for line in out.strip().splitlines():
        if line.startswith("#restart"):
            continue
        v = line.split(",")
        rows.append(dict(s0=int(v[0]), tau=[float(t) for t in v[1:7]], peak=[float(t) for t in v[7:13]], angle=float(v[13]),
                         elev=float(v[14]), norm=float(v[15]), resid=float(v[16]), snr=float(v[17]), flags=int(v[18]),
                         bg_s0=int(v[19]), bg_n=int(v[20])))
    return rows


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--rec", default=os.path.join(HERE, "..", "dumps", "stream", "ch4_gain"))
    ap.add_argument("--gcc", default=GCC_DEFAULT)
    a = ap.parse_args()

    bad = check_constants()
    if bad:
        print("doa.h 상수가 config/geometry.json과 다르다 → doa.h를 고치고 펌웨어를 다시 빌드:\n  " + "\n  ".join(bad))
        sys.exit(1)
    fr, (xr, sr) = frames(a.rec)
    stream = bytearray()
    for k, (seq, p) in enumerate(fr):
        stream += struct.pack("<IB", seq, k == 0) + p.astype("<i2").tobytes()

    tmp = tempfile.mkdtemp(prefix="doahost_")
    try:
        exe = build(a.gcc, tmp)
        out = subprocess.run([exe], input=bytes(stream), capture_output=True, check=True).stdout.decode()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    rows = parse(out)
    get = lambda lo, hi: xr[:, lo - sr:hi - sr] if sr <= lo and hi <= sr + xr.shape[1] else None
    print(f"호스트 빌드 결과: {os.path.basename(os.path.normpath(a.rec))} 창 {len(rows)}개 "
          f"(배경 학습 중 D0 {sum(not r['flags'] & cm.F_BG for r in rows)}개, D1 {sum(bool(r['flags'] & cm.F_BG) for r in rows)}개)")
    ok = cm.compare4(rows, get)
    print("호스트 시험:", "통과" if ok else "실패")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
