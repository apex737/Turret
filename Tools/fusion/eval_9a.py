"""Step9A 결합 규칙 평가 틀: 분류기 자리에 정답 타임라인을 넣고, 실제 방향 결과와 합친 출력을 채점한다.

    python fusion/eval_9a.py --check              입력만 확인 (재생 정렬, 창 수). 결합 결과는 내지 않는다
    python fusion/eval_9a.py --combiner naive     기준선: "최근 판정 + 최근 방위" (Step9A가 막으려는 방식)
    python fusion/eval_9a.py --combiner rule      fusion/combine.py (결합 규칙)
    → reports/step9a/eval_<combiner>.md (수치만, 판정은 Steps/Step9A.md에)

입력 (Step7 12방향 녹음, 보드 불필요)
  방향: dumps/stream/doa_az000 ~ az330 → doa_stream.run (D1, 배경 doa_bg, 채널 지연 보정) → 0.25 s마다 0.5 s 창
        정답 방위 = 폴더 이름의 각도 + 공통 회전 (12방향 편향의 원형 평균, Step7과 같은 방법)
  분류: 정답 타임라인. 21_doa_left_100s.wav(원음 5개 × 20 s) 재생 시작을 포락선 상관으로 찾고,
        1 s 창(0.5 s 이동)이 원음 구간 안에 있고 음원이 들리면(방향 창 SNR ≥ 6 dB가 절반 이상) positive
  도착 시각: 방향 = 창 끝 + --doa-lat, 분류 = 창 끝 + --cls-lat. 결합기는 도착한 것만 본다

평가 시점 = 방향 창 끝(0.25 s마다)
  드론 시점: 그 방향 창이 원음 구간 안 + 음원이 들림 → 공동 성공 = ("drone", θ)이고 정답과 ±10° 이내
  드론 없음 시점: 재생 앞뒤, 원음 구간에서 1 s 이상 떨어짐 → "drone"을 내면 잘못된 결합

고장 주입 (각 녹음에 하나씩, 잘못된 결합 수를 센다. --max-age = 허용하는 결과 경과 시간)
  F1 PC 멈춤       세 번째 원음 가운데 3 s 동안 분류 결과가 오지 않음 → 멈춘 뒤 max-age가 지나서도 "drone"이면 위반
  F2 비드론 구간   다섯 번째 원음을 비드론으로 라벨 → 그 구간 시작 + 해제 허용(--release) 뒤에도 "drone"이면 위반
  F3 방향 무효     두 번째 원음 가운데 2 s 동안 valid = False → 무효 시작 + max-age 뒤에도 "drone"이면 위반
  F4 늦은 분류     분류 도착이 1.5 s 늦음 → 공동 성공률만 본다 (시각을 s0·s1로 맞추는지)
  F5 방향 바뀜     az000 녹음의 세 번째 원음부터 az120 녹음으로 이어 붙임 → 바뀐 뒤 max-age 지나서 옛 방위(새 정답과 10° 넘게 차이)면 위반
"""
import argparse, glob, importlib, os, re, sys
import numpy as np
import soundfile as sf
from scipy.signal import lfilter, resample_poly

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import doa.doa_stream as ds
import preproc.frontend as fe

ROOT = os.path.join(HERE, "..", "..")
DUMPS = os.path.join(HERE, "..", "dumps", "stream")
PLAY = os.path.join(ROOT, "DataSet", "_playback", "21_doa_left_100s.wav")
OUT = os.path.join(ROOT, "reports", "step9a")
CLIPS = ["11_fpv_ev1", "12_fpv_ev2", "13_fpv_ev3", "14_mini3pro_hover", "15_air3"]   # make_playback.py 순서, 20 s씩
CLIP_S = 20.0


# ---------- 입력 ----------
def doa_args():
    ap = argparse.ArgumentParser(); ds.add_args(ap)
    return ap.parse_args([])


def env(z, f, sec=0.05):
    h = int(sec * f); n = len(z) // h
    e = 10 * np.log10(np.mean(z[:n * h].reshape(n, h) ** 2, axis=1) + 1e-12)
    return (e - e.mean()) / (e.std() + 1e-12)


def play_ref():
    x, fs = sf.read(PLAY, dtype="float64", always_2d=True)
    x50 = resample_poly(x[:, 0], 50000, fs) if fs != 50000 else x[:, 0]
    return lfilter(fe.B, [1.0], x50)[::fe.M]                  # MCU와 같은 FIR·↓4 (12.5 kHz)


