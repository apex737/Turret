"""
STREAM 모드 신호 사슬 뷰어: 보드가 보내는 PCM과 방위 결과를 받아, 방위가 나오기까지의 단계를 한 창에서 실시간으로 본다.

사용법
  python doa/doa_scope.py --port COM8                        # 실시간
  python doa/doa_scope.py --port COM8 --save scope1          # 받은 바이트도 dumps/stream/scope1/raw.bin에 저장
  python doa/doa_scope.py --replay dumps/stream/scope1       # 저장한 raw.bin을 실제 속도로 다시 보기 (--speed 2)
  python doa/doa_scope.py --demo                             # 보드 없이 합성 신호로 화면 확인

화면 (신호 사슬 순서)
  ①② 캡슐·MAX4466 출력  : 측정 불가 (모듈 안에서 바로 ADC로 간다. 따로 꺼낼 선이 없음)
  ③ ADC 50 kHz 원본      : STREAM 모드는 보내지 않음 (UART 대역 부족). 필요하면 BURST 모드
  ④ PCM 12.5 kHz         : 파형 3채널(최근 2 s) + 스펙트럼 (회색 띠 = 방향 대역 300 ~ 3000 Hz)
  ⑤ 방향 계산 중간 단계  : 보드가 결과를 보낼 때마다 PC가 같은 창·같은 배경으로 다시 계산해서 그린다
                           (doa_stream.py와 같은 계산. MCU와 지연 0.0001샘플까지 같다고 확인됨, Step7)
                           - 창 대 배경 자기 스펙트럼 (SNR = 배경 대비 대역 전력)
                           - PHAT 상관 곡선 3쌍: 봉우리 위치 = 시간차. 점 = MCU가 보낸 값
  ⑥ 방위                 : 나침반 (MCU 결과 = 굵은 선, PC 재계산 = 주황 점선) + MCU·PC 값 비교표와 유효 판정 조건

포트는 한 프로그램만 열 수 있으므로 stream_capture.py, doa_compass.py와 동시에 실행하지 않는다.
"""
import argparse
import binascii
import os
import queue
import struct
import sys
import threading
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))                     # Tools/
import doa_stream as ds                                          # noqa: E402
import gcc_phat as g                                             # noqa: E402
from board.dump_viewer import TYPE_DOA, TYPE_PCM, PacketParser   # noqa: E402

FS = 12500.0                     # doa.h DOA_FS
N = 256                          # 프레임당 PCM 샘플 (PREPROC_OUT)
OBS = 6250                       # doa.h DOA_OBS
HOP = 3072                       # doa.h DOA_HOP
BLOCK = 512
NFFT = 2 * BLOCK
BAND = (300.0, 3000.0)
MIN_PEAK, MAX_CLOSURE, MIN_NORM, MAX_NORM, MIN_SNR = 0.15, 0.3, 0.5, 1.3, 6.0
F_VALID, F_PRESENT, F_BG, F_LEARN = 0x01, 0x02, 0x04, 0x08
S_GAP, S_RESYNC, S_CLIP = 0x08, 0x02, 0x01
BYTES_PER_S = 1562 * FS / N + 78 * FS / HOP                       # STREAM 모드 UART 데이터량 (약 76.6 KB/s)
WAVE_S = 2.0                     # 파형 표시 길이 [s]
KEEP_FRAMES = int(40 * FS / N)   # PCM 보관 40 s (배경 10 s + 여유)

CH_COL = ["#2a78d6", "#eb6834", "#1baf7a"]                        # MIC1·2·3 (dataviz 기본 팔레트 1~3)
PAIR_COL = ["#6250d6", "#e87ba4", "#008300"]                       # 쌍 (1,2) (1,3) (2,3)
INK, MUTED, PC_COL = "#1f2328", "#8a8984", "#c2410c"
PAIR_NAME = ["1-2", "1-3", "2-3"]


def wrap(deg):
    return (deg + 180.0) % 360.0 - 180.0


# ───────────────────────── 데이터 (그리기와 무관) ─────────────────────────

class Store:
    """받은 PCM 블록을 frame_seq로 보관하고, 샘플 구간 [a, b)를 꺼내 준다 (빠진 프레임이 있으면 None)."""

    def __init__(self):
        self.frames = {}
        self.last_fseq = None
        self.n = dict(pcm=0, doa=0, frame_gaps=0, gap_flags=0, resync=0, clip=0)
        self.cpu_last = self.cpu_max = 0
        self.ctr = None                                          # 첫 패킷의 (drop, ovr, qdrop)
        self.ctr_now = (0, 0, 0)

    def add(self, p):
        f = p["frame_seq"]
        if self.last_fseq is not None and f != self.last_fseq + 1:
            self.n["frame_gaps"] += 1
        self.last_fseq = f
        self.frames[f] = p["data"].astype(np.float64)
        self.frames.pop(f - KEEP_FRAMES, None)
        self.n["pcm"] += 1
        self.n["gap_flags"] += bool(p["flags"] & S_GAP)
        self.n["resync"] += bool(p["flags"] & S_RESYNC)
        self.n["clip"] += bool(p["flags"] & S_CLIP)
        self.cpu_last = p["cpu"]; self.cpu_max = max(self.cpu_max, p["cpu"])
        c = (p["drop"], p["ovr"], p["qdrop"])
        if self.ctr is None:
            self.ctr = c
        self.ctr_now = tuple((b - a) & 0xFF for a, b in zip(self.ctr, c))

    def get(self, a, b):
        f0, f1 = a // N + 1, (b - 1) // N + 1
        parts = []
        for f in range(f0, f1 + 1):
            x = self.frames.get(f)
            if x is None:
                return None
            parts.append(x)
        x = np.concatenate(parts, axis=1)
        off = a - (f0 - 1) * N
        return x[:, off:off + (b - a)]

    def recent(self, seconds):
        """최근 seconds초 파형 (빠진 프레임은 NaN) → (시각 [s], x[3, n])"""
        if self.last_fseq is None:
            return None, None
        nf = int(seconds * FS / N)
        fs_ = range(self.last_fseq - nf + 1, self.last_fseq + 1)
        x = np.concatenate([self.frames.get(f, np.full((3, N), np.nan)) for f in fs_], axis=1)
        t = (np.arange(x.shape[1]) + (fs_[0] - 1) * N) / FS
        return t, x


