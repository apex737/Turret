# 개념 지도 — Turret

> 진단: 2026-10-21 · 근거: [quiz.md](quiz.md) 28문항 (문서·AI 없이 풂). 2026-10-22 문서 구조 개편 때 Step 문서에서 개념 9개를 더 뽑아 "미진단"으로 추가했다.
> 이 문서는 지식을 설명하지 않는다. 어느 Step이 어느 개념 위에 서 있는지와 판정만 적는다. 학습 방식은 [GUIDE.md](GUIDE.md).

판정: ✅ Pass (핵심 이유를 맞게 설명) · ❌ Fail · △ 근접 (Fail이지만 절반 이상) · ⚠ 확신 오류 (확신 상·중으로 틀림, 가장 먼저 고친다) · 미진단

## 1. 요약

| | 개념 | ✅ | △ | ❌ | ⚠ | 미진단 |
|---|---|---|---|---|---|---|
| 개수 | 39 (진단 30 + 미진단 9) | 3 | 10 | 17 | 5 (다른 칸과 겹침) | 9 |

- Fail의 절반 이상은 학부 신호 및 시스템 / DSP 기초(샘플링과 접힘, 푸리에 변환의 성질, FIR 필터)와 학부 머신러닝 평가 기초(누수, 문턱, AUC)다. 대학원에 가까운 것은 배열 신호처리(T1~T3, E2)뿐이고 그것도 위 기초 위에 있다.
- Step3가 병목이다. 스냅 파이프라인을 돌릴 수 있지만 설명할 수 있는 상태는 아니다. Step4·5·7이 같은 개념을 다시 쓴다.
- Step9A·10은 수학이 거의 필요 없는데 전부 모름이다. 다음 작업이라 따로 빠르게 메운다 (4절 트랙 A).

## 2. 단계별 의존 개념

설명 가능도 = ✅ 개수 / 전체. 각 Step 파일 frontmatter의 `explain`과 같다.

| 단계 | 의존 개념 | 설명 가능도 |
|---|---|---|
| Step1 | S1 ❌⚠ · R1 ✅ · R6 ❌⚠ · T0 | 1 / 4 |
| Step2 | R2 ✅ · S2 ❌△ · E1 ❌ · S3 · L1 · L2 | 1 / 6 |
| Step3 | F1 ❌△ · F2 ❌△⚠ · F3 ❌△ · T1 ❌△ · T2 ❌ · E3 ❌ · F4 · F5 | 0 / 8 |
| Step4 | S1 ❌⚠ · F1 ❌△ · F2 ❌△⚠ · C2 ❌ · C1 ❌ · C4 ❌ · F4 · E4 · E5 · T4 | 0 / 10 |
| Step5pre | S2 ❌△ · E4 | 0 / 2 |
| Step5 | R1 ✅ · R2 ✅ · R6 ❌⚠ · C1 ❌ · C2 ❌ · C3 ❌△ · N1 ❌ · R3 ❌⚠ | 2 / 8 |
| Step6 | M1 ❌⚠ · M2 ✅ | 1 / 2 |
| Step7 | F3 ❌△ · T1 ❌△ · T2 ❌ · T3 ❌ · E2 ❌△ · E3 ❌ · C4 ❌ · S2 ❌△ · R3 ❌⚠ | 0 / 9 |
| Step8 | M1 ❌⚠ · M2 ✅ · M3 ❌△ · M4 ❌ · M5 ❌ · M6 ❌△ · C2 ❌ · S2 ❌△ | 1 / 8 |
| Step9A | I1 ❌ · I2 ❌ · M4 ❌ | 0 / 3 |
| Step10 | R2 ✅ · R6 ❌⚠ · R4 ❌ · R5 ❌ · I1 ❌ · I2 ❌ · N1 ❌ | 1 / 7 |
| Step9B | T1 ❌△ · T3 ❌ | 0 / 2 |
| Step11 | M1 ❌⚠ · M5 ❌ · M6 ❌△ | 0 / 3 |

선택 확장(문항 없음): Step13 카메라 I2, R5 · Step14 MCU 단독 분류 M3, N1, R4.

