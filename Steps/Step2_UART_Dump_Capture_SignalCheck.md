# Step 2 — UART 프레임 덤프/캡처 & 3채널 원파형 검증

> 프로젝트: 3-MIC TDOA(GCC-PHAT) 기반 음원 방향 추정 터렛 / STM32F446 (Nucleo)
> 날짜: 2026-10-08
> 이전 단계: [Step1_ADC_DMA_DoubleBuffer_MicCheck.md](Step1_ADC_DMA_DoubleBuffer_MicCheck.md)

## 1. 이 단계의 목표
- CubeMonitor(통계값)로는 볼 수 없던 **샘플 단위(20µs) 원파형**을 PC로 가져오기
- 3채널 파형을 겹쳐 보면서 클리핑, 게인 균형, 도달 시간차(TDOA)를 눈으로 검증
- 이후 GCC-PHAT 프로토타입의 입력 데이터(npz) 확보

---

## 2. 폴더 구조 / 빌드 / 개발환경

```
Turret/
├─ Core/
│  ├─ Inc, Src, Startup        ← CubeMX 생성 코드
│  └─ app/
│     ├─ inc/  adc.h app.h def.h tdoa.h
│     ├─ src/  adc.c app.c def.c tdoa.c
│     └─ test/ dump.c/h capture.c/h      ← 디버그용 덤프/캡처
├─ Tools/
│  ├─ dump_viewer.py
│  ├─ requirements.txt
│  ├─ .venv/                    (git 제외)
│  └─ dumps/                    (git 제외, 캡처 데이터)
├─ Steps/                       ← 단계별 정리 문서
└─ Plots/
```

| 항목 | 내용 |
|---|---|
| 소스 경로 | `.cproject` 소스 폴더가 `Core` 전체 → `Core/app/**.c` 자동 컴파일. 추가 설정 불필요 (F5 Refresh) |
| Include 경로 | `Core/app/inc`, `Core/app/test` 추가 (All configurations). ⚠️ 현재 **절대경로**로 들어가 있음 → `../Core/app/inc`, `../Core/app/test` 상대경로로 바꾸는 것 권장 |
| 폴더 이동 후 | Project → Clean 1회 (옛 `Debug/Core/Src/*.o` 제거) |
| Python | `Tools/.venv` (Python 3.11), `pyserial numpy matplotlib scipy`, `requirements.txt`로 재현 |
| .gitignore | `Tools/.venv/`, `Tools/dumps/`, `__pycache__/`, `*.npz` |

venv 사용:
```powershell
cd C:\Users\user\STM32CubeIDE\Turret\Tools
.\.venv\Scripts\python dump_viewer.py --port COM8                 # 실시간 수신
.\.venv\Scripts\python dump_viewer.py --replay dumps\100.npz      # 저장 파일 다시 보기
```

---

## 3. UART 설정과 연결

### CubeMX 설정
| 항목 | 값 | 이유 |
|---|---|---|
| USART2 Baud | **921600** | 12KB 패킷 ≈ 0.13초 (115200이면 ≈1.07초 → 홀드오프 1초보다 길어 `skip_busy` 발생) |
| DMA | USART2_TX, DMA1 Stream6 Ch4, **Normal**, Byte, MemInc | `HAL_UART_Transmit_DMA` 사용 |
| NVIC | **USART2 global interrupt ON** | F4 HAL은 DMA 완료 후 UART TC 인터럽트에서 `HAL_UART_TxCpltCallback` 호출 → 꺼져 있으면 `dump_busy()`가 영원히 true |
| 포트 | ST-LINK 가상 COM = **COM8** | CubeMonitor(디버그 포트)와 동시 사용 가능 |

### 앱 연결 (`Core/app/src/app.c`)
- UART 하드웨어 초기화는 CubeMX(`MX_USART2_UART_Init`, `HAL_UART_MspInit`)가 이미 함.
- 앱에서 할 일:
  - `app_init`: `dump_init(app->huart)` → `capture_init(NULL)` → ADC 시작 → TIM2 시작(항상 마지막)
  - 메인 루프: `adc_get_frame()` 직후 **`capture_on_frame(&frame, seq)`** 호출
  - `HAL_UART_TxCpltCallback` → `dump_on_tx_cplt(huart)`
  - `HAL_GPIO_EXTI_Callback` (B1) → `capture_request_manual()`
---

## 4. 왜 덤프/캡처인가 — "차량 블랙박스" 방식