class Recompute:
    """MCU가 보낸 창(s0)과 배경(bg_s0, bg_n)으로 PC가 같은 계산을 다시 하고, 중간 단계를 돌려준다."""

    def __init__(self, store):
        self.store = store
        self.pos, self.d = ds.positions()
        self.max_lag = self.d / g.SOUND_SPEED * FS + 1.0
        self.bg_cache = {}
        self.f = np.fft.rfftfreq(NFFT, 1.0 / FS)
        self.band = (self.f >= BAND[0]) & (self.f <= BAND[1])

    def background(self, d):
        if not (d["flags"] & F_BG) or d["bg_n"] == 0:
            return None, "배경 없음 (보드가 아직 배우는 중이거나 D0)"
        key = (d["bg_s0"], d["bg_n"])
        if key not in self.bg_cache:
            xb = self.store.get(key[0], key[0] + key[1])
            if xb is None:
                return None, "PC가 보드의 배경 구간을 받지 못함 (뷰어를 보드보다 늦게 켬) → 배경 빼기 없이 계산. B1 버튼으로 배경을 다시 배우게 하면 맞춰짐"
            self.bg_cache = {key: ds.cross_spectra(xb, BLOCK, NFFT)}
        return self.bg_cache[key], "보드와 같은 배경 구간"

    def run(self, d):
        x = self.store.get(d["s0"], d["s0"] + OBS)
        if x is None:
            return None
        S = ds.cross_spectra(x, BLOCK, NFFT)
        bg, bg_note = self.background(d)
        snr = None
        if bg is not None:
            snr = float(10 * np.log10(sum(S[3 + c][self.band].sum() for c in range(3)) / sum(bg[3 + c][self.band].sum() for c in range(3))))
        tau, raw, peak, curves = [], [], [], []
        for k, R in enumerate(S[:3]):
            if bg is not None:
                R = R - bg[k]
            t, p, _, lags, cc = g.phat_peak(R, NFFT, FS, BAND, self.max_lag, 16, 0.01)
            i, j = g.PAIRS[k]
            corr = (ds.DELAY_US[j] - ds.DELAY_US[i]) * 1e-6 * FS
            raw.append(t); tau.append(t - corr); peak.append(p); curves.append((lags, cc, corr))
        ang, norm = g.tdoa_to_angle(tau, FS, self.pos)
        auto = sum(S[3 + c] for c in range(3)).real
        auto_bg = None if bg is None else sum(bg[3 + c] for c in range(3)).real
        return dict(tau=tau, raw=raw, peak=peak, angle=float(ang), norm=float(norm), closure=tau[0] + tau[2] - tau[1],
                    snr=snr, curves=curves, auto=auto, auto_bg=auto_bg, bg_note=bg_note)


# ───────────────────────── 소리 인식 (PANNs CNN14, AudioSet 527종) ─────────────────────────

CKPT = os.path.join(HERE, "..", "..", "DataSet", "_models", "Cnn14_16k_mAP=0.438.pth")
TAG_EVERY = 0.5                  # [s] 인식 간격
TAG_WIN = 1.0                    # [s] 인식에 쓰는 길이 (Step8과 같은 1 s)
DRONE_LIKE = ["Helicopter", "Propeller, airscrew", "Aircraft", "Aircraft engine", "Insect", "Mosquito",
              "Fly, housefly", "Bee, wasp, etc.", "Buzz", "Hum", "Mechanical fan"]   # AudioSet에 '드론'은 없다. 가까운 라벨


