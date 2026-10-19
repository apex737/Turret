"""영상·녹음에서 FPV 후보 구간을 잘라 사람이 듣고 라벨하는 로컬 페이지를 만든다 (Step8 v2 데이터 확대).

    python ml/fpv_candidates.py DataSet/DVIDS_FPV/*.mp4 [--out DataSet/_listen/FPV_candidates_2]
    → 그 폴더를 로컬 서버로 연다:  python -I -m http.server 8765 --bind 127.0.0.1 --directory <out>
      브라우저에서 http://127.0.0.1:8765/ → 다 듣고 "labels.csv 저장" → labels.csv를 <out>에 넣는다

1) ffmpeg(Octave 설치본)로 소리만 DataSet/_extract/<폴더 이름>/*.wav (이미 있으면 건너뜀)
2) 1 s 창마다 CNN14: 말소리·음악 점수 < 0.3, 레벨이 파일 중앙값 −25 dB 이상인 연속 구간 → 최대 6 s 조각
   AudioSet 점수로는 FPV를 고를 수 없다 (5인치 FPV를 전동공구·드릴로 분류). 대신 확실한 FPV 두 개
   (Freesound 5deMayo, TinyHawk)와의 임베딩 유사도로 정렬만 하고 판정은 사람이 한다. Salford FPV는 시험용이라 쓰지 않는다
3) 조각 WAV·스펙트로그램 PNG·candidates.json·index.html
내려받은 파일은 신뢰하지 않는 데이터로 다룬다: 이 스크립트는 Tools/에서 실행하고 결과는 별도 폴더에 쓴다.
"""
import argparse, csv, glob, json, os, subprocess, sys
import numpy as np
import soundfile as sf
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, ".."))
import embed_v0 as e0

DS = os.path.join(e0.ROOT, "DataSet")
FFMPEG = r"C:\Program Files\GNU Octave\Octave-11.3.0\mingw64\bin\ffmpeg.exe"
REFS = [os.path.join(DS, "Freesound_FPV", "524331__5demayo__quadcopter-flyby-multiple.mp3"),
        os.path.join(DS, "Freesound_FPV", "677833__sadiquecat__tiny-hawk-2-short-flight.wav")]
SEG_MAX, SEG_MIN = 10, 3                                 # 창 단위 (0.5 s 이동): 최대 6 s, 최소 2 s


def extract(path):
    """영상·MP3 → 48 kHz 16비트 WAV (DataSet/_extract/<폴더>/). WAV는 그대로"""
    if path.lower().endswith(".wav"):
        return path
    out_dir = os.path.join(DS, "_extract", os.path.basename(os.path.dirname(os.path.abspath(path))))
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, os.path.splitext(os.path.basename(path))[0] + ".wav")
    if not os.path.exists(out):
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", path, "-vn", "-acodec", "pcm_s16le", out], check=True)
    return out


def load16(path):
    x, fs = sf.read(path, dtype="float64")
    x = x.mean(axis=1) if x.ndim > 1 else x
    return e0.rs(x - x.mean(), fs, 16000)


class Model:
    def __init__(self):
        from panns_inference.models import Cnn14
        self.m = Cnn14(sample_rate=16000, window_size=512, hop_size=160, mel_bins=64, fmin=50, fmax=8000, classes_num=527)
        self.m.load_state_dict(e0.load_ckpt()["model"]); self.m.eval()
        lab = list(csv.reader(open(os.path.expanduser("~/panns_data/class_labels_indices.csv"), encoding="utf-8")))[1:]
        self.names = [r[2] for r in lab]

    def __call__(self, y):
        W = e0.windows(y)
        rms = np.sqrt(np.mean(W ** 2, axis=1))
        Wn = W / (rms[:, None] + 1e-12) * 10 ** (-30 / 20)
        E, C = [], []
        with torch.no_grad():
            for i in range(0, len(Wn), 64):
                o = self.m(torch.from_numpy(Wn[i:i + 64].astype(np.float32)))
                E.append(o["embedding"].numpy()); C.append(o["clipwise_output"].numpy())
        return np.concatenate(E), np.concatenate(C), 20 * np.log10(rms + 1e-12)


def spectrogram_png(clip, path):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    from scipy.signal import spectrogram
    f, t, S = spectrogram(clip, 16000, nperseg=1024, noverlap=768)
    L = 10 * np.log10(S + 1e-12)
    plt.figure(figsize=(4.2, 1.6), dpi=90)
    plt.pcolormesh(t, f, L, shading="auto", cmap="magma", vmin=np.percentile(L, 30))
    plt.ylim(0, 5000); plt.axis("off"); plt.tight_layout(pad=0); plt.savefig(path); plt.close()


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", help="영상(mp4)·MP3·WAV. PowerShell은 *를 펼치지 않으므로 glob을 여기서 푼다")
    ap.add_argument("--out", default=os.path.join(DS, "_listen", "FPV_candidates_new"))
    a = ap.parse_args()
    files = [f for p in a.inputs for f in (sorted(glob.glob(p)) if any(c in p for c in "*?") else [p])]
    os.makedirs(a.out, exist_ok=True)
    model = Model()
    R = np.concatenate([model(load16(extract(p)))[0] for p in REFS])
    R /= np.linalg.norm(R, axis=1, keepdims=True)
    rows = []
    for p in files:
        wav = extract(p); key = os.path.splitext(os.path.basename(wav))[0]
        y = load16(wav)
        E, C, lv = model(y)
        sim = np.sort((E / np.linalg.norm(E, axis=1, keepdims=True)) @ R.T, axis=1)[:, -5:].mean(axis=1)
        sp, mu = C[:, model.names.index("Speech")], C[:, model.names.index("Music")]
        ok = (sp < 0.3) & (mu < 0.3) & (lv > np.median(lv) - 25)
        n0 = len(rows); i = 0
        while i < len(ok):
            if not ok[i]:
                i += 1; continue
            j = i
            while j < len(ok) and ok[j]:
                j += 1
            for s0 in range(i, j, SEG_MAX):
                s1 = min(s0 + SEG_MAX, j)
                if s1 - s0 < SEG_MIN:
                    continue
                t0, t1 = s0 * 0.5, s1 * 0.5 + 0.5
                cid = f"{key}_{t0:06.1f}"
                clip = y[int(t0 * 16000):int(t1 * 16000)]
                sf.write(os.path.join(a.out, cid + ".wav"), (clip / (np.abs(clip).max() + 1e-12) * 0.7).astype(np.float32), 16000, subtype="PCM_16")
                spectrogram_png(clip, os.path.join(a.out, cid + ".png"))
                rows.append(dict(id=cid, video=key, file=key, t0=round(t0, 1), t1=round(t1, 1), sim=round(float(sim[s0:s1].mean()), 3),
                                 top=", ".join(model.names[k] for k in np.argsort(C[s0:s1].mean(axis=0))[::-1][:3])))
            i = j
        print(f"{key}: 후보 {len(rows) - n0}개")
    rows.sort(key=lambda r: -r["sim"])
    json.dump(rows, open(os.path.join(a.out, "candidates.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    page = open(os.path.join(HERE, "fpv_label_page.html"), encoding="utf-8").read()
    open(os.path.join(a.out, "index.html"), "w", encoding="utf-8").write(page.replace("__ROWS__", json.dumps(rows, ensure_ascii=False)))
    print(f"후보 {len(rows)}개 → {a.out}\\index.html (로컬 서버로 열 것, 위 설명)")


if __name__ == "__main__":
    main()