- 연속 전송 불가: 50k샘플 × 3ch × 2B = **300 KB/s** > UART 921600bps ≈ **92 KB/s**
- 그래서 **소리가 났을 때 그 전후만** 보낸다.

| 블랙박스 | 이 프로젝트 |
|---|---|
| 충격 감지 센서 | **capture.c** — "소리 났다" 판단 (언제 보낼지) |
| 충격 직전 영상도 저장 | 직전 프레임 + 트리거 프레임 (40.96ms) |
| 영상 파일로 포장 | **dump.c** — 패킷 포장 + CRC + UART DMA 송신 (어떻게 보낼지) |
| PC에서 재생 | **dump_viewer.py** — 수신·검증·저장(npz)·그래프 |

---

## 5. capture — 트리거 방식

매 프레임(20.48ms) `capture_on_frame()`:
```
① 채널별 AC RMS 계산 → level = 3채널 중 최대
② threshold = max(k_on × 잡음바닥, min_rms)
③ level > threshold && 학습 끝 && 홀드오프 끝 → 송신 [직전 프레임 | 현재 프레임]
④ 조용한 프레임(또는 학습 구간)이면 잡음바닥 EMA 갱신
⑤ 현재 프레임을 '직전 프레임'으로 보관
```

| 파라미터 | 기본값 | 이유 |
|---|---|---|
| `learn_frames` | 25 (≈0.5초) | 부팅 직후 방 잡음 학습, 트리거 안 함 → **리셋 직후 0.5초는 조용히** |
| `k_on` | 4.0 (≈+12dB) | 잡음이 우연히 튀는 정도로는 트리거 안 되게 |
| `min_rms` | 20 LSB | 잡음바닥이 아주 낮을 때 오트리거 방지 |
| `holdoff_frames` | 50 (≈1초) | 잔향 재트리거 방지 + 송신 시간 확보 |
| `floor_alpha` | 0.05 | 잡음바닥 추종 속도. 조용한 프레임에서만 갱신 (박수로 임계값이 오르지 않게) |

- **직전 프레임을 같이 보내는 이유**: 트리거는 소리가 커진 뒤에 걸림 → 직전 20ms를 붙여야 **소리 시작점**이 항상 포함됨.
- 직전 프레임은 `frame_seq == 이전 + 1`일 때만 이어붙임 (중간 drop 시 시간축 끊김 방지).

### 자동 트리거 vs B1 버튼
| | 자동 | B1 버튼 (수동) |
|---|---|---|
| 조건 | 임계값 초과 + 학습/홀드오프 끝 | **무조건** (학습·홀드오프 무시) |
| 제목 표시 | `[PRETRIG]` | `[MANUAL PRETRIG]` |
| 용도 | 소리 캡처 | 조용한 상태 **잡음 기준** 캡처, **송신 경로만** 시험 |

둘 다 이전 송신이 진행 중이면 보내지 못하고 `g_capture.skip_busy++`.
## 6. dump — 패킷 형식

```
[FF FF FF FF][헤더 16B][payload ch0[n] | ch1[n] | ch2[n]][CRC16 2B]
```
| 필드 | 의미 |
|---|---|
| sync `FF FF FF FF` | 패킷 시작. ADC 값 ≤ 0x0FFF라 payload에서 FF 4연속 불가 → 오인 없음 |
| ver=2, type=0x01, ch=3 | 형식 버전, RAW_ADC, 채널 수 |
| flags | `0x01` CLIP, `0x02` MANUAL, `0x04` PRETRIG |
| seq | 송신 패킷 번호 (누락 검출) — ⚠️ **MCU 리셋 시 0부터 다시 시작** |
| frame_seq | ADC 프레임 번호 (시간 정보, 나중에 MCU 결과 패킷과 짝짓기용) |
| n, len | 채널당 샘플 수(1024×프레임 수), payload 바이트 수 |
| CRC-16/CCITT-FALSE | ver~payload 끝. Python `binascii.crc_hqx(data, 0xFFFF)`와 동일. 12KB 기준 ≈2ms |

- **DMA 송신 이유**: CPU 직접 송신이면 0.13초 동안 ADC 프레임 6개를 놓침.
- 송신 버퍼는 정적 12,310B (DMA가 읽는 동안 스택 사용 불가).

---

## 7. dump_viewer.py — 결과 읽는 법