## 3. 개념 목록

출처는 처음 다룬 이전 문서의 절이다 (`FPV_Target` 브랜치). 이전 Step 문서의 개념 설명문은 옮기지 않았다.

| ID | 개념 | 판정 | 근거 문항 | 쓰이는 단계 | 선행 개념 | 출처 |
|---|---|---|---|---|---|---|
| S1 | 샘플링과 앨리어싱 (접힘 위치) | ❌ ⚠ | Q1 | 1, 3, 4 | — | Step1 0.4절 |
| S2 | dB, RMS, 전력 (AC RMS = 표준편차) | ❌ △ | Q4a | 2, 5pre, 7, 8 | — | Step2 5.2절 |
| S3 | ADC 눈금 LSB와 dBFS | 미진단 | — | 2 | — | Step2 5.2절, 7절 |
| F1 | DFT bin, 주파수 해상도, zero-padding | ❌ △ | Q5 | 3, 4, 7 | — | Step4 5.2절 |
| F2 | 시간 지연 ↔ 위상 (이동 성질, 선형 위상) | ❌ △ ⚠ | Q6 | 3, 4, 7 | — | Step4 2.1절 |
| F3 | 상관 정리, GCC-PHAT | ❌ △ | Q7 | 3, 7 | F1, F2 | Step3 4.2절 |
| F4 | 정밀도 식 σ_τ = σφ/(2π·β·√K), σθ ≈ (c/d)·√(2/3)·σ_τ | 미진단 | — | 3, 4 | F2 | Step1 0.5절, Step4 2절 |
| F5 | 서브샘플 포물선 보간 | 미진단 | — | 3 | F3 | Step3 4.3절 |
| T0 | TDoA 원리 (지연 = d·sinθ/c, 정면 민감·옆 둔감) | 미진단 | — | 1 | — | Step1 0.2절 |
| T1 | 배열 기하, 최대 지연, 공간 앨리어싱 | ❌ △ | Q8 | 3, 7, 9B | F2 | Step1 0.6절 |
| T2 | 평면파 가정과 최소제곱, norm | ❌ | Q9 | 3, 7 | T1 | Step3 4.4~4.5절 |
| T3 | 공통(확산) 잡음과 배경 빼기 | ❌ | Q19 | 7, 9B | F3, E2 | Step7 2절 |
| T4 | 고조파 음원의 공간 앨리어싱 조건 f0 < c/2d | 미진단 | — | 4 | T1 | Step4 5.7절 |
| E1 | EMA, 적응 문턱 | ❌ | Q4b·c | 2, 7 | S2 | Step2 5.5절 |
| E2 | 블록 평균과 SNR (코히어런트 평균) | ❌ △ | Q18 | 7 | F3, S2 | Step7 2절 |
| E3 | 닫힘(closure) 일관성 | ❌ | Q20 | 3, 7 | T2 | Step3 4.5절 |
| E4 | 고조파 점수 S(f0)와 f0/Δf | 미진단 | — | 4, 5pre | F1 | Step4 5.1~5.4절 |
| E5 | M-of-N 확정 (오탐·미탐 맞교환) | 미진단 | — | 4 | — | Step4 5.5절 |
| C1 | FIR 설계 (전이대역, 탭 수, 선형 위상, 군지연) | ❌ | Q11 | 4, 5, 7, 8 | F1, F2, C2 | Step4 4.3절 |
| C2 | 데시메이션 앨리어싱 | ❌ | Q10 | 4, 5, 8 | S1 | Step4 4.2절 |
| C3 | 블록 처리와 필터 상태 | ❌ △ | Q13 | 5, 7 | C1 | Step4 4.4절 |
| C4 | 공통 필터의 지연 상쇄, 채널 위상 일치 | ❌ | Q12 | 4, 5, 7 | F2, C1 | Step4 4.4절 |
| N1 | 수치 표현, 반올림, 비트 재현성 | ❌ | Q14 | 5, 10, 14 | C1 | Step5 2.2절 |
| L1 | C 배열 typedef·packed 구조체·_Static_assert | 미진단 | — | 2 | — | Step2 6.2~6.3절 |
| L2 | CRC 무결성 검사 | 미진단 | — | 2 | — | Step2 6.4절 |
| R1 | DMA 핑퐁 타이밍과 덮어쓰기 | ✅ | Q2a·b | 1, 5 | — | Step1 3.1절 |
| R2 | 통신 처리량 예산 | ✅ | Q3 | 2, 5, 10 | — | Step2 4절 |
| R3 | 클럭원과 정확도 | ❌ ⚠ | Q15 | 5, 7 | S1 | Step5 5절 |
| R4 | 실시간 마감, 최악 시간, 큐 | ❌ | Q27 | 10, 14 | R6, R2 | Step7 6절 |
| R5 | 고장 감지·무효화·복귀 | ❌ | Q28 | 10, 13 | R4, I2 | Step5 1절 |
| R6 | ISR과 main의 공유 변수 (임계 구역) | ❌ ⚠ | Q2c | 1, 5, 10 | R1 | Step1 4절 |
| M1 | 데이터 누수와 그룹 split | ❌ ⚠ | Q16 | 6, 8, 11 | — | Step6 2절 |
| M2 | 지름길 학습 | ✅ | Q17 | 6, 8 | — | Step6 2절 |
| M3 | 전이학습과 정규화 | ❌ △ | Q21 | 8, 14 | — | Step8 1절 |
| M4 | 문턱, 운용점, 오탐/시간 | ❌ | Q22 | 8, 9A, 11 | M1 | Step8 9절 |
| M5 | 불균형 지표, AUC, 소표본 불확실성 | ❌ | Q23 | 8, 11 | M4 | Step8 9절 |
| M6 | 도메인 이동 (장치 경로) | ❌ △ | Q24 | 8, 11 | M2, M3 | Step8 10절 |
| I1 | 공통 시간축 (샘플 번호) | ❌ | Q25 | 9A, 10 | — | Step5 1절 |
| I2 | 오래된 관측, 상태 기계 | ❌ | Q26 | 9A, 10, 13 | I1 | Roadmap 4.5.2 Step9A |


