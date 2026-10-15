"""녹음 파일에서 고조파 구조(f0)를 읽는다. Step4 8절의 점수 S(f0)와 같은 방식.

    python audio/f0_probe.py a.wav [b.wav ...] [--fmin 40 --fmax 500 --out dir]

잡음 바닥은 "같은 프레임의 이웃 주파수 중앙값"으로 잡는다. 드론이 녹음 내내 들려도 선은 좁아서 바닥에 섞이지 않는다.
"""
import sys, os, argparse
import numpy as np
from scipy.io import wavfile
from scipy.signal import stft
from scipy.ndimage import median_filter
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

H, CAP = 10, 10.0          # 빗살 개수, 한 빗살이 낼 수 있는 점수의 상한 (SNR, 선형)

def analyze(path, fmin, fmax, nfft=8192):
    fs, x = wavfile.read(path)
    x = x.astype(np.float64)
    if x.ndim > 1: x = x.mean(axis=1)
    x /= (np.abs(x).max() + 1e-12)
    f, t, Z = stft(x, fs, window='hann', nperseg=nfft, noverlap=nfft * 3 // 4, boundary=None)
    P = (np.abs(Z) ** 2).T                                   # [프레임, bin]
    df = fs / nfft
    floor = median_filter(P, size=(5, int(round(200 / df)) | 1), mode='nearest') / np.log(2)   # 중앙값 → 평균 환산
    snr = P / (floor + 1e-20)
    pk = np.maximum(snr, np.maximum(np.roll(snr, 1, axis=1), np.roll(snr, -1, axis=1)))        # 빗살마다 ±1칸 허용
    cand = np.arange(fmin, fmax + 0.25, 0.5)
    S = np.zeros((P.shape[0], cand.size))
    for h in range(1, H + 1):
        k = np.round(h * cand / df).astype(int)
        ok = k < P.shape[1] - 1
        S[:, ok] += np.minimum(pk[:, k[ok]], CAP)
    best = S.argmax(axis=1)
    smax = S[np.arange(S.shape[0]), best]
    # 두 배로 읽는 것을 피한다: 최고 점수의 90% 이상인 후보 중 가장 낮은 것
    low = np.array([np.argmax(S[i] >= 0.9 * smax[i]) for i in range(S.shape[0])])
    return dict(fs=fs, df=df, f=f, t=t, snr=snr, cand=cand, S=S, f0=cand[low], f0raw=cand[best], score=smax, dur=len(x) / fs)

def report(path, r, out):
    name = os.path.splitext(os.path.basename(path))[0]
    thr = max(45.0, np.percentile(r['score'], 60))            # 잡음만 있을 때의 최고 점수는 30~40 (H=10, 상한 10)
    on = r['score'] >= thr
    print(f"\n== {name}: {r['dur']:.1f}s, fs {r['fs']} Hz, 칸 폭 {r['df']:.2f} Hz, 프레임 {len(r['t'])}개, 점수 중앙값 {np.median(r['score']):.0f} / 최고 {r['score'].max():.0f}")
    print(f"   고조파 구조가 뚜렷한 프레임(점수 >= {thr:.0f}): {on.sum()}개 ({100 * on.mean():.0f}%)")
    if on.sum() >= 5:
        f0 = r['f0'][on]
        hist, edges = np.histogram(f0, bins=np.arange(r['cand'][0], r['cand'][-1] + 5, 5))
        top = np.argsort(hist)[::-1][:5]
        print('   f0 분포 (5 Hz 칸, 많은 순): ' + ', '.join(f"{edges[i]:.0f}~{edges[i + 1]:.0f} Hz {100 * hist[i] / on.sum():.0f}%" for i in top if hist[i]))
        print(f"   f0 사분위: {np.percentile(f0, 25):.1f} / {np.median(f0):.1f} / {np.percentile(f0, 75):.1f} Hz,  범위(5~95%): {np.percentile(f0, 5):.1f} ~ {np.percentile(f0, 95):.1f} Hz")
        # 가장 뚜렷한 2초 구간의 평균 스펙트럼에서 선의 위치를 직접 읽는다
        w = max(1, int(2.0 / (r['t'][1] - r['t'][0])))
        c = np.convolve(r['score'], np.ones(w) / w, mode='same').argmax()
        seg = slice(max(0, c - w // 2), c + w // 2 + 1)
        m = 10 * np.log10(r['snr'][seg].mean(axis=0))
        kmax = int(3000 / r['df'])
        peaks = [k for k in range(3, kmax) if m[k] > 8 and m[k] == m[k - 3:k + 4].max()]
        peaks = sorted(peaks, key=lambda k: -m[k])[:14]
        print(f"   t = {r['t'][c]:.1f}s 부근 2초의 뚜렷한 선: " + ', '.join(f"{r['f'][k]:.0f}Hz({m[k]:.0f}dB)" for k in sorted(peaks)))
        print(f"   그 구간의 f0 중앙값: {np.median(r['f0'][seg]):.1f} Hz (두 배 보정 전 {np.median(r['f0raw'][seg]):.1f} Hz)")
    fig, ax = plt.subplots(3, 1, figsize=(11, 9), gridspec_kw={'height_ratios': [3, 1.3, 1.6]})
    kk = r['f'] <= 2500
    ax[0].pcolormesh(r['t'], r['f'][kk], 10 * np.log10(r['snr'][:, kk].T + 1e-9), vmin=0, vmax=25, cmap='magma', shading='auto')
    ax[0].set_ylabel('Hz'); ax[0].set_title(f'{name} — SNR spectrogram (dB over local floor), bin {r["df"]:.1f} Hz')
    ax[1].scatter(r['t'][on], r['f0'][on], s=6, c='tab:blue'); ax[1].scatter(r['t'][~on], r['f0'][~on], s=2, c='lightgray')
    ax[1].set_ylabel('f0 [Hz]'); ax[1].set_xlim(r['t'][0], r['t'][-1]); ax[1].set_ylim(r['cand'][0], r['cand'][-1]); ax[1].grid(alpha=.3)
    ax[2].plot(r['t'], r['score']); ax[2].axhline(thr, color='r', ls='--'); ax[2].set_ylabel('score S'); ax[2].set_xlabel('time [s]'); ax[2].set_xlim(r['t'][0], r['t'][-1]); ax[2].grid(alpha=.3)
    fig.tight_layout(); fig.savefig(os.path.join(out, name + '_f0.png'), dpi=90); plt.close(fig)

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(); ap.add_argument('wav', nargs='+'); ap.add_argument('--fmin', type=float, default=60); ap.add_argument('--fmax', type=float, default=500); ap.add_argument('--out', default='.')
    a = ap.parse_args()
    for p in a.wav: report(p, analyze(p, a.fmin, a.fmax), a.out)