### 콘솔
```
seq 3  saved dumps/f_000003.npz  (1.52 s since last)  {'ok': 4, 'crc_fail': 0, 'bad_hdr': 0, 'seq_gap': 0}
```
| 항목 | 0이 아니면 |
|---|---|
| `crc_fail` | 보레이트 불일치, `printf` 혼입, 잡음 |
| `bad_hdr` | 거의 0이어야 정상 |
| `seq_gap` | PC가 패킷을 놓침 (리셋 직후 1회는 정상) |

### 그래프 3단
| 그래프 | 내용 | 볼 것 |
|---|---|---|
| **위: 전체 40.96ms** | -20 ~ 0ms = 직전 프레임,  0 ~ 20ms = 트리거 프레임 (빨간 점선 = 트리거 프레임 시작) | 소리 전 구간이 조용한가, 0·4095 점선에 붙었나(클리핑) |
| **가운데: 시작점 확대** | onset 기준 −0.5~+1.5ms, 평균 제거, **점 하나 = 20µs** | **같은 마루·골을 짝지어 채널 간 몇 점 밀렸나 = TDOA**. Δn × 20µs, Δn × **6.86mm** |
| **아래: 스펙트럼** | Hann 창, dBFS (0dBFS = 진폭 2048 사인), 로그 주파수, 초록 띠 = BPF 후보 (`--bpf`로 변경) | 에너지 대역, 험/스위칭 노이즈 선 → BPF 대역 결정 |

- onset(빨간 점선) = 최대 진폭의 20%(또는 잡음×6)를 처음 넘은 지점 → **대략값**. 실제 시작은 선들이 기준선에서 갈라지는 지점.
- 타당성: |Δn| ≤ 마이크 간격 / 6.86mm (예: 10cm → ≈15샘플)


---

## 8. 측정 결과 (핑거스냅)

| 캡처 | rms (M1/M2/M3) | p2p | clip | 해석 |
|---|---|---|---|---|
| seq 51 (게인 조정 전) | 232 / 298 / 304 | 4094~4095 | 8 / 22 / 18 | ⚠️ **3채널 모두 포화**. MIC1≈MIC3 먼저, MIC2 ≈+5샘플(≈3.4cm). 에너지 1.5~5kHz, 피크 ≈2.1kHz |
| seq 618 (MIC1 위주로 감도 낮춤) | 158 / 29 / 46 | 2731 / 428 / 735 | 0 / 0 / 0 | 클리핑 해결. 그러나 **채널 간 5.4배(−15dB) 차이** → 위치 탓인지 게인 탓인지 구분 필요. 1.1k·2.1kHz 공통 노치 (반사음 빗살 효과 가설: 간격 ≈1kHz → τ≈1ms ≈ 34cm) |
| seq 884 (재조정) | 213 / 258 / 134 | 3484 / 3808 / 2364 | 4 / 9 / 0 | 균형 **1.9배(−5.7dB)로 개선**, 3채널 파형 모양 거의 동일. MIC1 → MIC2 **+1샘플** → MIC3 **+3샘플**. 클리핑은 onset 후 1ms 이상 뒤라 직접음 구간은 깨끗 |

### 관찰 포인트
- 바이어스 3채널 모두 ≈2048, 60Hz 험 없음 → 전원/아날로그 깨끗.
- 소리 시작 이후 6~20ms의 잔향(벽/책상 반사) → **방향 정보는 첫 직접음에만** 정확 → GCC-PHAT은 onset 근처 몇 ms만 잘라서 쓰는 것이 유리.
- **MIC3은 5kHz 이상이 다른 채널보다 15~20dB 낮음** (파형도 더 둥긂). 채널 간 주파수(=위상) 응답 차이는 GCC-PHAT 지연을 편향시킬 수 있음 → BPF 상한을 3채널 스펙트럼이 비슷한 대역(≈4kHz 이하)으로.
- 같은 스냅이라도 매번 스펙트럼이 다름 (피크 2.1kHz ↔ 2.5kHz). 클리핑은 가짜 고조파를 만들어 스펙트럼을 왜곡 → BPF 결정은 클리핑 없는 캡처로.

### 게인 기준
- 3채널 게인은 **같게** (세 마이크에서 같은 거리, 1m 이상 정면에서 스냅 → rms ±2배 이내).
- 예상 최대 음량·최소 거리에서 p2p ≲ 3000 되는 선에서 **최대한 높게** (너무 낮추면 SNR 저하 → 그 채널 쌍의 지연 추정 불안정).
- "대부분의 캡처에서 clip = 0"이면 충분.

---

