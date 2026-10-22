---
id: Step5pre
title: 사전 측정 — 공개 원음 선정과 고조파 구조, 재생 경로
depends_on: [Step4]
goal_ref: [G2, I5]
exit: "공개 원음의 고조파 구조로 쓸 대역 f_use와 ↓4/↓2를 정하고, 노트북 스피커 재생 → 장치 녹음에서 FPV 고조파가 남는지 확인"
on_fail: null
status: {impl: 통과, explain: 0/2}
---

## 질문
어떤 원음을 쓰고, 어느 대역까지 남겨야 하며, 스피커로 재생해도 쓸 만한가?

## 최종 목표와의 연결
- G2: 학습 분류의 양성 원음 목록과 장치 대역(f_use)이 여기서 정해졌다.
- I5: 실제 FPV 녹음이 없어 모든 결과가 "재생음 조건"이 되는 출발점이다.

## 통과 기준 (Roadmap 4.5 v0.2, 2026-10-14 확정)
| 항목 | 기준 | 측정 조건 |
|---|---|---|
| 고조파 구조 | 원본과 장치 녹음 각각의 f0 범위, 고조파 수, 선 폭, 에너지 상한이 숫자로 나옴 | 공개 원음 + burst 재생 녹음 |
| 결정 | f_use, ↓4 / ↓2, 재생 조건, 원음 목록 확정 | — |

## 결과
| 항목 | 실측 | 판정 | 날짜 | 근거 |
|---|---|---|---|---|
| 고조파 선 위치 | 모든 기체에서 약 2 kHz 아래 (FPV는 4번째 고조파 약 2.1 kHz까지), 선 에너지 99%는 6 kHz 아래 | 통과 | 2026-10-14 | [harmonics.md](../reports/step5/harmonics.md) |
| 재생 경로 | FPV 고조파는 원본 4개 중 장치에서 3개 남음. 노트북 스피커는 270 Hz 아래가 약함 | 통과 | 2026-10-16 | [playback.md](../reports/step5/playback.md) |
| FPV 음압 | DJI FPV 15 m/s 통과·고도 10 m에서 LAFmax 59–61 dBA → 1 m 환산 약 80 dBA (보정기 94 dB 가정). Mini 3 Pro 47–50 dBA, 호버 51–53 dBA, 배경 21–23 dBA | 기록 | 2026-10-18 | [logs/Step5pre.md](logs/Step5pre.md) |
| FPV 빗 | 로터마다 회전수가 달라 4번째 차수 위로 흐트러짐 | 기록 | 2026-10-14 | harmonics.md |

## 파라미터
| 이름 | 현재 값 | 근거 |
|---|---|---|
| f_use | 5 kHz | [D5pre-2](../decisions.md) |
| 처리 속도 | 50 → 12.5 kHz (↓4) | D5pre-2 |
| 원음 | Salford DroneNoise(전체), Western Sydney DJI Air 3 → `DataSet/` (git 제외) | [D5pre-1](../decisions.md) |

원음 후보 표와 FPV 추가 출처 조사는 [logs/Step5pre.md](logs/Step5pre.md).

## 의존 개념
| ID | 개념 | 판정 |
|---|---|---|
| S2 | dB, RMS, 전력 | ❌ △ |
| E4 | 고조파 점수와 f0/Δf | 미진단 |

## 남은 일
- 없음. 장치 음압 보정 측정은 [problem.md](../problem.md) 열린 결정에 있다.

## 관련 결정
- D4.5-1, D5pre-1, D5pre-2 (decisions.md)