class Tagger:
    """받은 PCM 최근 1 s를 CNN14에 넣어 '무슨 소리인가'를 527종 확률로 낸다. 별도 스레드에서 돈다 (화면이 멈추지 않게).
    입력은 Step8과 같게: 세 채널 평균 → 12.5 → 16 kHz → RMS −30 dBFS로 맞춤. 6.25 kHz 위는 FIR에서 이미 잘려 있다."""

    def __init__(self, store, enabled=True):
        self.store, self.result, self.note = store, None, "불러오는 중"
        self.model = None
        if not enabled:
            self.note = "꺼짐 (--no-tag)"; return
        threading.Thread(target=self._loop, daemon=True).start()

    def _load(self):
        import csv
        import torch
        from panns_inference.models import Cnn14
        torch.set_num_threads(2)                                  # 그리기 스레드 몫을 남긴다
        m = Cnn14(sample_rate=16000, window_size=512, hop_size=160, mel_bins=64, fmin=50, fmax=8000, classes_num=527)
        allow = [(np._core.multiarray._reconstruct, "numpy.core.multiarray._reconstruct"), np.ndarray, np.dtype,
                 (np._core.multiarray.scalar, "numpy.core.multiarray.scalar"), np.dtypes.Float64DType, np.dtypes.Int64DType]
        with torch.serialization.safe_globals(allow):           # 가중치만 읽는다 (임의 코드 실행 방지, embed_v0.py와 같음)
            m.load_state_dict(torch.load(CKPT, map_location="cpu", weights_only=True)["model"])
        m.eval()
        lab = os.path.join(os.path.expanduser("~"), "panns_data", "class_labels_indices.csv")
        self.labels = [r["display_name"] for r in csv.DictReader(open(lab, encoding="utf-8"))]
        self.drone_idx = [self.labels.index(n) for n in DRONE_LIKE if n in self.labels]
        self.torch, self.model = torch, m

    def infer(self, x):
        """x: [3, n] PCM (12.5 kHz) → 결과 dict"""
        from scipy.signal import resample_poly
        y = x.mean(axis=0) / 32768.0
        y = y - y.mean()
        rms = float(np.sqrt(np.mean(y ** 2)) + 1e-12)
        y = resample_poly(y, 32, 25) * (10 ** (-30 / 20) / rms)  # 12.5 → 16 kHz, −30 dBFS
        with self.torch.no_grad():
            p = self.model(self.torch.from_numpy(y[None].astype(np.float32)))["clipwise_output"][0].numpy()
        top = np.argsort(p)[::-1][:6]
        return dict(top=[(self.labels[i], float(p[i])) for i in top],
                    drone=sorted(((self.labels[i], float(p[i])) for i in self.drone_idx), key=lambda t: -t[1])[:3],
                    level=20 * np.log10(rms * np.sqrt(2)))      # 사인 기준 dBFS (정규화 전 실제 크기)

    def _loop(self):
        try:
            self._load(); self.note = ""
        except Exception as e:                                    # 설치·가중치가 없으면 이유만 보여 주고 나머지는 계속
            self.note = f"꺼짐: {type(e).__name__}: {e}"[:160]; return
        while True:
            time.sleep(TAG_EVERY)
            _, x = self.store.recent(TAG_WIN)
            if x is None or np.isnan(x).any():
                continue
            try:
                self.result = self.infer(x)
            except Exception as e:
                self.note = f"오류: {e}"[:160]

    def once(self):
        """스냅샷용: 스레드를 기다리지 않고 한 번 바로"""
        if self.model is None:
            try:
                self._load(); self.note = ""
            except Exception as e:
                self.note = f"꺼짐: {type(e).__name__}: {e}"[:160]; return
        _, x = self.store.recent(TAG_WIN)
        if x is not None and not np.isnan(x).any():
            self.result = self.infer(x)


# ───────────────────────── 데모: 합성 STREAM 바이트열 ─────────────────────────

def _pkt(typ, flags, seq, fseq, n, payload, ch=3, drop=0, ovr=0, qdrop=0, cpu=0):
    hdr = struct.pack("<4sBBBBIIHHBBBB", b"\xff" * 4, 3, typ, ch, flags, seq, fseq, n, len(payload), drop, ovr, qdrop, cpu)
    body = hdr + payload
    return body + struct.pack("<H", binascii.crc_hqx(body[4:], 0xFFFF))


