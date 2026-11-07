# Tools/.venv
"""기초 정확도 측정 (2026-11-07). 음원을 고정하고 방위각·고도각마다 30 s씩 반복 녹음 → 실제 각도와 보드 추정 각도를 CSV로.

    python doa/accuracy.py --port COM8            # 안내에 따라 자리마다 녹음 (끊겨도 다시 실행하면 이어서)
    python doa/accuracy.py --collect              # 녹음 폴더만 다시 읽어 CSV 두 개를 새로 만듦
    python doa/accuracy.py --plan                 # 녹음 계획표와 예상 시간만 보기
    python doa/accuracy.py --port COM8 --set rod --mic4-mm 90   # 확인 실험: 통 빼고 MIC4를 막대로 (고도 0°, 6방향)

배치 (Step7과 같은 각도 규칙: 위에서 볼 때 MIC1 쪽 0°, 반시계 +)
  - 핸드폰(음원)은 각도판 0° 선 위, 배열 중심에서 수평 거리 l에 고정. 높이 h는 3마이크 평면 기준.
  - 배열을 시계 방향으로 θ 돌린다 (MIC1 화살표가 눈금 θ) → 음원은 배열 기준 방위 +θ, 고도 atan(h ÷ l).
  - 핸드폰은 41_phone_elev_fpv_2min.wav를 반복 재생으로 계속 틀어 둔다 (녹음 사이에도). 보드를 켤 때 처음 10 s는 조용히 (배경 학습).

저장
  Tools/dumps/stream/acc_e<고도>_a<방위>_r<반복>/   stream_capture.py 출력 + meta.json (실제 각도, h, l)
  reports/accuracy/acc_windows.csv   보드 방향 창(0.25 s)마다: 실제·추정 방위·고도, 오차, 판정 플래그
  reports/accuracy/acc_trials.csv    녹음마다: 창 수, 유효율, 오차 중앙값·p95, 편향
"""
import argparse, csv, json, math, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT_DEF = os.path.join(TOOLS, "dumps", "stream")
REPORT = os.path.join(TOOLS, "..", "reports", "accuracy")
CAPTURE = os.path.join(TOOLS, "board", "stream_capture.py")

L_CM = 100.0                                      # 계획 수평 거리
SETS = {   # 이름 → (계획 [(계획 고도°, 방위 목록, 반복 수)], 설명). 녹음 이름 앞머리 = 이름
    "acc": ([(0, list(range(0, 360, 30)), 2), (20, list(range(0, 360, 30)), 2), (40, list(range(0, 360, 60)), 2)],
            "기초 정확도 (2026-11-07 오전)"),
    "rod": ([(0, list(range(0, 360, 60)), 1)],
            "통을 빼고 MIC4를 막대로 받친 확인 실험 — acc 고도 0°와 같은 6방향 비교"),
}
PREFIX = "acc"
PLAN = [(0, list(range(0, 360, 30)), 2),          # (계획 고도°, 방위 목록, 반복 수) — main에서 SETS로 바꿈
        (20, list(range(0, 360, 30)), 2),
        (40, list(range(0, 360, 60)), 2)]
REC_MIN = 0.5                                     # 녹음 하나 30 s → 방향 창 약 120개
MIC4_MM = None
START_DELAY_S = 5                                 # Enter 뒤 녹음 시작까지 (그사이 핸드폰 재생)
F_VALID, F_PRESENT, F_LEARNING = 0x01, 0x02, 0x08


def label(el, az, rep):
    return f"{PREFIX}_e{el:02d}_a{az:03d}_r{rep}"


def trials():
    for el, azs, reps in PLAN:
        for rep in range(1, reps + 1):
            for az in azs:
                yield el, az, rep


def wrap(d):
    return (d + 180.0) % 360.0 - 180.0


def pct(xs, q):
    if not xs:
        return float("nan")
    s = sorted(xs); k = (len(s) - 1) * q / 100.0; i = int(math.floor(k)); j = min(i + 1, len(s) - 1)
    return s[i] + (s[j] - s[i]) * (k - i)


def circ_mean(deg):
    if not deg:
        return float("nan")
    c = sum(math.cos(math.radians(d)) for d in deg); s = sum(math.sin(math.radians(d)) for d in deg)
    return math.degrees(math.atan2(s, c))


def read_trial(d):
    """녹음 폴더 하나 → (meta, 창 목록). 창: 보드 doa_mcu.csv 한 줄 + 오차."""
    meta = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
    rows = []
    p = os.path.join(d, "doa_mcu.csv")
    if not os.path.exists(p):
        return meta, rows
    for r in csv.DictReader(open(p, encoding="utf-8")):
        fl = int(r["flags"])
        az, el = float(r["angle"]), float(r["elev"])
        peaks = [float(r[k]) for k in r if k.startswith("peak") and r[k] != ""]
        rows.append(dict(t_rx=float(r["t_rx"]), frame_seq=int(r["frame_seq"]),
                         est_az=az, est_el=el,
                         err_az=round(wrap(az - meta["truth_az"]), 3), err_el=round(el - meta["truth_el"], 3),
                         valid=int(bool(fl & F_VALID)), present=int(bool(fl & F_PRESENT)),
                         learning=int(bool(fl & F_LEARNING)),
                         snr_db=float(r["snr_db"]), resid=float(r["resid"]), norm=float(r["norm"]),
                         peak_min=min(peaks) if peaks else float("nan"), flags=fl,
                         **{k: float(r[k]) for k in ("tau12", "tau13", "tau23", "tau14", "tau24", "tau34") if k in r}))
    return meta, rows


