---
id: Step5
title: 연속 수음·전처리·기록
depends_on: [Step5pre]
goal_ref: [G4, I1, I3]
exit: "지정 정상 입력 10분 기록에서 유실·OVR·CRC 오류·클리핑 0, 채널 대응 일치, 샘플 번호로 구간·누락 복원, 동일 입력 PC/MCU 최종 PCM 최대 차이 ≤ 2 LSB"
on_fail: null
status: {impl: 통과, explain: 2/8}
---

## 질문과 답
**Q.** 이후 알고리즘을 평가할 만큼 믿을 수 있는 연속 데이터를 얻는가?

**A. 예.** STREAM 10분 × 3(quiet·스피커·선풍기)에서 유실·OVR·qdrop·CRC·클리핑 0, VERIFY 20쌍에서 MCU·PC PCM 최대 차이 1 LSB (기준 ≤ 2). 샘플레이트 +1.7%는 HSE 클럭으로 바꿔 해결했다.

## 최종 목표와의 연결
- G4: 50 kHz 3채널 → CMSIS FIR ↓4 → 12.5 kHz int16 PCM 연속 스트림이 실시간 통합의 입력이다.
- I1: 번호 건너뜀·OVR이면 필터 재시작 + `RESYNC`·`GAP`, 큐 유실은 `GAP`만.
- I3: 검증 모드로 같은 디지털 입력의 MCU·PC PCM을 비트 단위로 비교한다.

## 통과 기준 (Roadmap 4.5.2 v0.4, 2026-10-15 확정)
| 항목 | 기준 | 측정 조건 |
|---|---|---|
| 연속 기록 | 유실·OVR·qdrop·CRC 오류·클리핑 0 | STREAM 10분 × 3 (quiet, 스피커, 선풍기) |
| 채널 대응 | 채널 순서 일치 | BURST 재생 녹음 |
| 시간축 | 샘플 번호로 구간과 누락 복원 | 합성 스트림 재생 |
| PC = MCU | 최종 PCM 최대 차이 ≤ 2 LSB | VERIFY 20쌍 |

## 결과
| 항목 | 실측 | 판정 | 날짜 | 근거 |
|---|---|---|---|---|
| FIR 응답 | 75탭, 통과 리플 0.016 dB, 저지 −60.4 dB | 통과 | 2026-10-15 | [fir_response](../reports/step5/fir_response.png) |
| MCU 코드 = PC 기준 (호스트) | 랜덤·550 Hz+11 kHz·0/4095·임펄스 모두 최대 1 LSB | 통과 | 2026-10-15 | [logs/Step5.md](logs/Step5.md) |
| 채널 순서·재생 음량·`geometry.json` | 확인 | 통과 | 2026-10-16 | [playback.md](../reports/step5/playback.md) |
| VERIFY | 20쌍, 입력 −55 ~ −28 dBFS, 최대 1 LSB, CRC 오류 0 | 통과 | 2026-10-16 | logs/Step5.md |
| STREAM quiet 10분 | 유실·OVR·qdrop·CRC·클리핑 0 | 통과 | 2026-10-16 | logs/Step5.md |
| STREAM 스피커 10분 | 위와 같음, CPU 20%, RMS −30.5~−30.9 dBFS | 통과 | 2026-10-16 | logs/Step5.md |
| STREAM 선풍기 | 유실 0 (실제 선풍기 구간 약 7.6분) | 통과 | 2026-10-16 | logs/Step5.md |
| 샘플레이트 | HSI 약 50.86 kHz(+1.7%) → HSE BYPASS 8 MHz로 49,999.6 Hz | 해결 | 2026-10-16 | logs/Step5.md |

## 파라미터
| 이름 | 현재 값 | 근거 |
|---|---|---|
| FIR | Kaiser β 5.65, 75탭, 통과 5 kHz / 저지 7.5 kHz, 군지연 37샘플 @ 50 kHz | [D5pre-2](../decisions.md), `Tools/preproc/fir_design.py` |
| PCM 스케일 | `x = adc − 2048` → FIR·↓4 → ×16 → nearest-even → int16 포화 | PC `np.rint`와 같은 반올림 |
| 송신 큐 | 4칸 링버퍼 | UART 여유 약 17% |
| 마이크 전원 RC | 220 Ω, 100 µF (f_c 7.2 Hz) | 프레임 동기 간섭 대응, logs/Step5.md |

규약(PCM v3, 시간축, 끊김 처리)은 [docs/protocol.md](../docs/protocol.md), 코드 블록 구조와 모드는 [docs/firmware.md](../docs/firmware.md), 보드 시험 명령은 [docs/run.md](../docs/run.md).

## 의존 개념
| ID | 개념 | 판정 |
|---|---|---|
| R1 | DMA 핑퐁 타이밍 | ✅ |
| R2 | 통신 처리량 예산 | ✅ |
| R6 | ISR과 main의 공유 변수 | ❌ ⚠ |
| C1 | FIR 설계 | ❌ |
| C2 | 데시메이션 앨리어싱 | ❌ |
| C3 | 블록 처리와 필터 상태 | ❌ △ |
| N1 | 수치 표현, 반올림, 비트 재현성 | ❌ |
| R3 | 클럭원과 정확도 | ❌ ⚠ |

## 남은 일
- [ ] ch3 고역 잡음 원인 가리기 (모듈 교체 뒤에도 1.6–5 kHz 약 +5 dB, 5–10 kHz 약 +9 dB) — 배선 또는 ADC 핀 추정, 미확정

## 관련 결정
- D4-2, D5pre-2, D5-1 (decisions.md)
