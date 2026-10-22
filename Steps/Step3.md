---
id: Step3
title: GCC-PHAT 방향 추정 — Python 프로토타입, MCU 이식, 결과 비교
depends_on: [Step2]
goal_ref: [G1, I3]
exit: "(사후 정리) 덤프 원파형으로 쌍별 TDOA와 방향을 Python으로 구하고, 같은 계산을 MCU(CMSIS-DSP)로 옮겨 같은 캡처에서 두 결과를 자동 비교, MCU 계산 시간이 프레임 주기 안"
on_fail: null
status: {impl: 통과, explain: 0/8}
---

## 질문
스냅(순간음)의 방향을 Python과 MCU가 같은 값으로, 프레임 주기 안에 계산하는가?

## 최종 목표와의 연결
- G1: GCC-PHAT + LSE가 Step7 지속음 방향 추정(D1)의 기반이다. 스냅 경로는 회귀 확인용으로 남는다.
- I3: MCU와 PC가 같은 상수로 같은 결과를 내는 비교 방식을 처음 세웠다.

## 통과 기준 (확정일 기록 없음 — 원문 "이 단계의 목표"를 사후에 옮김)
| 항목 | 기준 | 측정 조건 |
|---|---|---|
| MCU = PC | 같은 캡처에서 지연·피크·각도 차이 0 | `doa_live.py` 비교 |
| 계산 시간 | 프레임 주기 20.48 ms 안 | DWT `proc_us` |

## 결과
| 항목 | 실측 | 판정 | 날짜 | 근거 |
|---|---|---|---|---|
| MCU 대 PC | 캡처 63개(31 + 32), 지연·피크·각도 차이 0 | 통과 | 2026-10-11 | [logs/Step3.md](logs/Step3.md) |
| 계산 시간 | `-O0` 18.6 ms → `-Ofast` 3.3 ms (16%) | 통과 | 2026-10-11 | logs/Step3.md |
| 같은 자리 반복 정밀도 | 표준편차 1.3° (스냅) | 기록 | 2026-10-11 | logs/Step3.md |
| 신뢰 판정 통과 비율 | 235개 중 220개 (94%), MCU·PC 판정 15/15 일치 | 기록 | 2026-10-11 | logs/Step3.md |
| 정확도 (실제 방향 대비 치우침) | — | 미측정 | — | — |
| 대역 150~2000 Hz 변경 후 보드 MCU = PC | — | 미측정 | — | — |
| 메모리 | 플래시 143.8 KB / RAM 50.7 KB (`-O2`), `-Ofast`는 미측정 | 기록 | 2026-10-11 | [build_analyze](../reports/step3/build_analyze.png) |

## 파라미터 (기준선 `baseline-v1` 이후 대역만 변경)
| 이름 | 현재 값 | 근거 |
|---|---|---|
| 대역 | 150~2000 Hz (실제 195~1953 Hz) | [D3-1](../decisions.md) |
| 분석 구간 / onset 전 여유 | 250샘플(5 ms) / 50샘플(1 ms), Tukey | 이전 판 5.1절 비교 |
| FFT / 최대 지연 | 512점 / ±13샘플 | 7 cm 최대 지연 10.2샘플 + 여유 |
| PHAT ε | 0.01 (대역 내 최대 크기 대비) | 신호 없는 빈 억제 |
| 보간 | 포물선 | [D3-2](../decisions.md) |
| 신뢰 판정 | peak ≥ 0.5, 0.3 ≤ norm ≤ 1.2 | [D3-5](../decisions.md) |

MCU·Python 상수 대응표는 [docs/firmware.md](../docs/firmware.md), 실행 명령은 [docs/run.md](../docs/run.md).

## 의존 개념
| ID | 개념 | 판정 |
|---|---|---|
| F1 | DFT bin, 주파수 해상도, zero-padding | ❌ △ |
| F2 | 시간 지연 ↔ 위상 | ❌ △ ⚠ |
| F3 | 상관 정리, GCC-PHAT | ❌ △ |
| T1 | 배열 기하, 최대 지연, 공간 앨리어싱 | ❌ △ |
| T2 | 평면파 가정과 최소제곱, norm | ❌ |
| E3 | 닫힘(closure) 일관성 | ❌ |
| F4 | 정밀도 식 (β·√K) | 미진단 |
| F5 | 서브샘플 포물선 보간 | 미진단 |

## 남은 일 (스냅 경로 — [D4.5-4](../decisions.md)에 따라 비교 기준이 아니라 회귀 확인용)
- [ ] 대역 변경을 보드에서 확인 (원파형 모드, MCU = PC) → 맞으면 `baseline-v2` 태그
- [ ] 기준선 정확도: 각도를 아는 위치에서 `--truth` 세션
- [ ] `-O0` 병목 확인: ① `Drivers/CMSIS/DSP`만 `-Ofast` ② 단계별 DWT. 예측을 먼저 적고 잴 것
- [ ] 신뢰 판정 숫자(peak 0.5, norm 0.3 / 1.2) 직접 결정. 위쪽 소리(낮은 norm) 표본 수집
- [ ] holdoff 직후 꼬리에서 잡힌 결과 확인 (원파형 모드, holdoff 10, 표본 2개뿐)
- [ ] 손으로 다시 짜기 2차 (ADC-DMA → capture/dump → tdoa 핵심부, 한 번에 한 모듈). 10-25까지 착수
- [ ] (선택) FFT 계수 표를 필요한 크기만 남겨 플래시 절약 (`ARM_DSP_CONFIG_TABLES`), `-Ofast` 플래시/RAM 기록
- [ ] 정리: `dumps` 바로 아래 이전 캡처 160개, Release 구성의 절대경로 include, Drivers 추적 범위(DSP만 남길지)

## 관련 결정
- D3-1 ~ D3-6 (decisions.md)