def summarize(meta, rows, summ):
    pres = [w for w in rows if w["present"] and not w["learning"]]
    ok = [w for w in pres if w["valid"]]
    ea = [w["err_az"] for w in ok]; ee = [w["err_el"] for w in ok]
    aa = [abs(x) for x in ea]; ae = [abs(x) for x in ee]
    pk = summ.get("packets", {}) if summ else {}
    return dict(label=meta["label"], planned_el=meta["planned_el"], truth_az=meta["truth_az"], truth_el=round(meta["truth_el"], 2),
                rep=meta["rep"], h_cm=meta["h_cm"], l_cm=meta["l_cm"],
                n_win=len(rows), n_present=len(pres), n_valid=len(ok),
                valid_rate=round(len(ok) / len(pres), 3) if pres else float("nan"),
                az_bias=round(circ_mean(ea), 2) if ea else float("nan"),
                az_abs_med=round(pct(aa, 50), 2), az_abs_p95=round(pct(aa, 95), 2),
                el_bias=round(pct(ee, 50), 2), el_abs_med=round(pct(ae, 50), 2), el_abs_p95=round(pct(ae, 95), 2),
                snr_med=round(pct([w["snr_db"] for w in pres], 50), 1),
                clip_packets=pk.get("clip_packets", ""), frames_missing=pk.get("frames_missing", ""))


def collect(root):
    os.makedirs(REPORT, exist_ok=True)
    win_rows, trial_rows = [], []
    for name in sorted(os.listdir(root)):
        d = os.path.join(root, name)
        if not (re.fullmatch(PREFIX + r"_e\d\d_a\d{3}_r\d+", name) and os.path.exists(os.path.join(d, "meta.json"))):   # _x1 = 버린 녹음
            continue
        meta, rows = read_trial(d)
        sp = os.path.join(d, "summary.json")
        summ = json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else None
        for w in rows:
            win_rows.append(dict(label=meta["label"], planned_el=meta["planned_el"], truth_az=meta["truth_az"],
                                 truth_el=round(meta["truth_el"], 2), rep=meta["rep"], **w))
        trial_rows.append(summarize(meta, rows, summ))
    for fn, data in ((f"{PREFIX}_windows.csv", win_rows), (f"{PREFIX}_trials.csv", trial_rows)):
        p = os.path.join(REPORT, fn)
        with open(p, "w", newline="", encoding="utf-8") as f:
            if data:
                w = csv.DictWriter(f, fieldnames=list(data[0].keys())); w.writeheader(); w.writerows(data)
    return trial_rows


def show_plan():
    n = sum(len(azs) * reps for _, azs, reps in PLAN)
    print(f"녹음 {n}개 × {REC_MIN * 60:.0f} s, 옮기는 시간 포함 약 {n * 70 / 60:.0f}분 (자리당 70 s 가정)")
    for el, azs, reps in PLAN:
        h = L_CM * math.tan(math.radians(el))
        print(f"  고도 {el:2d}° (l {L_CM:.0f} cm, h {h:5.1f} cm): 방위 {azs[0]} ~ {azs[-1]}° {len(azs)}곳 × 반복 {reps}")


def ask(prompt, default=None):
    s = input(prompt).strip()
    return s if s else default


def setup_for(el, root):
    """고도 묶음마다 실제로 잰 h, l을 한 번 받는다."""
    p = os.path.join(root, f"{PREFIX}_setup.json")
    st = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    key = str(el)
    if key in st:
        return st[key]
    h_plan = L_CM * math.tan(math.radians(el))
    print(f"\n=== 고도 {el}° 묶음 준비 ===")
    print(f"  핸드폰 스피커: 각도판 0° 선 위, 배열 중심에서 수평 {L_CM:.0f} cm, 3마이크 평면보다 {h_plan:.1f} cm 위 (책·상자로 고정, 스피커가 배열을 향하게)")
    while True:
        try:
            h = float(ask(f"  실제로 잰 높이 h [cm] (Enter = {h_plan:.1f}): ", h_plan))
            l = float(ask(f"  실제로 잰 수평 거리 l [cm] (Enter = {L_CM:.0f}): ", L_CM))
            break
        except ValueError:
            print("  숫자로 입력한다")
    st[key] = dict(h_cm=h, l_cm=l, truth_el=math.degrees(math.atan2(h, l)), time=time.strftime("%Y-%m-%d %H:%M:%S"))
    json.dump(st, open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"  → 실제 고도각 {st[key]['truth_el']:.1f}°")
    return st[key]