def align(rec, fs, ref):
    """녹음에서 재생이 시작된 샘플 (녹음 첫 샘플 기준). 50 ms 포락선 상관, 0 ~ 60 s"""
    a, b = env(rec, fs), env(ref, fe.FS_OUT)
    lags = range(0, max(1, min(len(a) - len(b) + 1, 1200)))
    c = [np.mean(a[l:l + len(b)] * b) for l in lags]
    i = int(np.argmax(c))
    return int(i * 0.05 * fs), float(c[i])


def load_recording(folder, a, bg, ref):
    segs = ds.load_segments(folder)
    fs = ds.effective_fs(folder, sum(x.shape[1] for x, _ in segs))
    doa = [r for x, s0 in segs for r in ds.run(x, fs, a, s0, bg)]
    s00 = min(s for _, s in segs)                            # 정렬용으로만 구간들을 한 줄에 놓는다 (유실 구간은 0)
    full = np.zeros(max(s + x.shape[1] for x, s in segs) - s00)
    for x, s in segs:
        full[s - s00:s - s00 + x.shape[1]] = x.mean(axis=0)
    start, corr = align(full, fs, ref)
    clips = [(s00 + start + int(k * CLIP_S * fs), s00 + start + int((k + 1) * CLIP_S * fs)) for k in range(len(CLIPS))]
    m = re.search(r"az(\d{1,3})", os.path.basename(folder))
    return dict(name=os.path.basename(folder), fs=fs, doa=doa, clips=clips, corr=corr, label=float(m.group(1)),
                first=min(s for _, s in segs), last=max(s + x.shape[1] for x, s in segs))


def clip_of(s0, s1, clips, margin):
    for k, (a, b) in enumerate(clips):
        if a + margin <= s0 and s1 <= b - margin:
            return k
    return -1


def oracle_cls(rec, nonpos_clip=None):
    """정답 타임라인 분류: 1 s 창, 0.5 s 이동. 원음 구간 안 + 방향 창 절반 이상이 들림 → positive"""
    fs = rec["fs"]; w, h = int(fs), int(fs / 2)
    pres = np.array([(r["s0"], r["s1"], r["present"]) for r in rec["doa"]])
    out = []
    for s0 in range(rec["first"], rec["last"] - w + 1, h):
        k = clip_of(s0, s0 + w, rec["clips"], int(0.25 * fs))
        m = (pres[:, 0] >= s0) & (pres[:, 1] <= s0 + w)
        aud = m.any() and pres[m, 2].mean() >= 0.5
        pos = k >= 0 and aud and k != nonpos_clip
        out.append(dict(s0=s0, s1=s0 + w, score=float(pos), positive=bool(pos)))
    return out


# ---------- 결합기 ----------
class NaiveCombiner:
    """기준선 (Step9A가 막으려는 방식): 가장 최근 분류 결과 + 가장 최근 방위. 경과 시간·유효성·시간 정렬을 보지 않는다"""
    def __init__(self, fs=12500.0):
        self.c = None; self.d = None

    def on_cls(self, ev):
        self.c = ev

    def on_doa(self, ev):
        self.d = ev

    def output(self, now):
        if self.c is None or self.d is None:
            return ("none", None)
        return ("drone", self.d["angle"]) if self.c["positive"] else ("none", None)


def make(kind, fs):
    if kind == "naive":
        return NaiveCombiner(fs)
    return importlib.import_module("fusion.combine").Combiner(fs)


def simulate(kind, fs, cls, doa, cls_lat, doa_lat):
    """도착 순서대로 결과를 넣고, 방향 창 끝마다 output()"""
    ev = [(c["s1"] + int(cls_lat * fs), 0, "cls", c) for c in cls] + [(d["s1"] + int(doa_lat * fs), 1, "doa", d) for d in doa]
    ev.sort(key=lambda e: (e[0], e[1]))
    ticks = sorted(d["s1"] for d in doa)
    cb, out, i = make(kind, fs), [], 0
    for t in ticks:
        while i < len(ev) and ev[i][0] <= t:
            (cb.on_cls if ev[i][2] == "cls" else cb.on_doa)(ev[i][3]); i += 1
        out.append((t, *cb.output(t)))
    return out


