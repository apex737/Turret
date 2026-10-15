"""MCU 전처리 코드(preproc.c + CMSIS FIR 데시메이션)를 PC용 gcc로 빌드해 돌리고, Python 기준(frontend.py)과 비교한다.

    python preproc/test_preproc_host.py [--gcc PATH]

보드 없이 "MCU 코드 = PC 기준"을 확인하는 회귀 시험. 통과: 모든 입력에서 최대 차이 ≤ 2 LSB.
(보드의 실제 출력 비교는 verify_preproc.py. 이 시험은 코드·규약 자체를 확인한다)
"""
import argparse, os, shutil, subprocess, sys, tempfile
import numpy as np
from frontend import preproc_reference

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
GCC_DEFAULT = r"C:\Program Files\GNU Octave\Octave-11.3.0\mingw64\bin\gcc.exe"
NF = 32


def build(gcc, tmp):
    # preproc.h가 같은 폴더의 def.h를 먼저 찾으므로 호스트용 def.h와 함께 임시 폴더에 모은다
    for f in ("hosttest/main.c", "hosttest/def.h"):
        shutil.copy(os.path.join(HERE, f), tmp)
    for f in ("Core/app/inc/preproc.h", "Core/app/inc/fir_coeffs.h", "Core/app/src/preproc.c"):
        shutil.copy(os.path.join(ROOT, f), tmp)
    dsp = os.path.join(ROOT, "Drivers", "CMSIS", "DSP")
    src = [os.path.join(dsp, "Source", "FilteringFunctions", f) for f in ("arm_fir_decimate_f32.c", "arm_fir_decimate_init_f32.c")]
    exe = os.path.join(tmp, "pre.exe")
    cmd = [gcc, "-O2", "-std=gnu11", "-D__GNUC_PYTHON__", "-I" + tmp, "-I" + os.path.join(dsp, "Include"),
           "-I" + os.path.join(dsp, "PrivateInclude"), os.path.join(tmp, "main.c"), os.path.join(tmp, "preproc.c"), *src, "-o", exe]
    subprocess.run(cmd, check=True, cwd=tmp, env=dict(os.environ, PATH=os.path.dirname(gcc) + os.pathsep + os.environ["PATH"]))
    return exe


def cases():
    rng = np.random.default_rng(0)
    yield "random", rng.integers(0, 4096, (NF, 3, 1024))
    t = np.arange(NF * 1024) / 50000
    tone = 2048 + 1500 * np.sin(2 * np.pi * 550 * t) + 300 * np.sin(2 * np.pi * 11000 * t)   # 11 kHz는 저지 대역
    yield "tone", np.stack([np.round(tone).reshape(NF, 1024)] * 3, axis=1)
    yield "extreme", np.where(rng.random((NF, 3, 1024)) < 0.5, 0, 4095)
    imp = np.full((NF, 3, 1024), 2048); imp[0, :, 0] += 1000
    yield "impulse", imp


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(); ap.add_argument("--gcc", default=GCC_DEFAULT); a = ap.parse_args()
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        exe = build(a.gcc, tmp)
        for name, v in cases():
            v = v.astype(np.uint16)
            out = subprocess.run([exe, str(NF)], input=v.tobytes(), capture_output=True, check=True).stdout
            mcu = np.concatenate(list(np.frombuffer(out, dtype="<i2").reshape(NF, 3, 256)), axis=1)
            ref = preproc_reference(np.concatenate(list(v), axis=1))
            d = np.abs(mcu.astype(int) - ref.astype(int))
            ok &= d.max() <= 2
            print(f"{name:8s} 최대 차이 {d.max()} LSB, 차이가 있는 샘플 {np.mean(d > 0) * 100:.3f}%")
    print("통과" if ok else "실패")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
