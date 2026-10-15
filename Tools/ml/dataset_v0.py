"""Step6(최소) 공개 원음 데이터셋 v0: 목록·라벨·split. Step8 첫 모델 평가용.

    python ml/dataset_v0.py            → data/dataset_manifest.csv, data/splits.json

원칙 (Roadmap Step6)
- split 단위는 "원본 사건". 같은 사건의 다른 마이크·파생본은 같은 fold에 둔다.
- 양성 기체가 5종뿐이라 고정 train/val/test 대신 5-fold: fold마다 기체 하나 + ESC-50 fold 하나를 시험으로 뺀다.
  → 시험 fold의 기체는 학습에서 한 번도 보지 않은 기체다 (기체 일반화를 정직하게 잰다).
- 불확실한 구간(통과 비행에서 멀리 있는 앞뒤)은 라벨 "uncertain"으로 두고 학습·평가에서 뺀다.
"""
import csv, glob, json, os, re

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
DATA = os.path.join(ROOT, "DataSet")
SAL = os.path.join(DATA, "Salford DroneNoise")
WS = os.path.join(DATA, "Western Sydney DJI Air 3", "device_1_nosync.wav")
ESC = os.path.join(DATA, "ESC-50", "ESC-50-master")

AIRCRAFT = {"Fp": "DJI FPV", "3p": "DJI Mini 3 Pro", "M3": "DJI Matrice 300", "Yn": "Yuneec H520E", "A3": "DJI Air 3"}
FOLD_OF = {"Fp": 1, "3p": 2, "M3": 3, "Yn": 4, "A3": 5}
SAL_MICS = ("M1", "M5", "M9")          # 사건마다 9개 중 3개 (같은 사건이라 정보가 겹침, 계산량 1/3)


def rows():
    pat = re.compile(r"^Ed_(\w\w)_10_(F15|H00)_.*_ev(\d+)_(M\d)\.wav$")
    for p in sorted(glob.glob(os.path.join(SAL, "Ed_*.wav"))):
        m = pat.match(os.path.basename(p))
        if not m or m.group(4) not in SAL_MICS:
            continue
        code, op, ev, mic = m.groups()
        yield dict(path=os.path.relpath(p, ROOT), channel=0, t0=0, t1=0, label="drone", source="salford",
                   aircraft=code, op="flyover" if op == "F15" else "hover", event=f"sal_{code}_{op}_ev{ev}",
                   fold=FOLD_OF[code], license="CC BY 4.0", category="drone",
                   # 통과 비행은 머리 위 전후만 확실한 양성으로 쓴다 (embed 단계에서 레벨로 판정)
                   label_rule="near_only" if op == "F15" else "all")
    for ch in range(5):
        for t0, t1 in ((82, 112), (200, 240)):
            yield dict(path=os.path.relpath(WS, ROOT), channel=ch, t0=t0, t1=t1, label="drone", source="westernsydney",
                       aircraft="A3", op="flight", event=f"ws_A3_{t0}", fold=FOLD_OF["A3"], license="CC BY-SA 4.0",
                       category="drone", label_rule="near_only")
    esc = list(csv.DictReader(open(os.path.join(ESC, "meta", "esc50.csv"), encoding="utf-8")))
    folds = {}
    for r in esc:
        folds.setdefault(r["src_file"], set()).add(r["fold"])
    for r in esc:
        if len(folds[r["src_file"]]) > 1:      # 같은 원본이 두 fold에 걸친 4개(시계·닭) → 누수 방지로 제외
            continue
        yield dict(path=os.path.relpath(os.path.join(ESC, "audio", r["filename"]), ROOT), channel=0, t0=0, t1=0,
                   label="nondrone", source="esc50", aircraft="", op="", event=f"esc_{r['src_file']}",
                   fold=int(r["fold"]), license="CC BY-NC 3.0", category=r["category"], label_rule="all")


def main():
    out = os.path.join(ROOT, "data"); os.makedirs(out, exist_ok=True)
    rs = list(rows())
    keys = list(rs[0].keys())
    with open(os.path.join(out, "dataset_manifest.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, keys); w.writeheader(); w.writerows(rs)
    # 누수 검사: 같은 사건이 두 fold에 있으면 안 됨
    ev_fold = {}
    for r in rs:
        assert ev_fold.setdefault(r["event"], r["fold"]) == r["fold"], f"사건 {r['event']}이 여러 fold에 있음"
    splits = {f"fold{k}": dict(test_aircraft=[c for c, v in FOLD_OF.items() if v == k], test_esc_fold=k,
                               test_events=sorted({r["event"] for r in rs if r["fold"] == k})) for k in range(1, 6)}
    json.dump(dict(rule="5-fold, 시험 fold = 기체 하나 + ESC-50 fold 하나. 사건 단위", folds=splits),
              open(os.path.join(out, "splits.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    n_d = sum(r["label"] == "drone" for r in rs); n_e = len({r["event"] for r in rs if r["label"] == "drone"})
    print(f"항목 {len(rs)} (드론 {n_d}, 드론 사건 {n_e}, 비드론 {len(rs) - n_d}) → data/dataset_manifest.csv, data/splits.json")


if __name__ == "__main__":
    main()
