---
name: project-next-steps
description: "Turret progress (branch four-mic, 2026-10-29): what was done, hardware-free task list in priority order, pending confirmations"
metadata:
  node_type: memory
  type: project
  modified: 2026-10-28T22:38:48.554Z
  originSessionId: 22b71e3d-c38f-4a45-b943-59b7839e02f2
---

**브랜치 `four-mic`** (restructure-docs `6f701fe`에서 분기). 2026-10-29 저녁에 커밋. 푸시 안 함.

**한 일 (2026-10-28 ~ 29, 집)**
- 방향 T 재분석: 올바른 배경 T90 12.4 dB, 배경 없음 17.0 dB, 보드(틀린 배경) 24.3 dB, 고조파 칸만 투표는 악화 (`doa_bg_real`, `doa_mask_real` 노트북) → D8d-4 (배경 계속 갱신 + 드론 판정·모터 구동 중 멈춤 + 모터 명령 블랭킹). 펌웨어 미반영.
- 평면 3마이크 고도 실측 실패 (`elev_real`: 6.8 · 12.4 · 23.7°에서 오차 +28 ~ +43°) → D8c-2: 평면 밖 4번째 마이크. 사용자가 **정사면체(중심 위 57.2 mm, 모든 쌍 70 mm)로 확정**. D4-3 수정, Step8e 신설.
- PC 기준 `Tools/doa/doa4.py` (6쌍 PHAT + 3D 최소제곱, selftest 통과). 합성 시뮬레이션(스크래치, 결과는 Step8e에 요약): 4마이크는 땅(0°)을 하늘로 오인 0 ~ 0.7 %, 3마이크 18 ~ 99 %. 배율 오차 무관. 가장 큰 위험은 땅 반사 (낮은 설치 0.5 m에서 20° → 6.5°).
- 아티팩트 [4마이크 고도각 설계](https://claude.ai/artifact/NxT85gJt9JC3VXvaKUp5yA) (비공개).
- USART2 상한 2.8125 Mbps (APB1 45 MHz ÷ 16) → 4채널 100 kB/s 문제 아님. 1.5 Mbps는 분주 오차 0.
- `stream_capture.py`가 같은 라벨 덮어쓰기를 거부함.

**하드웨어(4번째 마이크) 없이 할 수 있는 일** (2026-10-29 정리, 위에서부터 우선) — 사용자 순서: PC 시뮬레이션 → 평가 → MCU 이식 → 실측
1. **4마이크 유효 검사 문턱 다시 정하기** (`시뮬레이션`, 노트북 없음): 6쌍 최소 봉우리·최소제곱 잔차·norm 범위. 시뮬레이션에서 SNR 6 dB 유효율 79 %(3마이크 92 %)로 검사가 더 엄격했음. 이 문턱으로 방향 T·고도 T(땅/하늘 90 % SNR)를 예측. 스크립트 원본은 지난 세션 스크래치 `sim_elev4.py`(남아 있지 않으면 doa4.py + eval_doa_synth.py로 다시 작성).
2. **doa.c 4채널 이식 + 호스트 시험**: 6쌍 PHAT + 3D 최소제곱(doa4.py 이식). `Tools/doa/hosttest`·`test_doa_host.py`로 PC에서 C 코드를 돌려 doa4.py와 결과 일치 확인 (I3). RAM 계산 (남은 여유 약 18 KB였음).
3. **펌웨어 4채널 수집 (빌드까지, 사용자 확인 후 시작)**: PA4(Arduino A2, ADC12_IN4)를 ADC1 rank 2로. 삼중 동시 모드라 ADC2·3도 rank 2(자기 채널 반복) → 트리거당 6값 중 4개. rank 2는 1.78 µs 늦음((28+12) ÷ 22.5 MHz) → channel_delay_us로 보정. fs 12.5 kHz 그대로 (TIM2 50 kHz → FIR ↓4). FIR 4채널, STREAM 패킷 4채널, USART2 1.5 Mbps. 4번째 핀이 비어 있어도 빌드·플래시·전송 시험은 가능.
4. **PC 도구 4채널**: `stream_capture.py` 4채널 패킷 + `--baud`, `doa_compass.py`에 고도각 표시.
5. **D8d-4 배경 갱신**: PC 기준 구현(천천히 갱신 + 판정·구동 중 멈춤) → 기존 녹음(`T2_fpv`, `fan_10min`)으로 확인 = 실측이라 **노트북** (GUIDE v2.7: 그림은 결론부에만) → 펌웨어 반영.
6. **Step8c 다시 쓰기**: 감점 규칙의 "낮은 고도"를 4채널 고도각으로. 기존 데이터로 정지 판정 확인(`fan_10min`, Step7 12방향 = 노트북), 추적 KF 2상태 Python 구현(`phone_rot_try1`로 확인).
7. **B0 MCU 이식**: f0 하한 40 → 80 Hz 제안(보드 48.8 Hz·60 Hz 줄 오탐), RAM.
8. **문서**: Step8e 기준에 방향 T·고도 T 재측정 추가, parameter.json에 4마이크 반영, 노트북 3개 v2.7 정리(사용자 확인 시).

**판정 T(B0, ch1 하나) ≈ 0 dB는 4마이크에서도 유지. 방향 T(3마이크 12 ~ 17 dB 예상)는 4마이크로 다시 잼** (유효 검사·쌍 수·배경 처리가 바뀜). 4번째 마이크 장착은 마지막 실측 때만: M3 서포트 약 57 mm(25 + 20 + 12) 추천, 위치 오차 σ 3 mm까지 괜찮음(시뮬레이션), 아래로 매달아도 됨.

**집 녹음 남은 것** (docs/run.md "집 녹음 묶음"): `fan_T_fpv`(선풍기 + FPV 단계), `T2_mini3`, `servo_noise`(부품 있으면). 회전·3마이크 고도 녹음은 끝(더 안 함). 4마이크 하드웨어 뒤에 고도 녹음 다시.

**사용자 확인 대기**
- problem.md에 "음향 = 카메라 큐잉 센서, 유인기는 카메라 판별" 문장 반영 여부 (제안만 함).
- 오늘 노트북 3개(`doa_mask_real`, `doa_bg_real`, `elev_real`)는 중간 절에도 그림이 있어 GUIDE v2.7(그림은 결론부에만)에 안 맞음 — 손볼지.
- 노트북 덮개 닫힘 동작을 "아무것도 안 함"으로 바꿔 둔 것 되돌릴지.

**Why:** 다음 세션(싸피 PC)이 바로 이어서 시작하도록. **How to apply:** 세션 시작 시 이 순서를 보여 주고, 1번(펌웨어 4채널)은 사용자 확인 후 시작. 관련: [[project-product-direction]], [[feedback-checks-go-in-notebook]].
