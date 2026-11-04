"""Step9A 판정·방위 결합: 분류 결과와 MCU 방향 결과를 합쳐 0.25 s마다 하나를 낸다.

    평가: python fusion/eval_9a.py --combiner rule
    실시간: python fusion/live.py (Step10)

eval_9a.py와 live.py가 결과를 도착한 순서대로 넣고 output()을 부른다. 시간은 모두 STREAM 샘플 번호(12.5 kHz).

  on_cls(ev)   분류 창 하나. ev = {"s0", "s1", "score", "positive"}   1 s 창, 약 0.5 s 이동 (PC 학습 모델 또는 MCU B0)
  on_doa(ev)   방향 창 하나 (MCU). ev = {"s0", "s1", "angle", "valid", "present", "snr"}   0.5 s 창, 0.25 s 이동
  on_gap(s)    샘플 s 앞에서 MCU 입력이 끊겼다 (PCM 패킷 RESYNC). s 이전에 시작한 창은 모두 버린다
  output(now, link_age)  now = 지금까지 받은 PCM의 마지막 샘플 번호, link_age = 마지막 패킷 뒤 지난 실제 시간 [s]
               → ("none", None) | ("drone", θ°) | ("unknown", None). 이유는 self.reason,
               "drone"일 때 고도각은 self.elev (방위와 같은 방향 창들의 고도각 중앙값, 4채널이 아니면 None — 틸트 서보용)

규칙
  1. 판정: 받은 분류 창을 s1 순서로 두고 최근 CONFIRM_N개 중 CONFIRM_K개 이상 positive면 드론 (Step8의 3창 중 2창과 같음).
     도착 순서가 아니라 s1(창이 끝난 샘플)로 줄 세운다 → 늦게 온 결과도 제 시각에 들어간다.
  2. 판정 경과 시간: 가장 최근 분류 창의 s1이 now보다 CLS_MAX_AGE 넘게 오래되면 판정을 모른다 → "unknown" (reason "stale_cls").
  3. 방위: valid이고 present인 방향 창 중 s1이 now − DOA_MAX_AGE 이후인 것만, 원형 중앙값.
     없으면 드론이어도 "unknown" (reason "no_doa"). 무효·오래된 방위는 쓰지 않는다 (I4).
  4. 드론이 아니고 판정이 신선하면 "none".
  5. 통신 단절 (스피드런 2026-11-04 추가, Step9A 남은 일): 패킷이 LINK_TIMEOUT 넘게 안 오면 now가 멈춰 2·3이 걸리지 않으므로
     실제 시간으로 본다 → "unknown" (reason "link"). 다시 오면 그대로 이어 간다 (오래된 창은 2·3이 걸러 낸다).
  6. 입력 끊김 (on_gap): 끊김 앞에서 시작한 분류·방향 창을 버린다. 복귀 뒤 드론을 다시 내려면 끊김 뒤 분류 창 CONFIRM_K개가 positive여야 한다
     (reason "recover" — 끊김 뒤 분류 창이 CONFIRM_N개 모이기 전).
"""
import numpy as np

CONFIRM_N, CONFIRM_K = 3, 2     # 최근 분류 창 3개 중 2개 positive → 드론
CLS_MAX_AGE = 1.0               # [s] 가장 최근 분류 창 끝이 이보다 오래되면 판정 모름
DOA_MAX_AGE = 0.75              # [s] 이보다 오래된 방향 창은 버림 (0.25 s 이동이라 정상이면 창 3개)
LINK_TIMEOUT = 0.5              # [s] 실제 시간으로 이만큼 패킷이 없으면 통신 단절 (정상이면 PCM이 20 ms마다 옴)


def circ_median(deg):
    """원형 중앙값: 다른 점들까지 각도 거리 합이 가장 작은 점"""
    a = np.asarray(deg, dtype=float)
    d = np.abs((a[:, None] - a[None, :] + 180) % 360 - 180).sum(axis=1)
    return float(a[np.argmin(d)])


class Combiner:
    def __init__(self, fs=12500.0):
        self.fs = fs
        self.cls = []           # (s1, positive, s0), s1 순서
        self.doa = []           # (s1, angle, s0), valid·present인 것만
        self.gap_at = None      # 마지막 입력 끊김 샘플 (복귀 판단용)
        self.reason = "start"
        self.elev = None        # 마지막 "drone" 출력의 고도각 [deg]

    def on_cls(self, ev):
        s0 = ev.get("s0", ev["s1"] - self.fs)
        if self.gap_at is not None and s0 < self.gap_at:
            return                                  # 끊김 앞에서 시작한 창: 이어 붙이면 안 됨 (I1·I4)
        self.cls.append((ev["s1"], bool(ev["positive"]), s0))
        self.cls.sort(key=lambda c: c[0])
        del self.cls[:-CONFIRM_N]

    def on_doa(self, ev):
        s0 = ev.get("s0", ev["s1"] - self.fs / 2)
        if self.gap_at is not None and s0 < self.gap_at:
            return
        if ev["valid"] and ev["present"]:
            self.doa.append((ev["s1"], float(ev["angle"]), s0, ev.get("elev")))

    def on_gap(self, sample):
        self.gap_at = sample
        self.cls = [c for c in self.cls if c[2] >= sample]
        self.doa = [d for d in self.doa if d[2] >= sample]
        self.elev = None

    def output(self, now, link_age=0.0):
        if link_age > LINK_TIMEOUT:
            self.reason = "link"
            return ("unknown", None)
        if not self.cls or now - self.cls[-1][0] > CLS_MAX_AGE * self.fs:
            self.reason = "stale_cls"
            return ("unknown", None)
        if sum(p for _, p, _ in self.cls) < CONFIRM_K:
            if self.gap_at is not None and len(self.cls) < CONFIRM_N and any(p for _, p, _ in self.cls):
                self.reason = "recover"
                return ("unknown", None)
            self.reason = "ok"
            return ("none", None)
        lo = now - DOA_MAX_AGE * self.fs
        self.doa = [d for d in self.doa if d[0] >= lo]
        if not self.doa:
            self.reason = "no_doa"
            return ("unknown", None)
        self.reason = "ok"
        el = [d[3] for d in self.doa if d[3] is not None]
        self.elev = float(np.median(el)) if el else None
        return ("drone", circ_median([d[1] for d in self.doa]))