## 9. 왜 GCC-PHAT을 Python에서 먼저 만드나

MCU에서 바로 구현하면 결과가 이상할 때 원인 후보(알고리즘 이해 / 파라미터 / CMSIS-DSP 사용법 / 버퍼·인덱스 버그 / 매번 다른 소리)를 **구분할 수 없음**.

| 이점 | 내용 |
|---|---|
| 재현성 | 같은 npz로 무한 반복. 파라미터 바꿔 몇 초 만에 비교 |
| 가시성 | 상관 곡선 전체, 피크 선명도, 반사음 2차 피크까지 보임 |
| 설계 결정 | BPF 대역, 분석 구간 길이, FFT 크기·제로패딩, 2차 보간 효과를 데이터로 결정 |
| 정답지(golden model) | MCU 결과를 `frame_seq`와 함께 보내 같은 프레임의 Python 결과와 비교 → 차이 ≤ 0.1샘플이면 구현 OK. 틀리면 MCU 코드만 의심 |

```
Python : 알고리즘 설계 + 파라미터 결정 + 정답지   (빠른 반복, 다 보임)
   ↓ 확정된 설계 이식
MCU    : CMSIS-DSP 구현 → 같은 프레임 결과를 Python과 비교   (구현 버그만 찾으면 됨)
```

---

## 10. 데이터 현황

- `Tools/dumps/1.npz ~ 100.npz` : 최신 100개만 보관, **시간순 (1 = 가장 오래됨, 100 = 최신)**
  - 원래 seq 786 ~ 885, frame_seq 121154 ~ 151295
  - 그 이전 캡처(위 표의 seq 51, 618 포함 757개)는 삭제함. seq 884 = `99.npz`
- 숫자 이름이라 일반 정렬은 `1, 10, 100, 11, ...` 순 → Python에서는 `sorted(files, key=lambda p: int(Path(p).stem))`

---

## 11. 남은 이슈 / 다음 할 일

### 정리할 것
- [ ] `capture_on_frame`에 `mon_frame_cnt` 대신 **ADC 실제 프레임 번호** 전달 (`adc_get_frame_seq()` getter 추가). `mon_frame_cnt`는 drop된 프레임을 안 세서, drop 시 끊긴 두 프레임이 연속으로 보일 수 있음
- [ ] Include 경로 절대경로 → 상대경로
- [ ] 뷰어 저장 이름 `f_{seq}.npz`는 **MCU 리셋 시 seq가 0부터 다시 시작해서 이전 파일을 덮어씀** → 세션별 타임스탬프 폴더 또는 파일명에 시각 추가

### 측정
- [ ] 같은 거리 보정 테스트로 3채널 게인 최종 맞춤 (rms ±2배, clip 0)
- [ ] 각 마이크 바로 옆 스냅 → 그 마이크가 가장 먼저·크게 듣는지 (채널 매핑)
- [ ] 수직이등분선 위 스냅 → 해당 쌍 Δn ≈ 0 (동시성)
- [ ] B1 버튼으로 조용한 상태 잡음 기준 캡처 (게인 바꿨으니 SNR 재확인)
- [ ] MIC3 고주파 부족 원인: MIC1과 자리 바꿔 캡처 → 위치를 따라가면 배치 문제, 모듈을 따라가면 모듈 문제
- [ ] 마이크 배치(간격·형상) 실측 → 최대 지연(샘플) 계산
- [ ] 터렛이 반응할 **대상 소리** 결정 (스냅/박수/목소리 등) → BPF 대역 근거

### 다음 단계: `Tools/gcc_phat.py`
1. npz에서 onset 근처 구간 잘라내기 (직접음 위주)
2. 쌍(1-2, 1-3, 2-3)별 GCC-PHAT → 피크 → 지연
3. 눈으로 읽은 값(seq 884: +1, +3샘플)과 비교 검증
4. 최대 지연 검사, 2차 보간, 각도 변환

### 전체 로드맵 (app.c 주석 기준)
1. 마이크 모듈 파형 테스트 ← **완료** (덤프로 원파형 확인)
2. ADC-DMA 핑퐁 버퍼링, 지연/지터 측정 ← 구조 완료, DWT 타이밍 측정 남음
3. DMA 버퍼 안전 복사 ← 완료
4. GCC-PHAT (FFT → BPF → PHAT → IFFT → 피크) ← **다음: Python 프로토타입**
5. 후처리: 2차 보간, LSE 오차 보정, 시간차 → 각도
