---
id: Step2
title: UART 프레임 덤프·캡처와 3채널 원파형 확인
depends_on: [Step1]
goal_ref: [G1, G4]
exit: "(사후 정리) 샘플 단위(20 µs) 원파형을 PC로 가져와 3채널을 겹쳐 보고 클리핑·게인 균형·도달 시간차를 확인, GCC-PHAT 입력(npz) 확보"
on_fail: null
status: {impl: 통과, explain: 1/6}
---

## 질문
연속 전송이 안 되는 UART(약 92 KB/s)로 3채널 원파형을 어떻게 PC에서 볼 것인가?

## 최종 목표와의 연결
- G1: PC에서 같은 원파형으로 다시 계산하는 정답지(Python) 방식의 입력을 만든다 ([D2-4](../decisions.md)).
- G4: 패킷·CRC·TX DMA 구조가 이후 STREAM 패킷의 바탕이다.

## 통과 기준 (확정일 기록 없음 — 원문 "이 단계의 목표"를 사후에 옮김)
| 항목 | 기준 | 측정 조건 |
|---|---|---|
| 원파형 수신 | 트리거 프레임 + 직전 프레임, CRC 오류 0 | `dump_viewer.py` 콘솔 카운터 |
| 3채널 확인 | 클리핑·게인 균형·도달 시간차를 눈으로 확인 | 그래프 3단 |
| 정답지 입력 | npz 저장 | `dumps/` |

## 결과
| 항목 | 실측 | 판정 | 날짜 | 근거 |
|---|---|---|---|---|
| 패킷 수신 | 덤프 수신·그래프 확인 (패킷 12,310 B, 전송 약 134 ms는 계산값) | 통과 | 2026-10-08 | [dump_plot](../reports/step2/dump_plot.png) |
| 캡처 seq 22 | 클리핑 0, p2p 430 / 985 / 511, rms 29 / 63 / 31 (MIC2 약 +6 dB) | 확인 | 2026-10-08 | [logs/Step2.md](logs/Step2.md) |
| 스펙트럼 | 에너지 대부분 2~6 kHz, 150~2000 Hz는 −60~−70 dBFS | 확인 | 2026-10-08 | logs/Step2.md |
| 서서히 커지는 소리 | 약 59 dB/s 미만 상승은 트리거 안 됨 (시뮬레이션) | 한계 | 2026-10-10 | logs/Step2.md |

## 파라미터
| 이름 | 현재 값 | 근거 |
|---|---|---|
| `learn_frames` | 25 (약 0.5 s) | 부팅 직후 방 잡음 학습 |
| `k_on` | 4.0 (약 +12 dB) | [D2-3](../decisions.md) |
| `min_rms` | 20 LSB | 잡음 바닥이 아주 낮을 때 오트리거 방지 |
| `holdoff_frames` | 50 (원파형) / 10 (결과 전용) | [D3-6](../decisions.md) |
| `floor_alpha` | 0.05 | D2-3. 조용한 프레임에서만 갱신 |

값은 이론이 아니라 실험으로 정했다. 패킷 형식은 [docs/protocol.md](../docs/protocol.md), UART 설정은 [docs/firmware.md](../docs/firmware.md).

## 의존 개념
| ID | 개념 | 판정 |
|---|---|---|
| R2 | 통신 처리량 예산 | ✅ |
| S2 | dB, RMS, 전력 | ❌ △ |
| E1 | EMA, 적응 문턱 | ❌ |
| S3 | ADC 눈금 LSB와 dBFS | 미진단 |
| L1 | C 배열 typedef·packed 구조체·_Static_assert | 미진단 |
| L2 | CRC 무결성 검사 | 미진단 |

## 남은 일
- [ ] `dump_viewer.py` 저장 이름 `f_{seq}.npz`가 MCU 리셋 시 덮어써짐 → 세션별 폴더 또는 시각을 파일명에 (`doa_live.py`는 세션 폴더로 해결됨)

## 관련 결정
- D2-1, D2-2, D2-3, D2-4 (decisions.md)
