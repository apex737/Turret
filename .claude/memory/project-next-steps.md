---
name: project-next-steps
description: "Turret progress as of 2026-10-29 end of day (branch four-mic): what was done, what to do next at SSAFY (firmware 4ch), pending confirmations"
metadata:
  node_type: memory
  type: project
  modified: 2026-10-28T15:24:07.375Z
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

**다음 (싸피, 녹음 없이)** — 사용자 순서: PC 시뮬레이션 → 평가 → MCU 이식 → 실측
1. 펌웨어 4채널화 (아직 시작 전, 사용자 확인 필요): 4번째 마이크 PA4(Arduino A2, ADC12_IN4)를 ADC1 rank 2로. 삼중 동시 모드라 ADC2·3도 rank 2(자기 채널 반복)로 맞춤 → 트리거당 6값 중 4개 사용. rank 2는 1.78 µs 늦음((28+12) ÷ 22.5 MHz) → channel_delay_us로 보정. fs 12.5 kHz 그대로 (TIM2 50 kHz → FIR ↓4).
2. USART2 1.5 Mbps, `stream_capture.py` 4채널 패킷 + `--baud`.
3. `doa.c`에 6쌍 + 3D 최소제곱 (doa4.py 이식), RAM 확인 (남은 여유 약 18 KB였음).
4. Step8c 감점 규칙의 "낮은 고도"를 4채널 고도각으로 다시 쓰기. D8d-4 배경 갱신 펌웨어 반영. B0 MCU 이식.

**집 녹음 남은 것** (docs/run.md "집 녹음 묶음"): `fan_T_fpv`(선풍기 + FPV 단계), `T2_mini3`, `servo_noise`(부품 있으면). 회전·3마이크 고도 녹음은 끝(더 안 함). 4마이크 하드웨어 뒤에 고도 녹음 다시.

**사용자 확인 대기**
- 커밋에서 뺀 삭제 3개: `Tools/notebooks/doa_mask_phat.ipynb`, `kf_synth.ipynb`, `learning/notes/RefrencePaper.pdf` — 일부러 지운 것인지.
- problem.md에 "음향 = 카메라 큐잉 센서, 유인기는 카메라 판별" 문장 반영 여부 (제안만 함).
- 오늘 노트북 3개(`doa_mask_real`, `doa_bg_real`, `elev_real`)는 중간 절에도 그림이 있어 GUIDE v2.7(그림은 결론부에만)에 안 맞음 — 손볼지.
- 노트북 덮개 닫힘 동작을 "아무것도 안 함"으로 바꿔 둔 것 되돌릴지.

**Why:** 다음 세션(싸피 PC)이 바로 이어서 시작하도록. **How to apply:** 세션 시작 시 이 순서를 보여 주고, 1번(펌웨어 4채널)은 사용자 확인 후 시작. 관련: [[project-product-direction]], [[feedback-checks-go-in-notebook]].
