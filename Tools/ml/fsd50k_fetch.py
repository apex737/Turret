"""FSD50K에서 어려운 비드론(곤충·새·전동공구·엔진·항공기 등) 클립만 골라 받는다 (Step8, 오탐 줄이기).

    python ml/fsd50k_fetch.py                 → DataSet/FSD50K/audio/<fname>.wav, DataSet/FSD50K/selected.csv

FSD50K(Zenodo 4060432)는 30 GB짜리 분할 ZIP이다. 전부 받지 않고 HTTP Range로
  1) 마지막 조각(.zip) 끝에서 ZIP 목차(ZIP64 포함)를 읽고
  2) 고른 파일의 로컬 헤더와 데이터만 해당 조각(.z01 …)에서 잘라 받아 푼다.
고르는 규칙
  - 범주(1차 라벨 기준): Insect 200, Bird 150, 나머지 9개 80개씩 (seed 0)
  - 제목·태그·설명에 drone·quadcopter·fpv 등이 있으면 제외 (비드론에 드론이 섞이지 않게)
  - ESC-50 원본(src_file)과 같은 Freesound ID는 제외 (ESC-50이 시험 비드론이라 누수 방지)
  - 라이선스: CC0, CC-BY, CC-BY-NC만. selected.csv에 업로더·라이선스를 남긴다 (CC-BY 출처 표기용)
내려받은 데이터는 신뢰하지 않는다: 바이트만 저장하고 실행하지 않는다. 메타데이터는 ground_truth·metadata zip (meta/).
"""
import csv, http.client, io, json, os, re, struct, sys, time, urllib.request, zlib
from concurrent.futures import ThreadPoolExecutor
import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
BASE = os.path.join(ROOT, "DataSet", "FSD50K")
META = os.path.join(BASE, "meta")
OUT = os.path.join(BASE, "audio")
URL = "https://zenodo.org/api/records/4060432/files/{}/content"
CAPS = {"Insect": 200, "Bird_vocalization_and_bird_call_and_bird_song": 150, "Engine": 80, "Wind": 80, "Hiss": 80, "Power_tool": 80,
        "Sawing": 80, "Aircraft": 80, "Motorcycle": 80, "Boat_and_Water_vehicle": 80, "Mechanical_fan": 80}
ORDER = ["Insect", "Buzz", "Cricket", "Bird_vocalization_and_bird_call_and_bird_song", "Chirp_and_tweet", "Power_tool", "Drill",
         "Mechanical_fan", "Engine", "Aircraft", "Fixed-wing_aircraft_and_airplane", "Sawing", "Motorcycle", "Boat_and_Water_vehicle", "Wind", "Hiss"]
PARENT = {"Buzz": "Insect", "Cricket": "Insect", "Chirp_and_tweet": "Bird_vocalization_and_bird_call_and_bird_song", "Drill": "Power_tool",
          "Fixed-wing_aircraft_and_airplane": "Aircraft"}
DRONE_TXT = re.compile(r"drone|quad|copter|uav|fpv|dji|\brc\b|multirot|propell", re.I)
LICENSES = ("publicdomain/zero", "licenses/by/", "licenses/by-nc/")


def get(name, a, b, tries=6):
    """조각 name의 바이트 [a, b] (양 끝 포함)"""
    for k in range(tries):
        try:
            req = urllib.request.Request(URL.format(name), headers={"Range": f"bytes={a}-{b}"})
            with urllib.request.urlopen(req, timeout=60) as r:
                d = r.read()
            if len(d) == b - a + 1:
                return d
        except (OSError, http.client.HTTPException):   # 연결 끊김(IncompleteRead 등)은 다시 받는다
            pass
        time.sleep(2 * (k + 1))
    raise IOError(f"{name} {a}-{b} 받기 실패")


