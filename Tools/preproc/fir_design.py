"""Step5: 데시메이션 FIR 계수를 설계하고 MCU 헤더·설정 파일로 내보낸다.

    python preproc/fir_design.py

- 50 kHz → 12.5 kHz (↓4). 통과 0~5 kHz, 저지 7.5 kHz 이상 60 dB (12.5 − 5 = 7.5 kHz 위가 0~5 kHz로 접히므로)
- Kaiser 창, 홀수 탭(대칭, 선형 위상 → 군지연 (N−1)/2 샘플 @ 50 kHz)
- 출력: Core/app/inc/fir_coeffs.h (float32, CMSIS 순서), config/frontend_config.json, reports/step5/fir_response.png
"""
import json, os
import numpy as np
from scipy.signal import kaiserord, firwin, freqz
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FS_IN, M = 50000, 4
F_PASS, F_STOP, ATT_DB = 5000.0, 7500.0, 60.0
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def design():
    n, beta = kaiserord(ATT_DB, (F_STOP - F_PASS) / (FS_IN / 2))
    n |= 1                                                     # 홀수 탭 → 지연이 정수 샘플
    b = firwin(n, (F_PASS + F_STOP) / 2, window=("kaiser", beta), fs=FS_IN)
    return b.astype(np.float32), beta


def main():
    b, beta = design()
    n = len(b)
    w, h = freqz(b.astype(np.float64), worN=8192, fs=FS_IN)
    mag = 20 * np.log10(np.abs(h) + 1e-12)
    ripple = np.ptp(mag[w <= F_PASS]); stop = mag[w >= F_STOP].max()
    print(f"taps {n}, beta {beta:.2f}, 통과 리플 {ripple:.3f} dB, 저지 최대 {stop:.1f} dB, 군지연 {(n - 1) / 2:.0f} 샘플 @ 50 kHz")

    # CMSIS FIR은 계수를 시간 역순 b[N-1]..b[0]으로 받는다. 대칭이라 같지만 규칙대로 뒤집어 저장한다
    rev = b[::-1]
    lines = ",\n".join("    " + ", ".join(f"{v: .9e}f" for v in rev[i:i + 4]) for i in range(0, n, 4))
    hdr = f"""#ifndef FIR_COEFFS_H
#define FIR_COEFFS_H
/* Tools/preproc/fir_design.py 가 만든 파일. 직접 고치지 말 것.
 * 50 kHz → 12.5 kHz (M = {M}), Kaiser beta {beta:.3f}, 통과 {F_PASS:.0f} Hz / 저지 {F_STOP:.0f} Hz / {ATT_DB:.0f} dB
 * 통과 리플 {ripple:.3f} dB, 저지 최대 {stop:.1f} dB, 군지연 {(n - 1) // 2} 샘플 @ 50 kHz
 * CMSIS 순서(시간 역순)로 저장. 대칭 계수라 순서는 결과에 영향 없음 */
#define FIR_DECIM_M     {M}u
#define FIR_NUM_TAPS    {n}u
#define FIR_GROUP_DELAY {(n - 1) // 2}u   /* 50 kHz 샘플 */

static const float fir_coeffs[FIR_NUM_TAPS] = {{
{lines}
}};

#endif
"""
    open(os.path.join(ROOT, "Core", "app", "inc", "fir_coeffs.h"), "w", encoding="utf-8").write(hdr)

    cfg = dict(version=1, fs_in=FS_IN, decim=M, fs_out=FS_IN // M, f_pass=F_PASS, f_stop=F_STOP, att_db=ATT_DB,
               window="kaiser", beta=round(float(beta), 4), num_taps=n, group_delay_in=(n - 1) // 2,
               coeffs=[float(v) for v in b],
               adc_center=2048, pcm_scale=16, pcm_round="nearest-even", pcm_saturate="int16",
               output_phase="y[k] = sum_j b[j] * x[4k - j] (CMSIS arm_fir_decimate_f32, 상태 0에서 시작. 호스트에서 CMSIS 코드로 실측)",
               note="PCM = sat16(round((adc - 2048) 를 FIR·↓4 한 값 × 16))")
    os.makedirs(os.path.join(ROOT, "config"), exist_ok=True)
    json.dump(cfg, open(os.path.join(ROOT, "config", "frontend_config.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)

    os.makedirs(os.path.join(ROOT, "reports", "step5"), exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(w, mag); ax.axvspan(0, F_PASS, color="g", alpha=.08); ax.axvspan(F_STOP, FS_IN / 2, color="r", alpha=.06)
    ax.axhline(-ATT_DB, c="r", ls="--", lw=.8); ax.axvline(FS_IN / M / 2, c="k", lw=.8)
    ax.set_ylim(-100, 5); ax.set_xlim(0, FS_IN / 2); ax.grid(alpha=.3)
    ax.set_xlabel("Hz"); ax.set_ylabel("dB"); ax.set_title(f"decimation FIR: {n} taps, Kaiser β={beta:.2f} (green: pass, red: stop, black: new Nyquist)")
    fig.tight_layout(); fig.savefig(os.path.join(ROOT, "reports", "step5", "fir_response.png"), dpi=90)


if __name__ == "__main__":
    main()
