"""Step8b: 장치 경로에서 생긴 가짜 선 그림 — 재생 파일 원본 대 보드 녹음 스펙트럼 (비 소리 클립).

    python harmonic/plot_fake_lines.py      → reports/step8b/fake_lines.png

원본은 재생 파일을 장치와 같은 FIR·↓4로 12.5 kHz로 만든 것, 녹음은 devpath_A MIC1. 같은 구간을 재생 시작 17.39 s, 시계 차이 +45 ppm으로 맞춘다
(embed_v5 정렬값). 두 스펙트럼은 각자 300 ~ 1,300 Hz 중앙값을 0 dB로 맞춰 겹친다. 세로선 = 녹음에서 찾은 가짜 선, 점선 = 그 평균 간격의 정수배.
"""
import csv, os, sys
import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, os.path.join(HERE, "..", "ml"))
import embed_v0 as e0
from audio.to_listen import load

ROOT = os.path.join(HERE, "..", "..")
PLAY = os.path.join(ROOT, "DataSet", "_playback")
OFF, DRIFT, FS = 17.39, 45e-6, 12500
LINES = [299.8, 579.2, 884.8, 1170.2]


def main():
    fs, p = load(os.path.join(PLAY, "30_devpath_A.wav"), 1); ref = e0.frontend_float(p, fs)
    x, _ = sf.read(os.path.join(HERE, "..", "dumps", "stream", "devpath_A", "seg_000.wav"), dtype="float64"); x = x[:, 0] - x[:, 0].mean()
    rows = [r for r in csv.DictReader(open(os.path.join(PLAY, "30_devpath.csv"), encoding="utf-8")) if r["part"] == "A" and r["cls"] in ("rain", "sea_waves", "wind")]
    N = 1 << 15; f = np.fft.rfftfreq(N, 1 / FS); A = 0; B = 0
    for r in rows:
        a, b = float(r["t0_s"]) + 0.3, float(r["t1_s"]) - 0.3
        wa = ref[int(a * FS):int(b * FS)]; s = int((OFF + a * (1 + DRIFT)) * FS); wb = x[s:s + len(wa)]
        A = A + np.abs(np.fft.rfft(wa * np.hanning(len(wa)), N)) ** 2; B = B + np.abs(np.fft.rfft(wb * np.hanning(len(wb)), N)) ** 2
    m = (f >= 300) & (f <= 1300)
    dA = 10 * np.log10(A + 1e-30); dA -= np.median(dA[m]); dB = 10 * np.log10(B + 1e-30); dB -= np.median(dB[m])
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 4))
    k = (f >= 150) & (f <= 1500)
    ax.plot(f[k], dA[k], lw=0.8, label="playback file (digital source, same FIR)")
    ax.plot(f[k], dB[k], lw=0.8, label="board recording (speaker -> MAX4466)")
    for fr in LINES:
        ax.axvline(fr, color="tab:red", lw=1, alpha=0.6)
    step = np.mean(np.array(LINES) / np.arange(1, 5))
    for n in range(1, 5):
        ax.axvline(n * step, color="k", lw=0.8, ls=":", alpha=0.6)
    ax.set_xlabel("Hz"); ax.set_ylabel("dB (median 300-1300 Hz = 0)")
    ax.set_title(f"Fake lines in rain/sea/wind clips (n={len(rows)}): red = measured peaks, dotted = exact multiples of {step:.1f} Hz")
    ax.grid(alpha=0.3); ax.legend(fontsize=8); fig.tight_layout()
    out = os.path.join(ROOT, "reports", "step8b", "fake_lines.png"); fig.savefig(out, dpi=110); print("→", out)


if __name__ == "__main__":
    main()