## 4. 보완 순서

트랙 A(다음 작업 Step9A·10을 막는 개념)와 트랙 B(Step3~8의 기초)를 나란히 간다. 문항별 채점과 고칠 점은 [quiz.md](quiz.md) 끝의 채점 절.

### 0단계 — ⚠ 확신 오류부터 (30분)
Q1 S1, Q2c R6, Q6a F2, Q15 R3, Q16 M1. 고칠 점 한 줄씩은 quiz.md 채점 절에 있다. 해당 문항을 다시 푼다.

### 트랙 A — Step9A·10용 (반나절)

| 순서 | 개념 | 볼 곳 | 다시 풀 문항 |
|---|---|---|---|
| A1 | I1 공통 시간축 | [docs/protocol.md](../docs/protocol.md) v3 "시간축", [Step9A](../Steps/Step9A.md) | Q25 |
| A2 | I2 오래된 관측, 상태 | [Step9A](../Steps/Step9A.md) "최종 목표와의 연결" 세 가지 | Q26 |
| A3 | R6 공유 변수 | [adc.c](../Core/app/src/adc.c) `adc_get_frame`, [docs/firmware.md](../docs/firmware.md) STREAM 코드 블록 표 | Q2c |
| A4 | R4 마감과 큐 | [logs/Step7.md](../Steps/logs/Step7.md) MCU CPU 표, [stream.c](../Core/app/src/stream.c) 링버퍼, [Step10](../Steps/Step10.md) 통과 기준 | Q27 |
| A5 | R5 고장·복귀 | [app.c](../Core/app/src/app.c) `on_stream_frame`의 `RESYNC`/`GAP`, Step10 고장 주입 | Q28 |

### 트랙 B — 신호처리 기초 → 방향 추정 → 학습

