"""Step8c 방위 추적 KF (2상태). doa.c가 0.25 s마다 내는 방위를 받아 방위와 각속도를 추정한다.

    상태  x = [θ, ω]        θ = 방위 [deg], ω = 각속도 [deg/s] (반시계 +, doa.h와 같은 각도 규칙)
    모델  θ ← θ + ω·Δt,  ω ← ω          등각속도. 모델이 틀릴 수 있는 정도는 Q (아래)
    측정  z = θ + 잡음 (분산 R)          VALID이고 PRESENT인 방위만 측정으로 쓴다 (I4)

    한 주기의 계산 (step):
      1) 예측   x ← F·x,  P ← F·P·Fᵀ + Q            측정이 없어도 매 주기 한다 → P(불확실성)가 커진다
      2) 혁신   y = wrap(z − θ_pred)                 ±180°에서 이어지게 각도 차이를 감싼다
               S = P[0,0] + R                       혁신의 분산 (예측 불확실성 + 측정 잡음)
      3) 관문   y² / S > GATE² 이면 측정을 버린다    예측에서 너무 벗어난 값 (반사·다른 음원)
      4) 갱신   K = P·Hᵀ / S,  x ← x + K·y,  P ← (I − K·H)·P
               K[0]: 방위를 측정 쪽으로 얼마나 당길지, K[1]: 그 차이로 각속도를 얼마나 고칠지
      5) 놓기   이번 주기에 갱신을 못 했고(측정 없음·관문에서 버림) √P[0,0] > LOST_DEG 이면 추적을 놓는다
               (갱신한 주기는 P가 줄어든 직후라 보지 않는다. 시작 직후는 각속도를 몰라 P가 빨리 커지므로 기준을 30°로)

    Q (과정 잡음): 이산 백색 가속도 모델. 매 주기 각속도가 σa·Δt 정도 무작위로 바뀔 수 있다고 본다.
        Q = σa² · [[Δt⁴/4, Δt³/2], [Δt³/2, Δt²]]
        σa [deg/s²] 크면: 급한 움직임을 잘 따라가지만 측정 흔들림도 더 따라간다
    R (측정 잡음): 방위 측정의 분산 = σz² [deg²]. Step7 고정 음원 흔들림 2 ~ 4°에서 출발값을 잡는다.

    σa, σz의 값은 아직 확정 전이다 (Step8c, 학습 지침 T3 점검 뒤 정한다). 여기 기본값은 자리만 채운 출발값.
"""
import math

import numpy as np

DT = 3072 / 12500.0              # doa.h DOA_HOP / DOA_FS = 0.246 s (방위 결과 주기)
SIGMA_A = 30.0                   # [deg/s²] 출발값, 미확정
SIGMA_Z = 3.0                    # [deg] 출발값, 미확정 (Step7 흔들림 2 ~ 4°)
GATE = 3.0                       # 혁신이 이 표준편차 배수를 넘으면 버림
LOST_DEG = 30.0                  # 측정 없이 예측만 한 주기에서 방위 표준편차가 이보다 크면 추적을 놓음
P0_OMEGA = 90.0                  # [deg/s] 시작할 때 각속도 불확실성 (모름 → 크게)


def wrap(deg):
    """각도를 −180 ~ 180으로"""
    return (deg + 180.0) % 360.0 - 180.0


class AngleKF:
    def __init__(
        self,
        sigma_a=SIGMA_A,         # 과정 잡음: 각가속도 흔들림 [deg/s²]
        sigma_z=SIGMA_Z,         # 측정 잡음: 방위 측정 표준편차 [deg]
        gate=GATE,               # 관문 [표준편차 배수]
        lost_deg=LOST_DEG,       # 놓는 기준 [deg]
    ):
        self.sigma_a, self.R, self.gate, self.lost = sigma_a, sigma_z ** 2, gate, lost_deg
        self.x = None            # 상태 [θ, ω]. None = 추적 중이 아님
        self.P = None            # 공분산 2×2
        self.t = None            # 마지막으로 예측한 시각 [s]

    def _Q(self, dt):
        q = self.sigma_a ** 2
        return q * np.array([[dt ** 4 / 4, dt ** 3 / 2], [dt ** 3 / 2, dt ** 2]])

    def predict(self, t):
        """시각 t까지 예측만 한다 (측정 없음)"""
        dt = t - self.t
        if dt <= 0:
            return
        F = np.array([[1.0, dt], [0.0, 1.0]])
        self.x = F @ self.x
        self.x[0] = wrap(self.x[0])
        self.P = F @ self.P @ F.T + self._Q(dt)
        self.t = t

    def step(
        self,
        t,                       # 이 방위 결과의 시각 [s] (창 끝 샘플 번호 ÷ 12,500)
        z=None,                  # 측정 방위 [deg]. VALID·PRESENT가 아니면 None (예측만)
    ):
        """한 주기 처리 → 결과 dict. status: idle(추적 없음) / start / update / reject(관문에서 버림) / coast(측정 없음) / lost"""
        if self.x is None:
            if z is None:
                return dict(t=t, status="idle")
            self.x = np.array([wrap(z), 0.0])
            self.P = np.diag([self.R, P0_OMEGA ** 2])
            self.t = t
            return self._out(t, "start", z)
        self.predict(t)
        status = "coast"
        if z is not None:
            y = wrap(z - self.x[0])
            S = self.P[0, 0] + self.R
            if y * y / S > self.gate ** 2:
                status = "reject"
            else:
                K = self.P[:, 0] / S                       # H = [1, 0] 이라 P·Hᵀ = P의 첫 열
                self.x = self.x + K * y
                self.x[0] = wrap(self.x[0])
                self.P = self.P - np.outer(K, self.P[0, :])  # (I − K·H)·P
                status = "update"
        if status != "update" and math.sqrt(self.P[0, 0]) > self.lost:
            out = self._out(t, "lost", z)
            self.x = self.P = None
            return out
        return self._out(t, status, z)

    def _out(self, t, status, z):
        return dict(t=t, status=status, z=z, theta=float(self.x[0]), omega=float(self.x[1]),
                    sd_theta=float(math.sqrt(self.P[0, 0])), sd_omega=float(math.sqrt(self.P[1, 1])))


def track(
    times,                       # 방위 결과 시각들 [s]
    angles,                      # 측정 방위 [deg], 쓸 수 없는 창은 NaN
    **kw,                        # AngleKF 인자 (sigma_a, sigma_z, gate, lost_deg)
):
    """방위열 전체를 차례로 넣어 결과 목록을 돌려준다 (녹음·합성 시험용)"""
    kf = AngleKF(**kw)
    return [kf.step(t, None if (a is None or np.isnan(a)) else float(a)) for t, a in zip(times, angles)]
