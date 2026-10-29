---
name: project-next-steps
description: "Turret progress (branch four-mic, 2026-10-29 night): 4-mic board pipeline done & matches PC; remaining task list in priority order, pending confirmations"
metadata:
  node_type: memory
  type: project
  modified: 2026-10-29T14:41:25.141Z
  originSessionId: 22b71e3d-c38f-4a45-b943-59b7839e02f2
---

**브랜치 `four-mic`**, 2026-10-29 밤 커밋·푸시.

**끝난 것 (2026-10-29, 집, 4마이크 하드웨어 장착)**
- 하드웨어: 정사면체(평면 70 mm, MIC4 높이 57 mm). 배선 MIC1 0°(새 마이크) A0 · MIC2 120° A1 · MIC3 −120° A5 · MIC4(위) A2 = PA4. ioc: ADC1 rank 2 = IN4, ADC2·3 rank 2 자리 채우기, USART2 1.5 Mbps.
- 펌웨어 4채널 수집 + FIR 256씩 4번(상태 13 KB → 5 KB) → 유실 0, 채널 매핑 확인(`ch4_map`, `ch4_check` 노트북). ch4 게인 −4.9 dB(평면 대비, 수용).
- doa.c 4채널(6쌍 PHAT + 3D 최소제곱, 결과 패킷 ver 4, 84 B). 호스트 시험 통과. 6쌍이 회전 계산 공유 → 마무리 10.2 → 6.1 ms, **CPU 최대 92 → 74 %** (목표 75 %, 여유 1 %p). 보드 = PC 확인(`doa4_check3`, compare_mcu 통과).
- `doa_compass.py` 하늘 지도(반지름 = 고도각). `stream_capture.py` 4채널·1.5 Mbps.
- 주의: compare_mcu는 녹음 시작 **뒤** B1로 배경을 배워야 비교 창이 생김. 펌웨어 바꾸면 Run ▶으로 다시 올릴 것(리셋만 하면 이전 펌웨어 — `doa4_check2`가 그 사례).

**남은 일 (우선순위)**
1. **채널 지연 다시 재기**: MIC1이 새 모듈, ch4 지연은 계산값(−1.78 µs)뿐. 방향을 아는 녹음 필요(하드웨어). config/geometry.json → doa.h.
2. **유효 문턱 재조정** (`시뮬레이션`): 6쌍 최소 봉우리 0.15 · 잔차 0.3샘플 · norm 0.5 ~ 1.3은 3마이크 값 그대로.
3. **4채널 고도 실측 → 노트북** (Step8e 기준은 제안 상태), 방향 T·고도 T 다시 잼.
4. **D8d-4 배경 갱신** PC 구현 → 기존 녹음 노트북 → 펌웨어. CPU 여유 1 %p라 펌웨어 넣기 전 절감 후보(상관 반복 메모리 배치 −6 %p, CRC 표 −2 %p, lrintf → vcvtr −1.5 %p, 추정) 먼저.
5. **Step8c 다시 쓰기** (4채널 고도각으로 감점 규칙).
6. **B0 MCU 이식** (f0 하한 80 Hz 제안).
7. 집 녹음: `fan_T_fpv`, `T2_mini3`, `servo_noise`.

**사용자 확인 대기**: problem.md "큐잉 센서" 문장, 노트북 v2.7 정리, 노트북 덮개 설정 되돌리기.

**Why:** 다음 세션이 바로 이어서 시작하도록. **How to apply:** 세션 시작 시 이 목록을 보여 주고 사용자에게 순서 확인. 관련: [[project-product-direction]], [[feedback-checks-go-in-notebook]].