| 순서 | 개념 | 저장소 안 | 바깥 자료 | 다시 풀 문항 |
|---|---|---|---|---|
| 1 | S1 앨리어싱 | [TDOA 배경지식](notes/TDOA_튜닝_배경지식.md) 3절 | *The Scientist and Engineer's Guide to DSP* (S. W. Smith, dspguide.com) 3장 | Q1 |
| 2 | F2 지연 ↔ 위상 | TDOA 배경지식 2절 (페이저), [Step4 도우미](notes/Step4_helper.html) | 같은 책 10장 "Characteristics of the Phase" | Q6 |
| 3 | F1 DFT·해상도 | TDOA 배경지식 4절 | 같은 책 8~9장 | Q5 |
| 4 | C2 데시메이션 | [logs/Step4.md](../Steps/logs/Step4.md) 처리 속도 시뮬레이션 | 같은 책 10장 "Multirate" | Q10 |
| 5 | C1 FIR 설계 | logs/Step4.md FIR 탭 수 표, [fir_design.py](../Tools/preproc/fir_design.py) 주석 | 같은 책 14장, 16장 | Q11 |
| 6 | C4 공통 지연 상쇄 | [Step4](../Steps/Step4.md) 파라미터 "FIR 조건" | — | Q12 |
| 7 | C3 필터 상태 | docs/firmware.md STREAM 표 preproc 줄, [preproc.h](../Core/app/inc/preproc.h) 주석 | — | Q13 |
| 8 | N1 수치 재현성 | docs/firmware.md `×16` 줄, [test_preproc_host.py](../Tools/preproc/test_preproc_host.py) | — | Q14 |
| 9 | F3 상관 정리·PHAT | TDOA 배경지식 6절 (6.3, 6.5) | — | Q7 |
| 10 | T1 공간 앨리어싱 | TDOA 배경지식 8.3절, 10.1절 | — | Q8 |
| 11 | T2 평면파 LSE | TDOA 배경지식 10.2~10.3절, 10.6절 | — | Q9 |
| 12 | E3 닫힘 | [docs/protocol.md](../docs/protocol.md) v2 부호 규약, [Step3](../Steps/Step3.md) 파라미터 | — | Q20 |
| 13 | S2 dB · E1 적응 문턱 | [Step2](../Steps/Step2.md) 파라미터, [decisions.md](../decisions.md) D2-3 | — | Q4 |
| 14 | E2 블록 평균 | [Step7](../Steps/Step7.md) 파라미터 "블록" | — | Q18 |
| 15 | T3 배경 빼기 | [logs/Step7.md](../Steps/logs/Step7.md) D0 실패 원인 | — | Q19 |
| 16 | R3 클럭 | [logs/Step5.md](../Steps/logs/Step5.md) 샘플레이트 +1.7% | — | Q15 |
| 17 | M1 누수 | [logs/Step6.md](../Steps/logs/Step6.md) 규칙 표 | scikit-learn `GroupKFold` | Q16 |
| 18 | M3 전이·정규화 | [Step8](../Steps/Step8.md) 파라미터 "모델" | scikit-learn `LogisticRegression`의 `C` | Q21 |
| 19 | M4 문턱·운용점 | [Step6](../Steps/Step6.md) 파라미터, [logs/Step8.md](../Steps/logs/Step8.md) v4 | Google *Machine Learning Crash Course* 분류 단원 | Q22 |
| 20 | M5 지표·불확실성 | logs/Step8.md v4 (시드 흔들림, 사건 수) | 같은 과정 (precision/recall) | Q23 |
| 21 | M6 도메인 이동 | logs/Step8.md v5 | — | Q24 |

## 5. 다시 진단하는 법

1. 다시 풀 문항을 [quiz.md](quiz.md)에 `재답:`으로 이어 쓴다. 처음 답은 지우지 않는다.
2. 재채점 후 3절의 판정과 각 Step frontmatter의 `explain`을 갱신한다. ⚠는 다시 풀어 맞으면 지운다.
3. Pass로 바뀐 개념에는 처음 보는 응용 문제를 하나 더 낸다. 그것까지 맞으면 Pass로 확정한다.

Step 완료의 기준: 그 Step의 의존 개념이 전부 ✅이면 "문서를 닫고 설명할 수 있음"으로 본다. [decisions.md](../decisions.md)의 "설명할 수 있다" 기준과 같은 뜻이다.
