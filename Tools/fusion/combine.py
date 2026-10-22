"""Step9A 판정·방위 결합: PC 분류 결과와 MCU 방향 결과를 합쳐 0.25 s마다 하나를 낸다.

    평가: python fusion/eval_9a.py --combiner rule

eval_9a.py(나중에는 Step10 실시간 루프)가 결과를 도착한 순서대로 넣고 output()을 부른다. 시간은 모두 STREAM 샘플 번호(12.5 kHz).

  on_cls(ev)   분류 창 하나 (PC). ev = {"s0", "s1", "score", "positive"}   1 s 창, 0.5 s 이동
  on_doa(ev)   방향 창 하나 (MCU). ev = {"s0", "s1", "angle", "valid", "present", "snr"}   0.5 s 창, 0.25 s 이동
  output(now)  now = 지금까지 받은 PCM의 마지막 샘플 번호 → ("none", None) | ("drone", θ°) | ("unknown", None)

규칙
  1. 판정: 받은 분류 창을 s1 순서로 두고 최근 CONFIRM_N개 중 CONFIRM_K개 이상 positive면 드론 (Step8의 3창 중 2창과 같음).
     도착 순서가 아니라 s1(창이 끝난 샘플)로 줄 세운다 → 늦게 온 결과도 제 시각에 들어간다.
  2. 판정 경과 시간: 가장 최근 분류 창의 s1이 now보다 CLS_MAX_AGE 넘게 오래되면 판정을 모른다 → "unknown".
     (정상일 때 경과 시간 = 창 이동 0.5 s + PC 추론 지연. PC가 멈추면 마지막 "드론"이 계속 남는 것을 막는다)
  3. 방위: valid이고 present인 방향 창 중 s1이 now − DOA_MAX_AGE 이후인 것만, 원형 중앙값.
     없으면 드론이어도 "unknown" (방향 없이 카메라를 돌릴 수 없다). 무효·오래된 방위는 쓰지 않는다 (I4).
  4. 드론이 아니고 판정이 신선하면 "none".
"""
import numpy as np

CONFIRM_N, CONFIRM_K = 3, 2     # 최근 분류 창 3개 중 2개 positive → 드론
CLS_MAX_AGE = 1.0               # [s] 가장 최근 분류 창 끝이 이보다 오래되면 판정 모름
DOA_MAX_AGE = 0.75              # [s] 이보다 오래된 방향 창은 버림 (0.25 s 이동이라 정상이면 창 3개)


def circ_median(deg):
    """원형 중앙값: 다른 점들까지 각도 거리 합이 가장 작은 점"""
    a = np.asarray(deg, dtype=float)
    d = np.abs((a[:, None] - a[None, :] + 180) % 360 - 180).sum(axis=1)
    return float(a[np.argmin(d)])


class Combiner:
    def __init__(self, fs=12500.0):
        self.fs = fs
        self.cls = []           # (s1, positive), s1 순서
        self.doa = []           # (s1, angle), valid·present인 것만

    def on_cls(self, ev):
        self.cls.append((ev["s1"], bool(ev["positive"])))
        self.cls.sort(key=lambda c: c[0])
        del self.cls[:-CONFIRM_N]

    def on_doa(self, ev):
        if ev["valid"] and ev["present"]:
            self.doa.append((ev["s1"], float(ev["angle"])))

    def output(self, now):
        if not self.cls or now - self.cls[-1][0] > CLS_MAX_AGE * self.fs:
            return ("unknown", None)
        if sum(p for _, p in self.cls) < CONFIRM_K:
            return ("none", None)
        lo = now - DOA_MAX_AGE * self.fs
        self.doa = [d for d in self.doa if d[0] >= lo]
        if not self.doa:
            return ("unknown", None)
        return ("drone", circ_median([a for _, a in self.doa]))