# ---------- 채점 ----------
def score(out, rec_truth, doa, clips, fs, nonpos_clip=None):
    """rec_truth(t) = 정답 방위. 공동 성공률, 드론 없음 시점의 잘못된 "drone" 수"""
    by_t = {d["s1"]: d for d in doa}
    hit = n = fa = n0 = 0
    for t, kind, ang in out:
        d = by_t.get(t)
        k = clip_of(d["s0"], d["s1"], clips, int(0.5 * fs)) if d else -1
        if k >= 0 and k != nonpos_clip and d["present"]:
            n += 1
            hit += kind == "drone" and ang is not None and ds.ang_err(ang, rec_truth(t)) <= 10
        elif all(t < a - fs or t > b + fs for a, b in clips):
            n0 += 1; fa += kind == "drone"
    return dict(joint=hit / max(n, 1), n=n, fa=fa, n0=n0)


def violations(out, t_from, t_to, cond):
    return sum(1 for t, kind, ang in out if t_from <= t <= t_to and kind == "drone" and cond(ang))


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--combiner", choices=["naive", "rule"], default="naive")
    ap.add_argument("--check", action="store_true", help="입력만 확인하고 결합 결과는 내지 않는다")
    ap.add_argument("--cls-lat", type=float, default=0.3, help="분류 결과 도착 지연 [s] (PC 추론)")
    ap.add_argument("--doa-lat", type=float, default=0.02, help="방향 결과 도착 지연 [s] (MCU 계산 + UART)")
    ap.add_argument("--max-age", type=float, default=1.0, help="고장 주입 채점에서 허용하는 결과 경과 시간 [s]")
    ap.add_argument("--release", type=float, default=2.0, help="F2 비드론 구간에서 드론 해제까지 허용 [s]")
    g = ap.parse_args()
    a = doa_args()
    xb, _ = ds.load_folder(os.path.join(DUMPS, "doa_bg"))
    bg = ds.background(xb, ds.effective_fs(os.path.join(DUMPS, "doa_bg"), xb.shape[1]), a)
    ref = play_ref()
    recs = [load_recording(f, a, bg, ref) for f in sorted(glob.glob(os.path.join(DUMPS, "doa_az*")))]
    bias = []
    for r in recs:
        v = [d["angle"] for d in r["doa"] if d["valid"] and d["present"] and clip_of(d["s0"], d["s1"], r["clips"], 0) >= 0]
        c = np.degrees(np.angle(np.mean(np.exp(1j * np.radians(v)))))
        bias.append((c - r["label"] + 180) % 360 - 180)
    off = float(np.degrees(np.angle(np.mean(np.exp(1j * np.radians(bias))))))
    print(f"녹음 {len(recs)}개, 공통 회전 {off:+.1f}° (Step7: +11.4°)")
    for r in recs:
        cls = oracle_cls(r)
        print(f"  {r['name']:10s} 재생 정렬 상관 {r['corr']:.2f}  방향 창 {len(r['doa'])}  분류 창 {len(cls)} (positive {sum(c['positive'] for c in cls)})")
    if g.check:
        return

    fs_ = lambda r: r["fs"]
    truth = lambda r: (lambda t: (r["label"] + off) % 360)
    rows, viol = [], {k: [0, 0] for k in ("F1", "F2", "F3", "F5")}
    for r in recs:
        fs = fs_(r); c0, c1, c2, c3, c4 = r["clips"]
        base = oracle_cls(r)
        res = {"F0": score(simulate(g.combiner, fs, base, r["doa"], g.cls_lat, g.doa_lat), truth(r), r["doa"], r["clips"], fs)}
        # F1 PC 멈춤
        st = (c2[0] + c2[1]) // 2; en = st + int(3 * fs)
        o = simulate(g.combiner, fs, [c for c in base if not (st <= c["s1"] + g.cls_lat * fs <= en)], r["doa"], g.cls_lat, g.doa_lat)
        viol["F1"][0] += violations(o, st + g.max_age * fs, en, lambda ang: True); viol["F1"][1] += sum(st + g.max_age * fs <= t <= en for t, *_ in o)
        # F2 비드론 구간
        o = simulate(g.combiner, fs, oracle_cls(r, nonpos_clip=4), r["doa"], g.cls_lat, g.doa_lat)
        viol["F2"][0] += violations(o, c4[0] + g.release * fs, c4[1], lambda ang: True); viol["F2"][1] += sum(c4[0] + g.release * fs <= t <= c4[1] for t, *_ in o)
        res["F2"] = score(o, truth(r), r["doa"], r["clips"], fs, nonpos_clip=4)
        # F3 방향 무효
        st = (c1[0] + c1[1]) // 2; en = st + int(2 * fs)
        d3 = [dict(d, valid=False) if st <= d["s1"] <= en else d for d in r["doa"]]
        o = simulate(g.combiner, fs, base, d3, g.cls_lat, g.doa_lat)
        viol["F3"][0] += violations(o, st + g.max_age * fs, en, lambda ang: True); viol["F3"][1] += sum(st + g.max_age * fs <= t <= en for t, *_ in o)
        # F4 늦은 분류
        res["F4"] = score(simulate(g.combiner, fs, base, r["doa"], g.cls_lat + 1.5, g.doa_lat), truth(r), r["doa"], r["clips"], fs)
        rows.append((r["name"], res))
    # F5 방향 바뀜: az000의 세 번째 원음 시작에서 az120으로 이어 붙임 (샘플 번호를 이어지게 옮긴다)
    A = next(r for r in recs if r["label"] == 0); B = next(r for r in recs if r["label"] == 120)
    tA, tB = A["clips"][2][0], B["clips"][2][0]; sh = tA - tB
    mv = lambda e: dict(e, s0=e["s0"] + sh, s1=e["s1"] + sh)
    doa5 = [d for d in A["doa"] if d["s1"] <= tA] + [mv(d) for d in B["doa"] if d["s0"] >= tB]
    cls5 = [c for c in oracle_cls(A) if c["s1"] <= tA] + [mv(c) for c in oracle_cls(B) if c["s0"] >= tB]
    o = simulate(g.combiner, A["fs"], cls5, doa5, g.cls_lat, g.doa_lat)
    newt = (120 + off) % 360
    end = B["clips"][4][1] + sh
    viol["F5"] = [violations(o, tA + g.max_age * A["fs"], end, lambda ang: ang is None or ds.ang_err(ang, newt) > 10),
                  sum(tA + g.max_age * A["fs"] <= t <= end for t, *_ in o)]

    os.makedirs(OUT, exist_ok=True)
    md = [f"# Step9A 결합 평가 — `{g.combiner}`", "",
          f"> `Tools/fusion/eval_9a.py`가 만든 파일. 수치만 적는다 (판정은 Steps/Step9A.md).",
          f"> 분류 = 정답 타임라인, 방향 = Step7 12방향 녹음 (D1, 공통 회전 {off:+.1f}°). 분류 도착 지연 {g.cls_lat} s, 방향 {g.doa_lat} s. "
          f"고장 채점의 허용 결과 경과 시간 {g.max_age} s, 해제 허용 {g.release} s.", "",
          "| 녹음 | 공동 성공률 F0 (드론 시점 수) | 드론 없음 시점의 drone 출력 (시점 수) | F2 비드론 구간 넣은 뒤 공동 성공률 | F4 분류 1.5 s 늦음 공동 성공률 |",
          "|---|---|---|---|---|"]
    for name, res in rows:
        f0 = res["F0"]
        md.append(f"| {name} | {f0['joint']:.2f} ({f0['n']}) | {f0['fa']} ({f0['n0']}) | {res['F2']['joint']:.2f} | {res['F4']['joint']:.2f} |")
    j = [res["F0"]["joint"] for _, res in rows]
    md += [f"| **최소 / 중앙** | {min(j):.2f} / {np.median(j):.2f} | {sum(res['F0']['fa'] for _, res in rows)} | | |", "",
           "## 고장 주입 — 잘못된 결합 (위반 시점 / 채점 시점)", "", "| 고장 | 위반 | 내용 |", "|---|---|---|",
           f"| F1 PC 멈춤 3 s | {viol['F1'][0]} / {viol['F1'][1]} | 멈춘 뒤 {g.max_age} s 지나서도 drone |",
           f"| F2 비드론 구간 | {viol['F2'][0]} / {viol['F2'][1]} | 비드론 시작 {g.release} s 뒤에도 drone |",
           f"| F3 방향 무효 2 s | {viol['F3'][0]} / {viol['F3'][1]} | 무효 시작 {g.max_age} s 뒤에도 drone |",
           f"| F5 방향 바뀜 (az000 → az120) | {viol['F5'][0]} / {viol['F5'][1]} | 바뀐 뒤 {g.max_age} s 지나서 옛 방위 (새 정답과 10° 초과) |", ""]
    p = os.path.join(OUT, f"eval_{g.combiner}.md")
    open(p, "w", encoding="utf-8").write("\n".join(md))
    print("\n".join(md[5:]))
    print(f"→ {p}")


if __name__ == "__main__":
    main()