def demo_bytes(seconds=40.0, seed=1):
    """보드 없이 화면을 확인하는 합성 녹음. 처음 12 s는 배경만, 그 뒤 음원이 3 s마다 방향을 바꾼다.
    MCU 방위 결과는 PC 계산(doa_stream.py)으로 흉내 낸다 (부팅 → 배경 10 s 학습 → D1). 실제 보드 녹음이 아니다."""
    rng = np.random.default_rng(seed)
    nfr = int(seconds * FS / N); n = nfr * N
    t = np.arange(n) / FS
    pos, _ = ds.positions()
    f = np.fft.rfftfreq(n, 1 / FS)
    common = np.fft.irfft(np.fft.rfft(rng.standard_normal(n)) * (f < 900), n)       # 세 마이크에 같이 들어오는 저음 잡음
    x = 2.0 * common / common.std() + 1.0 * rng.standard_normal((3, n))              # [ADC LSB]
    seg = int(3 * FS); start = int(12 * FS)
    angles = [60, 60, 150, -120, -30, 90, 0, -150, 30]
    for k, s in enumerate(range(start, n, seg)):
        e = min(s + seg, n); m = e - s
        tt = t[s:e]
        src = sum(np.sin(2 * np.pi * h * 450 * tt + rng.uniform(0, 6.28)) / h for h in (1, 2, 3, 4))
        ff = np.fft.rfftfreq(m, 1 / FS)
        src = src + 0.5 * np.fft.irfft(np.fft.rfft(rng.standard_normal(m)) * ((ff > 300) & (ff < 3000)), m)
        src = 20.0 * src / src.std()
        th = np.radians(angles[k % len(angles)]); u = np.array([np.cos(th), np.sin(th)])
        Xs = np.fft.rfft(src)
        for c in range(3):
            delay = -(pos[c] @ u) / g.SOUND_SPEED + ds.DELAY_US[c] * 1e-6
            x[c, s:e] += np.fft.irfft(Xs * np.exp(-2j * np.pi * ff * delay), m)
    pcm = np.clip(np.rint(x * 16), -32768, 32767).astype("<i2")

    # MCU 흉내: 부팅 첫 프레임은 재시작 → 창과 배경은 둘째 프레임(샘플 256)부터
    p = argparse.ArgumentParser(); ds.add_args(p); A = p.parse_args([])
    pos_, d_ = ds.positions()
    bg_s0, bg_n = N, int(10 * FS)
    bg_ready = bg_s0 + (bg_n - BLOCK) // (BLOCK // 2) * (BLOCK // 2) + BLOCK
    bg = ds.cross_spectra(pcm[:, bg_s0:bg_s0 + bg_n].astype(float), BLOCK, NFFT)
    doa_at = {}
    for k, s0 in enumerate(range(N, n - OBS, HOP)):
        fin = s0 + 6144
        use_bg = fin >= bg_ready
        r = ds.estimate(pcm[:, s0:s0 + OBS].astype(float), FS, pos_, d_, BAND, BLOCK, bg=bg if use_bg else None)
        fl = (F_BG if use_bg else F_LEARN) | (F_VALID if ds.is_valid(r, A) else 0)
        if not use_bg or r["snr"] >= MIN_SNR:
            fl |= F_PRESENT
        pay = struct.pack("<I3f3ffffBBHII", s0, *r["tau"], *r["peak"], r["angle"], r["norm"],
                          r["snr"] if use_bg else 0.0, fl, 0, 900, bg_s0 if use_bg else 0, bg_n if use_bg else 0)
        doa_at[(fin + N - 1) // N] = (k, pay)
    out = bytearray()
    for fr in range(1, nfr + 1):
        out += _pkt(0x03, S_RESYNC if fr == 1 else 0, fr - 1, fr, N, pcm[:, (fr - 1) * N:fr * N].tobytes(), cpu=34)
        if fr in doa_at:
            k, pay = doa_at[fr]
            out += _pkt(0x04, 0, k, fr, 1, pay)
    return bytes(out)


# ───────────────────────── 화면 ─────────────────────────

def build_ui(args):
    import pyqtgraph as pg
    from pyqtgraph.Qt import QtCore, QtGui, QtWidgets
    dash = getattr(QtCore.Qt, "PenStyle", QtCore.Qt).DashLine
    pg.setConfigOptions(antialias=True, background="w", foreground=INK)
    app = pg.mkQApp("DOA scope")
    app.setFont(QtGui.QFont("Malgun Gothic", 9))

    win = QtWidgets.QMainWindow(); win.setWindowTitle("DOA scope — STREAM 신호 사슬")
    root = QtWidgets.QWidget(); win.setCentralWidget(root)
    lay = QtWidgets.QGridLayout(root); lay.setContentsMargins(8, 8, 8, 8); lay.setHorizontalSpacing(10)

    chain = QtWidgets.QLabel(
        "<b>신호 사슬</b> &nbsp; "
        f"<span style='color:{MUTED}'>① 캡슐 → ② MAX4466 출력 = ADC 입력 : 측정 불가 &nbsp;│&nbsp; "
        "③ ADC 50 kHz 원본 : STREAM은 보내지 않음 (BURST 모드로 따로)</span> &nbsp;│&nbsp; "
        "<b>④ PCM 12.5 kHz</b> → <b>⑤ 방향 계산 (PC 재계산)</b> → <b>⑥ 방위</b>")
    chain.setTextFormat(QtCore.Qt.TextFormat.RichText)
    lay.addWidget(chain, 0, 0, 1, 2)

    glw = pg.GraphicsLayoutWidget(); lay.addWidget(glw, 1, 0, 2, 1)
    W = {}
    W["wave"] = []
    for c in range(3):
        p = glw.addPlot(row=c, col=0)
        p.setLabel("left", f"MIC{c + 1}")
        p.showGrid(x=True, y=True, alpha=0.15)
        p.setDownsampling(auto=True, mode="peak"); p.setClipToView(True)
        if c == 0:
            p.setTitle("④ PCM 파형 (int16, ±32768 = 풀스케일) · 녹색 구간 = 마지막 방위 계산 창 0.5 s")
        if c > 0:
            p.setXLink(W["wave"][0][0])
        if c == 2:
            p.setLabel("bottom", "시각 [s] (= 샘플 번호 ÷ 12,500)")
        curve = p.plot(pen=pg.mkPen(CH_COL[c], width=1))
        reg = pg.LinearRegionItem(values=(0, 0), movable=False, brush=pg.mkBrush(26, 127, 75, 30), pen=pg.mkPen(None))
        p.addItem(reg)
        W["wave"].append((p, curve, reg))

    p = glw.addPlot(row=3, col=0, title="④ PCM 스펙트럼 (최근 0.33 s, 사인 기준 dBFS) · 회색 = 방향 대역")
    p.setLabel("bottom", "주파수 [Hz]"); p.setLabel("left", "dBFS"); p.showGrid(x=True, y=True, alpha=0.15)
    p.setXRange(0, FS / 2); p.setYRange(-110, -10)
    p.addItem(pg.LinearRegionItem(values=BAND, movable=False, brush=pg.mkBrush(120, 120, 120, 30), pen=pg.mkPen(None)))
    W["spec"] = [p.plot(pen=pg.mkPen(CH_COL[c], width=1), name=f"MIC{c + 1}") for c in range(3)]

    p = glw.addPlot(row=4, col=0, title="⑤-1 창 대 배경: 세 채널 자기 스펙트럼 합 (상대 dB)")
    p.setLabel("bottom", "주파수 [Hz]"); p.setLabel("left", "dB"); p.showGrid(x=True, y=True, alpha=0.15); p.setXRange(0, FS / 2)
    p.addItem(pg.LinearRegionItem(values=BAND, movable=False, brush=pg.mkBrush(120, 120, 120, 30), pen=pg.mkPen(None)))
    p.addLegend(offset=(10, 5), brush=pg.mkBrush(255, 255, 255, 220))
    W["auto"] = p.plot(pen=pg.mkPen(INK, width=1.5), name="이번 창")
    W["auto_bg"] = p.plot(pen=pg.mkPen(MUTED, width=1.5, style=dash), name="배경")
    W["auto_p"] = p

    p = glw.addPlot(row=5, col=0, title="⑤-2 PHAT 상관 곡선 (채널 지연 보정 전) · 봉우리 위치 = 시간차 · 점 = MCU 값 · 회색선 = 최소 봉우리 0.15")
    p.setLabel("bottom", "지연 [샘플 @ 12.5 kHz]"); p.setLabel("left", "상관"); p.showGrid(x=True, y=True, alpha=0.15)
    p.getAxis("left").enableAutoSIPrefix(False)
    p.addLegend(offset=(10, 5), brush=pg.mkBrush(255, 255, 255, 220))
    p.addItem(pg.InfiniteLine(pos=MIN_PEAK, angle=0, pen=pg.mkPen(MUTED, style=dash)))
    W["cc"] = [p.plot(pen=pg.mkPen(PAIR_COL[k], width=1.5), name=f"쌍 {PAIR_NAME[k]}") for k in range(3)]
    W["cc_pk"] = [pg.InfiniteLine(angle=90, pen=pg.mkPen(PAIR_COL[k], style=dash)) for k in range(3)]
    for ln in W["cc_pk"]:
        p.addItem(ln)
    W["cc_mcu"] = pg.ScatterPlotItem(size=10, pen=pg.mkPen("w", width=1.5))
    p.addItem(W["cc_mcu"])
    for r, h in zip(range(6), (1, 1, 1, 2, 1.6, 2.2)):
        glw.ci.layout.setRowStretchFactor(r, int(h * 10))

    # 나침반
    cp = pg.PlotWidget(); cp.setAspectLocked(True); cp.hideAxis("left"); cp.hideAxis("bottom")
    cp.setMouseEnabled(False, False); cp.setXRange(-1.45, 1.45); cp.setYRange(-1.45, 1.45); cp.setMenuEnabled(False)
    cp.setMinimumSize(360, 360)
    th = np.linspace(0, 2 * np.pi, 361)
    cp.plot(np.cos(th), np.sin(th), pen=pg.mkPen(MUTED, width=1))

    def xy(deg, r=1.0):                                         # 0° = 위(MIC1 쪽), 반시계 +
        a = np.radians(deg + args.offset)
        return -np.sin(a) * r, np.cos(a) * r
    for a in range(0, 360, 30):
        x0, y0 = xy(a - args.offset, 1.0); x1, y1 = xy(a - args.offset, 0.94)
        cp.plot([x0, x1], [y0, y1], pen=pg.mkPen(MUTED))
        tx = pg.TextItem(f"{wrap(a):+.0f}°" if a not in (0, 180) else ("0°" if a == 0 else "±180°"), color=MUTED, anchor=(0.5, 0.5))
        tx.setPos(*xy(a - args.offset, 1.2)); cp.addItem(tx)
    for c, pp in enumerate(ds.positions()[0]):
        a = np.degrees(np.arctan2(pp[1], pp[0]))
        mx, my = xy(a - args.offset, 1.33)
        cp.plot([mx], [my], pen=None, symbol="o", symbolBrush="w", symbolPen=pg.mkPen(CH_COL[c], width=2), symbolSize=12)
        t_ = pg.TextItem(f"MIC{c + 1}", color=CH_COL[c], anchor=(0.5, 1.4)); t_.setPos(mx, my); cp.addItem(t_)
    W["dots"] = pg.ScatterPlotItem(size=9, pen=pg.mkPen("w", width=1))
    cp.addItem(W["dots"])
    W["arr_mcu"] = cp.plot(pen=pg.mkPen(INK, width=5))
    W["arr_pc"] = cp.plot(pen=pg.mkPen(PC_COL, width=2, style=dash))
    W["big"] = QtWidgets.QLabel("수신 대기"); W["big"].setFont(QtGui.QFont("Malgun Gothic", 22, QtGui.QFont.Weight.Bold))
    W["big"].setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    W["xy"] = xy
    box = QtWidgets.QWidget(); bl = QtWidgets.QVBoxLayout(box); bl.setContentsMargins(0, 0, 0, 0)
    cap = QtWidgets.QLabel("<b>⑥ 방위</b> &nbsp; 굵은 선 = MCU 결과 · 주황 점선 = PC 재계산 · 점 = 최근 유효 결과"
                           + (f" · 표시 보정 {args.offset:+.1f}°" if args.offset else ""))
    cap.setTextFormat(QtCore.Qt.TextFormat.RichText)
    bl.addWidget(cap); bl.addWidget(W["big"]); bl.addWidget(cp, 1)

    # 소리 인식 막대 (상위 6개)
    tp = pg.PlotWidget(); tp.setMaximumHeight(200); tp.setMouseEnabled(False, False); tp.setMenuEnabled(False)
    tp.setXRange(0, 1, padding=0); tp.setYRange(-0.6, 5.6, padding=0); tp.getAxis("left").setWidth(170)
    tp.setTitle("지금 들리는 소리 — CNN14 AudioSet 527종, 최근 1 s (확률)")
    tp.showGrid(x=True, alpha=0.15); tp.invertY(True)
    W["tag_bar"] = pg.BarGraphItem(x0=[0] * 6, y=list(range(6)), height=0.7, width=[0] * 6, brush=pg.mkBrush("#2a78d6"))
    tp.addItem(W["tag_bar"]); W["tag_plot"] = tp
    bl.addWidget(tp)
    W["tag_note"] = QtWidgets.QLabel(""); W["tag_note"].setTextFormat(QtCore.Qt.TextFormat.RichText); W["tag_note"].setWordWrap(True)
    bl.addWidget(W["tag_note"])
    W["table"] = QtWidgets.QLabel("방위 결과를 기다리는 중"); W["table"].setTextFormat(QtCore.Qt.TextFormat.RichText)
    W["table"].setAlignment(QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft)
    W["table"].setWordWrap(True)
    bl.addWidget(W["table"])
    lay.addWidget(box, 1, 1, 2, 1)
    lay.setColumnStretch(0, 3); lay.setColumnStretch(1, 2)
    W["status"] = QtWidgets.QLabel(""); lay.addWidget(W["status"], 3, 0, 1, 2)
    win.resize(1500, 950)
    return app, win, W, pg


def table_html(d, r):
    """MCU 결과 d와 PC 재계산 r을 나란히. 판정 조건마다 통과 여부."""
    ok = lambda b: "<span style='color:#1a7f4b'>통과</span>" if b else "<span style='color:#c0362c'><b>탈락</b></span>"
    f = int(d["flags"])
    rows = []
    def row(name, mcu, pc, cond=""):
        rows.append(f"<tr><td>{name}</td><td align=right>{mcu}</td><td align=right>{pc}</td><td>{cond}</td></tr>")
    for k in range(3):
        row(f"시간차 τ{PAIR_NAME[k]} [샘플]", f"{d['tau'][k]:+.3f}", "—" if r is None else f"{r['tau'][k]:+.3f}")
    pmin = min(d["peak"])
    row("최소 봉우리", f"{pmin:.3f}", "—" if r is None else f"{min(r['peak']):.3f}", f"≥ {MIN_PEAK} {ok(pmin >= MIN_PEAK)}")
    clo = d["tau"][0] + d["tau"][2] - d["tau"][1]
    row("닫힘 |τ12+τ23−τ13|", f"{abs(clo):.3f}", "—" if r is None else f"{abs(r['closure']):.3f}", f"≤ {MAX_CLOSURE} {ok(abs(clo) <= MAX_CLOSURE)}")
    row("norm", f"{d['norm']:.3f}", "—" if r is None else f"{r['norm']:.3f}", f"{MIN_NORM} ~ {MAX_NORM} {ok(MIN_NORM <= d['norm'] <= MAX_NORM)}")
    has_bg = bool(f & F_BG)
    row("배경 대비 SNR [dB]", f"{d['snr_db']:+.1f}" if has_bg else "배경 없음",
        "—" if r is None or r["snr"] is None else f"{r['snr']:+.1f}", f"≥ {MIN_SNR:g} {ok(d['snr_db'] >= MIN_SNR)}" if has_bg else "배경 없으면 항상 PRESENT")
    row("방위 [°]", f"{wrap(d['angle']):+.1f}", "—" if r is None else f"{wrap(r['angle']):+.1f}")
    flags = " ".join(n for b, n in ((F_VALID, "VALID"), (F_PRESENT, "PRESENT"), (F_BG, "BG"), (F_LEARN, "LEARNING")) if f & b) or "없음"
    diff = "" if r is None else (f"MCU−PC 차이: 시간차 최대 {max(abs(a - b) for a, b in zip(d['tau'], r['tau'])):.4f} 샘플, "
                                 f"방위 {abs(wrap(d['angle'] - r['angle'])):.2f}° (기준 ≤ 0.02 샘플, ≤ 0.2°)")
    note = "PC가 이 창의 PCM을 다 받지 못해 재계산 생략" if r is None else r["bg_note"]
    return ("<table cellspacing=0 cellpadding=3 style='font-family:Malgun Gothic'>"
            "<tr><th align=left>항목</th><th>MCU</th><th>PC</th><th align=left>유효 판정 조건</th></tr>" + "".join(rows) + "</table>"
            f"<p>MCU flags: <b>{flags}</b> · 창 s0 = {d['s0']} ({d['s0'] / FS:.2f} s) · 계산 {d['proc_us']} µs<br>"
            f"{diff}<br><span style='color:{MUTED}'>PC 배경: {note}</span></p>")


class Scope:
    def __init__(self, args, source):
        self.args, self.source = args, source
        self.app, self.win, self.W, self.pg = build_ui(args)
        self.store, self.parser = Store(), PacketParser()
        self.rc = Recompute(self.store)
        self.tagger = Tagger(self.store, enabled=not args.no_tag and not args.snapshot)
        self.tag_shown = None
        self.hist = []                                          # (수신 시각, 방위) 최근 유효 MCU 결과
        self.last_spec = 0.0
        self.t_start = time.time()

    def feed(self, data):
        new_doa = None
        for p in self.parser.feed(data):
            if p["type"] == TYPE_PCM:
                self.store.add(p)
            elif p["type"] == TYPE_DOA:
                self.store.n["doa"] += 1
                new_doa = p
        return new_doa

    def show_doa(self, p, now):
        d = p["doa"]; f = int(d["flags"]); W = self.W
        r = self.rc.run(d)
        learning = bool(f & F_LEARN) and not f & F_BG
        ok = bool(f & F_VALID) and bool(f & F_PRESENT) and not learning
        if ok:
            self.hist.append((now, d["angle"]))
        xy = W["xy"]
        if learning:
            W["big"].setText("배경 학습 중, 조용히"); W["arr_mcu"].setData([], [])
        elif f & F_PRESENT:
            W["big"].setText(f"{wrap(d['angle'] + self.args.offset):+.0f}°" + ("" if ok else " ?"))
            x1, y1 = xy(d["angle"], 0.88)
            W["arr_mcu"].setData([0, x1], [0, y1]); W["arr_mcu"].setPen(self.pg.mkPen(INK if ok else MUTED, width=5 if ok else 2))
        else:
            W["big"].setText("소리 없음"); W["arr_mcu"].setData([], [])
        if r is not None and not learning and f & F_PRESENT:
            x2, y2 = xy(r["angle"], 0.8); W["arr_pc"].setData([0, x2], [0, y2])
        else:
            W["arr_pc"].setData([], [])
        W["table"].setText(table_html(d, r))
        for (_, _, reg) in W["wave"]:
            reg.setRegion((d["s0"] / FS, (d["s0"] + OBS) / FS))
        if r is None:
            return
        fr = self.rc.f
        W["auto"].setData(fr, 10 * np.log10(r["auto"] + 1e-12))
        if r["auto_bg"] is not None:
            W["auto_bg"].setData(fr, 10 * np.log10(r["auto_bg"] + 1e-12))
            W["auto_p"].setTitle(f"⑤-1 창 대 배경: 세 채널 자기 스펙트럼 합 · 배경 대비 대역 전력 {r['snr']:+.1f} dB (≥ 6 dB면 PRESENT)")
        else:
            W["auto_bg"].setData([], [])
            W["auto_p"].setTitle("⑤-1 이번 창 자기 스펙트럼 (배경 없음 → 배경 빼기 없이 계산)")
        pts = []
        for k in range(3):
            lags, cc, corr = r["curves"][k]
            W["cc"][k].setData(lags, cc)
            W["cc_pk"][k].setValue(r["raw"][k])
            raw_mcu = d["tau"][k] + corr                             # MCU 값을 보정 전 지연으로 되돌려 같은 축에
            pts.append(dict(pos=(raw_mcu, d["peak"][k]), brush=self.pg.mkBrush(PAIR_COL[k])))
        W["cc_mcu"].setData(pts)

    def draw_wave(self, now):
        t, x = self.store.recent(WAVE_S)
        if t is None:
            return
        for c, (p, curve, _) in enumerate(self.W["wave"]):
            curve.setData(t, x[c], connect="finite")
        if now - self.last_spec > 0.25:
            self.last_spec = now
            seg = x[:, -4096:]
            if not np.isnan(seg).any():
                w = np.hanning(seg.shape[1]); fr = np.fft.rfftfreq(seg.shape[1], 1 / FS)
                for c in range(3):
                    A = 2 * np.abs(np.fft.rfft((seg[c] - seg[c].mean()) * w)) / w.sum()
                    self.W["spec"][c].setData(fr, 20 * np.log10(A / 32768 + 1e-12))
        # 오래된 유효 점
        self.hist = [(tt, a) for tt, a in self.hist if now - tt <= self.args.keep]
        xy = self.W["xy"]
        self.W["dots"].setData([dict(pos=xy(a, 1.0), brush=self.pg.mkBrush(42, 120, 214, int(255 * max(0.15, 1 - (now - tt) / self.args.keep))))
                                for tt, a in self.hist])

    def draw_tags(self):
        r, W = self.tagger.result, self.W
        if r is None or r is self.tag_shown:
            if r is None:
                W["tag_note"].setText(f"<span style='color:{MUTED}'>{self.tagger.note or '소리를 모으는 중'}</span>")
            return
        self.tag_shown = r
        W["tag_bar"].setOpts(width=[p for _, p in r["top"]])
        W["tag_plot"].getAxis("left").setTicks([[(i, n[:26]) for i, (n, _) in enumerate(r["top"])]])
        dl = " · ".join(f"{n} {p:.2f}" for n, p in r["drone"])
        W["tag_note"].setText(f"입력 크기 {r['level']:+.1f} dBFS (인식 전 −30 dBFS로 맞춤) · 드론에 가까운 라벨: {dl}"
                              f"<br><span style='color:{MUTED}'>AudioSet에는 '드론'이 없다. 6.25 kHz 위는 잘린 입력이고, "
                              "장치 경로(스피커·마이크·보드 잡음)를 거쳐 학습 때와 다른 소리라 참고용</span>")

    def status(self, extra=""):
        n, st = self.store.n, self.parser.stats
        dd, do, dq = self.store.ctr_now
        self.W["status"].setText(
            f"PCM {n['pcm']} · 방위 {n['doa']} · 프레임 건너뜀 {n['frame_gaps']} · GAP {n['gap_flags']} · RESYNC {n['resync']} · CLIP {n['clip']} · "
            f"보드 누계 drop {dd} ovr {do} qdrop {dq} · CPU {self.store.cpu_last}% (최대 {self.store.cpu_max}%) · "
            f"수신 crc_fail {st['crc_fail']} seq_gap {st['seq_gap']}" + (f" · {extra}" if extra else ""))

    def step(self):
        now = time.time()
        data = self.source.read(now)
        if data is None:
            self.status("재생 끝"); return
        doa = self.feed(data) if data else None
        if doa is not None:
            self.show_doa(doa, now)
        self.draw_wave(now)
        self.draw_tags()
        self.status(self.source.label)

    def run(self):
        timer = self.pg.QtCore.QTimer(); timer.timeout.connect(self.step); timer.start(40)
        self.win.show()
        self.app.exec() if hasattr(self.app, "exec") else self.app.exec_()
        self.source.close()

    def snapshot(self, path, at):
        """창을 띄우지 않고 at초 분량까지 넣은 화면을 PNG로 (확인용)"""
        data = self.source.take(at)
        last = None
        for i in range(0, len(data), 4096):
            p = self.feed(data[i:i + 4096])
            last = p or last
        now = time.time()
        if last is not None:
            self.show_doa(last, now)
        self.draw_wave(now); self.status(self.source.label)
        if not self.args.no_tag:
            self.tagger.once(); self.draw_tags()
        self.win.show(); self.app.processEvents(); time.sleep(0.2); self.app.processEvents()
        self.win.grab().save(path); print(f"→ {path}")


# ───────────────────────── 입력 ─────────────────────────

class BytesSource:
    """저장한 바이트열(raw.bin 또는 데모)을 실제 속도로 내보낸다."""

    def __init__(self, data, speed, label):
        self.data, self.speed, self.label = data, speed, label
        self.i, self.t0 = 0, None

    def read(self, now):
        if self.t0 is None:
            self.t0 = now
        if self.i >= len(self.data):
            return None
        j = min(len(self.data), int((now - self.t0) * self.speed * BYTES_PER_S))
        out, self.i = self.data[self.i:j], max(self.i, j)
        return out

    def take(self, seconds):
        return self.data[:int(seconds * BYTES_PER_S)]

    def close(self):
        pass


class SerialSource:
    def __init__(self, port, baud, save):
        import serial
        self.label = f"{port} @ {baud}"
        self.ser = serial.Serial(port, baud, timeout=0.05)
        try:
            self.ser.set_buffer_size(rx_size=1 << 20)
        except (AttributeError, ValueError, serial.SerialException):
            pass
        self.ser.reset_input_buffer()
        self.raw = None
        if save:
            out = os.path.join(HERE, "..", "dumps", "stream", save); os.makedirs(out, exist_ok=True)
            self.raw = open(os.path.join(out, "raw.bin"), "wb"); self.label += f" · 저장 {save}"
        self.q, self.stop = queue.Queue(), threading.Event()
        threading.Thread(target=self._reader, daemon=True).start()   # 그리기가 늦어도 포트 읽기는 계속

    def _reader(self):
        while not self.stop.is_set():
            d = self.ser.read(self.ser.in_waiting or 1)
            if d:
                self.q.put(d)

    def read(self, now):
        chunks = []
        while True:
            try:
                chunks.append(self.q.get_nowait())
            except queue.Empty:
                break
        data = b"".join(chunks)
        if self.raw and data:
            self.raw.write(data)
        return data

    def close(self):
        self.stop.set(); self.ser.close()
        if self.raw:
            self.raw.close()


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port"); ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--save", metavar="LABEL", help="받은 바이트를 dumps/stream/LABEL/raw.bin에 저장")
    ap.add_argument("--replay", help="raw.bin 또는 그것이 든 폴더")
    ap.add_argument("--demo", action="store_true", help="합성 신호로 화면 확인 (보드 불필요)")
    ap.add_argument("--speed", type=float, default=1.0, help="재생 배속")
    ap.add_argument("--offset", type=float, default=0.0, help="표시 각도에 더할 보정 [deg]")
    ap.add_argument("--keep", type=float, default=3.0, help="최근 유효 결과를 점으로 남길 시간 [s]")
    ap.add_argument("--no-tag", action="store_true", help="소리 인식(CNN14) 패널 끄기 (PyTorch 없이 쓸 때)")
    ap.add_argument("--snapshot", help=argparse.SUPPRESS); ap.add_argument("--snapshot-at", type=float, default=20.0, help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.snapshot:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if a.demo:
        src = BytesSource(demo_bytes(), a.speed, "데모 (합성 신호, MCU 결과도 PC 계산으로 흉내)")
    elif a.replay:
        path = a.replay if a.replay.endswith(".bin") else os.path.join(a.replay, "raw.bin")
        src = BytesSource(open(path, "rb").read(), a.speed, f"재생 {path}")
    elif a.port:
        src = SerialSource(a.port, a.baud, a.save)
    else:
        ap.error("--port, --replay, --demo 중 하나")
    sc = Scope(a, src)
    if a.snapshot:
        sc.snapshot(a.snapshot, a.snapshot_at); return
    sc.run()


if __name__ == "__main__":
    main()