def one_line(s):
    return (f"  창 {s['n_win']} · 소리 있음 {s['n_present']} · 유효 {s['n_valid']} ({s['valid_rate']})  "
            f"방위 오차 |중앙| {s['az_abs_med']}° p95 {s['az_abs_p95']}° 편향 {s['az_bias']}°  "
            f"고도 오차 |중앙| {s['el_abs_med']}° 편향 {s['el_bias']}°  clip {s['clip_packets']} 유실 {s['frames_missing']}")


def run(port, root):
    all_t = list(trials())
    for i, (el, az, rep) in enumerate(all_t):
        lab = label(el, az, rep); d = os.path.join(root, lab)
        if os.path.exists(os.path.join(d, "meta.json")) and os.path.exists(os.path.join(d, "raw.bin")):
            continue                                                    # 이미 한 자리 (이어서 하기)
        st = setup_for(el, root)
        left = len(all_t) - i
        while True:
            print(f"\n[{i + 1}/{len(all_t)}, 남은 약 {left * 70 / 60:.0f}분] 고도 {el}° · 반복 {rep} · 배열 MIC1 화살표 → 눈금 {az}°")
            k = ask(f"  배열을 맞췄으면 Enter → {START_DELAY_S} s 안에 핸드폰 재생 (s = 이 자리 건너뜀, q = 끝냄): ", "")
            if k == "q":
                return
            if k == "s":
                break
            meta = dict(label=lab, planned_el=el, truth_az=float(az), truth_el=st["truth_el"], rep=rep,
                        h_cm=st["h_cm"], l_cm=st["l_cm"], port=port, start=time.strftime("%Y-%m-%d %H:%M:%S"),
                        set=PREFIX, mic4_mm=MIC4_MM)
            for c in range(START_DELAY_S, 0, -1):                     # Enter 뒤 재생을 틀 시간
                print(f"  {c} s 뒤 녹음 시작…", end="\r", flush=True); time.sleep(1)
            print("  녹음 시작            ")
            rc = subprocess.run([sys.executable, CAPTURE, "--port", port, "--label", lab, "--minutes", str(REC_MIN), "--out", root]).returncode
            rb = os.path.join(d, "raw.bin")
            if rc != 0 or not os.path.exists(rb) or os.path.getsize(rb) == 0:
                print("  녹음 실패 (포트를 다른 프로그램이 쓰는지, 보드가 STREAM 모드인지 확인) — 같은 자리를 다시")
                if os.path.exists(d):
                    n = 1
                    while os.path.exists(f"{d}_x{n}"):
                        n += 1
                    os.rename(d, f"{d}_x{n}")
                continue
            json.dump(meta, open(os.path.join(d, "meta.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
            m, rows = read_trial(d)
            sp = os.path.join(d, "summary.json")
            s = summarize(m, rows, json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else None)
            print(one_line(s))
            if s["n_present"] < 0.7 * s["n_win"]:
                print(f"  ! 소리 있는 창이 {s['n_present']} / {s['n_win']}뿐 — 핸드폰이 녹음 내내 재생 중이었는지 확인하고 r로 다시")
            if s["n_valid"] < 20 or (s["clip_packets"] not in ("", 0)):
                print("  ! 유효 창이 20개 미만이거나 클리핑 — 소리·배치를 보고 다시 할지 정한다")
            k = ask("  Enter = 다음 자리, r = 이 자리 다시: ", "")
            if k == "r":
                n = 1
                while os.path.exists(f"{d}_x{n}"):
                    n += 1
                os.rename(d, f"{d}_x{n}")                               # 버린 녹음은 지우지 않고 이름만 바꿈 (collect가 읽지 않음)
                continue
            collect(root)
            break
    collect(root)
    print(f"\n끝. CSV → {os.path.abspath(REPORT)}")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--port"); ap.add_argument("--root", default=ROOT_DEF)
    ap.add_argument("--collect", action="store_true"); ap.add_argument("--plan", action="store_true")
    ap.add_argument("--set", default="acc", choices=list(SETS), help="녹음 묶음 (acc = 기초 정확도, rod = 통 뺀 확인 실험)")
    ap.add_argument("--mic4-mm", type=float, help="MIC4 높이 실측 [mm] (3마이크 평면 기준). meta.json에만 적는다 — 보드 계산은 57.2 mm 그대로")
    a = ap.parse_args()
    global PREFIX, PLAN, MIC4_MM
    PREFIX, PLAN, MIC4_MM = a.set, SETS[a.set][0], a.mic4_mm
    print(f"묶음 {a.set}: {SETS[a.set][1]}")
    if a.plan:
        show_plan(); return
    if a.collect:
        t = collect(a.root)
        print(f"녹음 {len(t)}개 → {os.path.abspath(REPORT)}")
        for s in t:
            print(s["label"], one_line(s))
        return
    if not a.port:
        ap.error("--port COMx 가 필요하다 (또는 --collect · --plan)")
    show_plan(); run(a.port, a.root)


if __name__ == "__main__":
    main()
