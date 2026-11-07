# Tools/.venv
"""Step8c 움직임·고도 감점: 고정된 지면 회전 기계(선풍기·엔진)의 고조파 점수를 깎는다 (D8c-1, 스피드런 2026-11-04).

방향 결과(0.246 s마다)를 넣으면 창마다 감점 여부를 낸다.
  1) 정지 판정: 최근 WIN_S(3 s) 동안의 유효 방위에 직선을 맞춘 기울기 |ω| ≤ OMEGA_MAX(3°/s)이면 정지.
     방위는 가장 최근 값 기준으로 ±180° 안에 감아 이어 붙이고, 원형 중앙값에서 OUTLIER_DEG(30°) 넘게 벗어난 점(반사·다른 음원)은 뺀다.
     점이 MIN_PTS(6)개 미만이면 판정 안 함(정지 아님).
  2) 고도: 같은 3 s의 고도각 중앙값 < ELEV_EDGE(5°)이면 낮음. 고도각이 없는 녹음(평면 3마이크)은 낮음으로 본다 (구분 못 함).
  3) 고도각을 잰 소리(4채널)가 낮으면 후보에서 뺀다: 점수 = 0. 움직임과 상관없다 (사용자 결정 2026-11-05, 목표 고도 20 ~ 40°로 넓힘 2026-11-07).
     고도각이 없는 녹음(평면 3마이크)은 예전 규칙: 정지가 HOLD_S(3 s) 넘게 이어지면 고조파 점수 × PENALTY(½).
Step8c 통과 기준(정지 판정 95%, 선풍기 감점 ≥ 80%, 높이 있는 정지 음원 감점 ≤ 5%)의 숫자는 eval_motion.py가 잰다.
ELEV_EDGE 5° (2026-11-07, 10° → 5°): 보드가 실제 21.8° 음원을 약 9° 낮게 읽어서, 10°면 그 음원의 26.6 %를 땅 위로 보고 뺐다.
  5°면 2.0 %만 빠진다. 대가로 땅 위(0°) 음원을 거르는 비율이 69.2 % → 51.3 %로 줄어든다
  (acc 녹음 60개, 보드가 유효로 낸 창의 3 s 고도 중앙값 기준, reports/accuracy/acc_windows.csv).
"""
import numpy as np

WIN_S = 3.0            # [s] 정지 판정 회귀 길이 (Step8c: σ 3°, 0.25 s 간격 → 2.3 s, 창 50% 겹침 → 3 s)
OMEGA_MAX = 3.0        # [deg/s] 이하면 정지 (Step8c 기준)
MIN_PTS = 6            # 회귀에 필요한 최소 유효 방위 수 (3 s에 최대 12개)
OUTLIER_DEG = 30.0     # 원형 중앙값에서 이보다 먼 방위는 회귀에서 뺀다
ELEV_EDGE = 5.0        # [deg] 고도각 중앙값이 이보다 작으면 "낮음" (목표 20 ~ 40°, 2026-11-07 acc 녹음으로 정함)
HOLD_S = 3.0           # [s] 정지·낮음이 이만큼 이어져야 감점
PENALTY = 0.5          # 감점 배율 (D8c-1: 깎되 버리지 않는다)


def wrap(d):
    return (np.asarray(d, float) + 180.0) % 360.0 - 180.0


def circ_median(a):
    a = np.asarray(a, float)
    d = np.abs(wrap(a[:, None] - a[None, :])).sum(axis=1)
    return float(a[np.argmin(d)])


class MotionGate:
    def __init__(self, win_s=WIN_S, omega_max=OMEGA_MAX, min_pts=MIN_PTS, elev_edge=ELEV_EDGE, hold_s=HOLD_S):
        self.win_s, self.omega_max, self.min_pts, self.elev_edge, self.hold_s = win_s, omega_max, min_pts, elev_edge, hold_s
        self.pts = []          # (t, angle, elev or None) 유효 방위만
        self.since = None      # 정지·낮음이 시작된 시각

    def reset(self):
        """입력이 끊겼을 때 (재시작·통신 단절): 이어 붙이면 안 되는 과거를 버린다 (I4)"""
        self.pts, self.since = [], None

    def update(
        self,
        t,                     # 이 방향 창의 시각 [s] (창 끝 샘플 ÷ 12,500)
        angle=None,            # 방위 [deg]. 유효·present가 아니면 None
        elev=None,             # 고도각 [deg]. 4채널이 아니면 None
    ):
        """한 창 → dict(omega, n, stationary, elev_med, low, penalize)"""
        if angle is not None:
            self.pts.append((t, float(angle), None if elev is None else float(elev)))
        self.pts = [p for p in self.pts if p[0] > t - self.win_s]
        out = dict(t=t, omega=float("nan"), n=len(self.pts), stationary=False, elev_med=float("nan"), low=True, penalize=False, drop=False)
        if len(self.pts) >= self.min_pts:
            tt = np.array([p[0] for p in self.pts])
            aa = np.array([p[1] for p in self.pts])
            med = circ_median(aa)
            rel = wrap(aa - med)
            keep = np.abs(rel) <= OUTLIER_DEG
            if keep.sum() >= self.min_pts:
                slope = float(np.polyfit(tt[keep], rel[keep], 1)[0])
                out["omega"] = slope
                out["stationary"] = abs(slope) <= self.omega_max
            ev = [p[2] for p in self.pts if p[2] is not None]
            if ev:
                out["elev_med"] = float(np.median(ev))
                out["low"] = out["elev_med"] < self.elev_edge
                out["drop"] = out["low"]                     # 고도각을 잰 낮은 소리 → 후보에서 뺌
        if out["stationary"] and out["low"]:
            if self.since is None:
                self.since = t
            out["penalize"] = t - self.since >= self.hold_s
        else:
            self.since = None
        return out


def penalized_score(score, gate_out):
    """B0 점수에 규칙을 적용한다: 고도각을 잰 낮은 소리면 0 (후보에서 뺌), 고도각 없이 정지·낮음이 이어지면 × ½"""
    if gate_out.get("drop"):
        return 0.0
    return score * PENALTY if gate_out["penalize"] else score