def size_of(name):
    req = urllib.request.Request(URL.format(name), headers={"Range": "bytes=0-0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return int(r.headers["Content-Range"].split("/")[1])


class SplitZip:
    """분할 ZIP (prefix.z01 … prefix.zNN, prefix.zip). 디스크 번호 k = .z(k+1), 마지막 = .zip"""
    def __init__(self, prefix, nparts):
        self.parts = [f"{prefix}.z{k + 1:02d}" for k in range(nparts)] + [f"{prefix}.zip"]
        self.sizes = {}
        last = self.parts[-1]
        n = size_of(last); self.sizes[last] = n
        tail = get(last, n - 65536, n - 1)
        e = tail.rfind(b"PK\x05\x06")                     # EOCD
        loc = tail.rfind(b"PK\x06\x07", 0, e)             # ZIP64 EOCD locator
        _, z64_disk, z64_off, _ = struct.unpack_from("<IIQI", tail, loc)
        rec = get(self.parts[z64_disk], z64_off, z64_off + 55)
        (sig, _, _, _, _, cd_disk, _, n_ent, cd_size, cd_off) = struct.unpack("<IQHHIIQQQQ", rec)
        assert sig == 0x06064B50
        cd = get(self.parts[cd_disk], cd_off, cd_off + cd_size - 1)
        self.entries, p = {}, 0
        while p < len(cd):
            (sig, _, _, _, method, _, _, _, csize, usize, nlen, xlen, clen, disk, _, _, lho) = struct.unpack_from("<IHHHHHHIIIHHHHHII", cd, p)
            assert sig == 0x02014B50
            name = cd[p + 46:p + 46 + nlen].decode("utf-8", "replace")
            x = cd[p + 46 + nlen:p + 46 + nlen + xlen]
            q = 0
            while q + 4 <= len(x):                         # ZIP64 확장 필드: 0xFFFFFFFF인 값만 순서대로 들어 있다
                hid, hl = struct.unpack_from("<HH", x, q)
                if hid == 1:
                    vals, r_ = [], q + 4
                    for cond in (usize == 0xFFFFFFFF, csize == 0xFFFFFFFF, lho == 0xFFFFFFFF):
                        if cond:
                            vals.append(struct.unpack_from("<Q", x, r_)[0]); r_ += 8
                    it = iter(vals)
                    if usize == 0xFFFFFFFF: usize = next(it)
                    if csize == 0xFFFFFFFF: csize = next(it)
                    if lho == 0xFFFFFFFF: lho = next(it)
                    if disk == 0xFFFF: disk = struct.unpack_from("<I", x, r_)[0]
                q += 4 + hl
            self.entries[os.path.basename(name)] = (disk, lho, csize, method)
            p += 46 + nlen + xlen + clen

    def _size(self, k):
        if self.parts[k] not in self.sizes:
            self.sizes[self.parts[k]] = size_of(self.parts[k])
        return self.sizes[self.parts[k]]

    def _read(self, disk, off, n):
        """디스크 경계를 넘어가는 읽기"""
        out = b""
        while n > 0:
            sz = self._size(disk)
            m = min(n, sz - off)
            out += get(self.parts[disk], off, off + m - 1)
            n -= m; disk += 1; off = 0
        return out

    def extract(self, fname):
        disk, lho, csize, method = self.entries[fname]
        h = self._read(disk, lho, 30)
        nlen, xlen = struct.unpack_from("<HH", h, 26)
        # 데이터 시작 = 로컬 헤더 + 이름 + 확장. 디스크 경계를 넘을 수 있어 같은 함수로 이어 읽는다
        start = lho + 30 + nlen + xlen; d = disk
        while start >= self._size(d):
            start -= self._size(d); d += 1
        data = self._read(d, start, csize)
        if method == 0:
            return data
        if method == 8:
            return zlib.decompress(data, -15)
        raise ValueError(f"압축 방식 {method}")


def select():
    info = {}
    for part in ("dev", "eval"):
        info.update(json.load(open(os.path.join(META, "FSD50K.metadata", f"{part}_clips_info_FSD50K.json"), encoding="utf-8")))
    esc = {r["src_file"] for r in csv.DictReader(open(os.path.join(ROOT, "DataSet", "ESC-50", "ESC-50-master", "meta", "esc50.csv"), encoding="utf-8"))}
    pool = {}
    for part in ("dev", "eval"):
        for r in csv.DictReader(open(os.path.join(META, "FSD50K.ground_truth", f"{part}.csv"), encoding="utf-8")):
            labs = r["labels"].split(",")
            hit = [t for t in ORDER if t in labs]
            if not hit:
                continue
            i = info.get(r["fname"], {})
            if DRONE_TXT.search(" ".join([i.get("title", ""), " ".join(i.get("tags", [])), i.get("description", "")])):
                continue
            if r["fname"] in esc or not any(l in i.get("license", "") for l in LICENSES):
                continue
            cls = PARENT.get(hit[0], hit[0])
            pool.setdefault(cls, []).append(dict(fname=r["fname"], part=part, cls=cls, labels=r["labels"], title=i.get("title", ""),
                                                 uploader=i.get("uploader", ""), license=i.get("license", "")))
    rng = np.random.default_rng(0)
    sel = []
    for cls, cap in CAPS.items():
        c = pool.get(cls, [])
        sel += [c[k] for k in sorted(rng.choice(len(c), min(cap, len(c)), replace=False))]
    return sel


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.makedirs(OUT, exist_ok=True)
    sel = select()
    with open(os.path.join(BASE, "selected.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, list(sel[0].keys())); w.writeheader(); w.writerows(sel)
    print(f"고른 클립 {len(sel)}개 → selected.csv")
    zips = {"dev": SplitZip("FSD50K.dev_audio", 5), "eval": SplitZip("FSD50K.eval_audio", 1)}
    print(f"ZIP 목차: dev {len(zips['dev'].entries)}, eval {len(zips['eval'].entries)}")
    todo = [r for r in sel if not os.path.exists(os.path.join(OUT, r["fname"] + ".wav"))]
    print(f"이미 받음 {len(sel) - len(todo)}, 남음 {len(todo)}")

    def fetch(r):
        try:
            data = zips[r["part"]].extract(r["fname"] + ".wav")
        except (IOError, ValueError, zlib.error) as e:
            return r["fname"], str(e)
        if data[:4] != b"RIFF":
            return r["fname"], "RIFF 아님"
        tmp = os.path.join(OUT, r["fname"] + ".part")
        open(tmp, "wb").write(data); os.replace(tmp, os.path.join(OUT, r["fname"] + ".wav"))   # 다 받은 뒤에만 .wav
        return r["fname"], None

    fails = []
    with ThreadPoolExecutor(4) as ex:                      # 동시 4개 (Zenodo 부담을 작게)
        for k, (fn, err) in enumerate(ex.map(fetch, todo)):
            if err:
                fails.append((fn, err))
            if k % 100 == 0:
                print(f"{k + 1}/{len(todo)}  실패 {len(fails)}")
    print(f"완료 {len(sel) - len(fails)}/{len(sel)}, 실패 {len(fails)} {fails[:5]} → {OUT}")


if __name__ == "__main__":
    main()
