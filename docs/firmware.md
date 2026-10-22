# 펌웨어

코드가 원본이다. 이 문서는 참고표이고 코드와 같은 커밋에서 고친다.

## 모듈 구조

```
Core/
├─ app/                       직접 작성한 코드
│  ├─ inc/ src/
│  │  ├─ app      초기화와 메인 루프. APP_MODE에 따라 모듈을 연결
│  │  ├─ adc      ADC 3채널 + DMA 핑퐁 (프레임 1024샘플), 프레임 번호, OVR 복구
│  │  ├─ preproc  CMSIS FIR ↓4 → int16 PCM (fir_coeffs.h는 Tools/preproc/fir_design.py가 생성)
│  │  ├─ stream   PCM v3 / DOA 결과 패킷, 송신 큐
│  │  ├─ doa      지속음 방향 (D1, Step7)
│  │  ├─ tdoa     스냅 GCC-PHAT (Step3, SNAP 모드)
│  │  └─ def      공통 include, error_handle
│  └─ test/
│     ├─ capture  소리 트리거 (RMS, 잡음 바닥 EMA, holdoff)
│     ├─ dump     v2 패킷 + CRC, UART DMA
│     ├─ burst    50 kHz 164 ms 연속 원파형
│     └─ verify   원본 + PCM 쌍
├─ Inc/, Src/                 CubeMX 생성 코드 (main.c가 app_init / app_main 호출)
└─ Startup/
Drivers/                      HAL, CMSIS, CMSIS-DSP. 직접 고치지 않음
```

## 데이터 흐름 (STREAM 모드)

```
마이크 3개 → ADC1~3 동시 변환 (50 kHz, TIM2 TRGO) → DMA 핑퐁 (반버퍼 1024샘플 = 20.48 ms)
  → adc_get_frame(out, &seq)  복사 + ISR이 매긴 번호
  → preproc_run               CMSIS FIR ↓4 → int16 (256샘플)
  → doa                       블록 누적 → 창마다 방위
  → stream_push / _doa        4칸 링버퍼 → UART TX DMA 921600 bps
  ADC overrun ISR → ovrPending → adc_service: 정지 → 재시작
```

## 클럭·ADC·DMA

| 항목 | 설정 | 비고 |
|---|---|---|
| 클럭원 | HSE BYPASS 8 MHz (ST-LINK MCO) | 2026-10-16 HSI에서 전환 (D5-1) |
| SYSCLK | PLL M=4, N=180, P=2 → 180 MHz | Over-drive ON, Flash latency 5 |
| APB1 / APB2 | 45 MHz / 90 MHz | TIM2 클럭 = 90 MHz |
| 샘플링 트리거 | TIM2, PSC 0, ARR 1799 → 50 kHz TRGO(Update) | ADC1 외부 트리거, Rising |
| ADC 모드 | Triple regular simultaneous | ADC1 = 마스터, ADC2/3 = 슬레이브 |
| 채널 | ADC1 = PA0(IN0), ADC2 = PA1(IN1), ADC3 = PC0(IN10) | |
| ADC 클럭 | PCLK2/4 = 22.5 MHz | 28 + 12 = 40 cycles ≈ 1.78 µs/변환 |
| DMA | DMA2 Stream0 Ch0, P→M, half-word, Circular, 다중모드 DMA mode 1 | ADC1→2→3 순 |
| DDS | `DMAContinuousRequests = ENABLE` | 순환 DMA가 계속 요청받기 위해 필요 |
| 시작 순서 | 슬레이브 `HAL_ADC_Start` ×2 → 마스터 `HAL_ADCEx_MultiModeStart_DMA` → `HAL_TIM_Base_Start` | 타이머를 마지막에 켜서 buffer[0] = ADC1 보장 |
| 버퍼 | `adc_buffer[6144]` uint16, 인터리브 [ADC1, ADC2, ADC3, …], 반버퍼 3072 | 프레임당 3,686,400 cycles |

- ISR(HT/TC 콜백)은 어느 절반이 준비됐는지와 번호만 표시한다. main이 `__disable_irq()` 구간에서 꺼내고, 복사 후 번호가 바뀌었으면 폐기하고 `drop`을 올린다.
- F446(Cortex-M4)은 D-Cache가 없어 DMA 캐시 일관성 문제가 없다. 샘플 간격은 TIM2가 정하므로 콜백 지터는 처리 마감에만 영향을 준다.
- OVR: ISR은 횟수만 세고, main에서 타이머 → ADC → DMA를 멈춘 뒤 슬레이브 → 마스터 → 타이머 순으로 재시작한다. 재시작에 걸린 시간은 프레임 번호에 나타나지 않고 `RESYNC`·`GAP`으로만 표시된다.

## UART

| 항목 | 값 | 이유 |
|---|---|---|
| USART2 | 921600 bps | 115200이면 12 KB 패킷이 약 1.07 s |
| DMA | USART2_TX, DMA1 Stream6 Ch4, Normal, Byte, MemInc | `HAL_UART_Transmit_DMA` |
| NVIC | USART2 global interrupt ON | F4 HAL은 UART TC 인터럽트에서 `HAL_UART_TxCpltCallback`을 부른다. 꺼져 있으면 busy가 풀리지 않음 |
| 포트 | ST-LINK 가상 COM | CubeMonitor(디버그 포트)와 동시 사용 가능 |

- busy 플래그는 DMA 시작 전에 켠다. 송신 버퍼는 `static` (DMA가 함수가 끝난 뒤에도 읽음).

## 동작 모드 (`app.c`의 `APP_MODE`, 또는 `-DAPP_MODE=n`)

| 모드 | 값 | 내용 | 수신 | 텍스트 | data + bss |
|---|---|---|---|---|---|
| SNAP | 0 | 소리 트리거 → TDOA → 결과/원파형 (`CAPTURE_SEND_RAW` 1 검증 / 0 결과 전용) | `doa/doa_live.py` | 146.1 KB | 106.8 KB |
| BURST | 1 | 50 kHz 164 ms 연속 원파형 반복 | `board/burst_rx.py` | 14.3 KB | 89.4 KB |
| STREAM | 2 (기본) | 12.5 kHz PCM 연속 + DOA 결과 | `board/stream_capture.py` | 14.8 KB | 46.8 KB |
| VERIFY | 3 | 원본 + PCM 쌍 | `board/verify_preproc.py` | 15.3 KB | 106.8 KB |

크기는 2026-10-15 명령줄 빌드 (doa.c 추가 전). doa 포함 빌드는 RAM 108 KB / 128 KB, Flash 148 KB, 스택 최대 112 B (2026-10-18).

## STREAM 코드 블록과 도입 이유

| 코드 | 해결하려는 문제 | 근거 |
|---|---|---|
| `adc.c` `readySeq`, `adc_get_frame(out, &seq)` | main이 받은 횟수를 세면 놓친 프레임이 번호에 안 드러남 | ISR에서 번호를 매기고 데이터와 같은 임계 구역에서 꺼냄 |
| `preproc.c` `arm_fir_decimate_f32` ×3 | 7.5 kHz 위가 0~5 kHz로 접힘 | 계수 하나, 상태는 채널마다 (세 채널 위상 응답이 같아야 방위가 안 틀어짐) |
| `preproc.c` 상태를 프레임 사이에서 유지 | 경계마다 지우면 20.48 ms마다 과도 응답 → 48.8 Hz 빗 | `preproc_reset()`은 부팅과 끊김 뒤에만 |
| `preproc.c` `×16`, `lrintf`, `__SSAT` | PC와 비트 단위로 비교하려면 int16 고정 | 반올림 규칙이 `np.rint`와 같음 |
| `stream.c` 링버퍼 4칸 + `kick_locked` | 송신(약 17 ms/패킷) 중에도 20.48 ms마다 다음 프레임 | 생산자 1·소비자 1. 넘치면 버리고 `qdrop`, 번호는 소비 |
| `app.c` `on_stream_frame` | 끊긴 입력을 필터에 이어 넣으면 가짜 파형 | 번호 건너뜀·OVR → 필터 재시작 + `RESYNC`·`GAP`, 큐 유실은 `GAP`만 |
| `verify.c` | "같은 디지털 입력"으로 비교해야 함 | 8프레임 원본과 PCM을 같이 보냄 |

## doa.c (MCU 방향, Step7)

| 결정 | PC와 다른 점 | 이유 |
|---|---|---|
| 블록이 준비될 때마다 누적 | 0.5 s 창을 저장하지 않음 | 창 저장은 37 KB, 링버퍼 6 KB면 됨. 프레임마다 블록 하나라 계산이 고르게 나뉨 |
| 창 이동 3072 샘플 (0.246 s) | PC 기본 3125 (0.25 s) | 블록 간격 256의 배수 → 겹치는 두 창과 배경이 같은 블록 FFT 공유 (프레임당 FFT 3개) |
| 상관을 지연 범위만 직접 계산 | 16배 제로패딩 IFFT(16384점) 대신 115개 지연 × 221빈 합 | 같은 값, IFFT용 64 KB 불필요. 회전 인자는 부팅 때 표로, 세 쌍 공유, ±지연 대칭 |
| 배경 10 s, 부팅 시 + B1 버튼 | PC 시험은 60 s | 켠 뒤 빨리 쓰기 위함 |
| 배경 재학습 중 기존 배경 사용 | — | 처음 배우는 10 s만 D0로 표시 |
| ADC 유실·overrun이면 창을 버리고 다음 프레임부터 | 송신 큐 유실은 무시 | 큐 유실은 PC만 못 받은 것 |

RAM: doa 약 64 KB (배경 2벌 16 KB, 창 2개 16 KB, 링버퍼·FFT·블록 스펙트럼·PHAT 버퍼). Hann 512 → FFT 1024, 대역 빈 221개만 보관.

## tdoa.c (스냅, Step3)

| 함수 | 하는 일 |
|---|---|
| `tdoa_init()` | FFT 준비, 창 계산, 마이크 좌표 → 최소제곱 풀이 행렬(2×3). 부팅 시 한 번 |
| `tdoa_process(frames, nframes, out)` | onset → 구간 → 평균 제거·Tukey → FFT 512 → 교차 스펙트럼 → 대역 + PHAT → IFFT → 피크 + 2차 보간 → LSE → atan2·norm → `valid` |
| `find_onset()`, `deviation()`, `sample()` | onset 탐색 (정수 연산, 두 프레임을 붙이지 않고 번호로 읽음) |

- 고정 버퍼 약 11 KB. `arm_rfft_fast_f32`는 입력 버퍼를 덮어쓴다. 음수 지연은 `corr[512 + l]`. 피크가 1이 되도록 `512 / (2 × 19)`를 곱함.
- 터렛 제어는 `r.valid`가 참일 때만 `r.angle_deg`를 써야 한다.

## 같이 고쳐야 하는 짝 (I3)

| MCU | PC | 맞출 것 |
|---|---|---|
| `Core/app/inc/tdoa.h` (`TDOA_BAND_*`, `TDOA_WIN`, `TDOA_PRE`, `TDOA_MAX_LAG`, `TDOA_PHAT_EPS`, `TDOA_SPACING_M`, `TDOA_MIN_PEAK`·`_NORM`) | `Tools/doa/gcc_phat.py` (`--band`, `--win`, `--pre`, `--max-lag`, `--eps`, `--spacing`, `--min-peak`, `--min-norm`, `--max-norm`) | 대역, 분석 구간, FFT, 간격, 신뢰 판정 |
| `Core/app/inc/doa.h` (`DOA_HOP`, `DOA_BAND_*`, `DOA_BG_SECONDS`, 유효 판정) | `Tools/doa/doa_stream.py`, `config/geometry.json` | 창·대역·판정, 채널 지연 |
| `Core/app/inc/fir_coeffs.h`, `preproc.h` | `Tools/preproc/fir_design.py`, `frontend.py` | FIR 계수·스케일·위상 |
| `Core/app/test/dump.h`, `Core/app/inc/stream.h` | `Tools/board/dump_viewer.py` (`RESULT_FMT`, `DOA_FMT`) | 헤더 필드, 버전, 패킷 종류 ([protocol.md](protocol.md)) |
| `TDOA_FS`, `ADC_SAMPLES_PER_HALF` | `Turret.ioc` 타이머 | 샘플링 주파수, 프레임 길이 |

## 빌드·IDE

- `.cproject` 소스 폴더가 `Core` 전체라 `Core/app/**.c`는 자동 컴파일 (새 파일이 안 잡히면 F5 Refresh). Include 경로에 `Core/app/inc`, `Core/app/test`.
- CMSIS-DSP 1.10.0 (STM32Cube_FW_F4_V1.28.3에서 복사, 소스만). `Include`, `PrivateInclude` 전체와 `Source` 중 아래만. Source 폴더를 통째로 넣으면 묶음 파일(`TransformFunctions.c` 등) 때문에 같은 함수가 두 번 정의된다.

| 폴더 | 파일 |
|---|---|
| TransformFunctions | `arm_rfft_fast_f32`, `arm_rfft_fast_init_f32`, `arm_cfft_f32`, `arm_cfft_init_f32`, `arm_cfft_radix8_f32`, `arm_bitreversal2` |
| CommonTables | `arm_common_tables`, `arm_const_structs` |
| ComplexMathFunctions | `arm_cmplx_conj_f32`, `arm_cmplx_mult_cmplx_f32`, `arm_cmplx_mag_f32` |
| BasicMathFunctions | `arm_offset_f32`, `arm_mult_f32` |
| StatisticsFunctions | `arm_mean_f32`, `arm_max_f32` |
| FilteringFunctions | `arm_fir_decimate_f32`, `arm_fir_decimate_init_f32` (Step5) |

- IDE (Debug): FPv4-SP-D16, Hardware ABI (기본값), Include `../Drivers/CMSIS/DSP/Include`·`PrivateInclude`, 최적화 `-Ofast` (D3-3). `ARM_MATH_CM4` define 불필요. FPU는 CubeMX `SystemInit()`이 켠다.
- 명령줄 빌드를 위해 `Debug/`의 생성 makefile에 새 파일을 추가한 적이 있다. CubeIDE 빌드에서는 자동으로 다시 만들어진다.

## CubeMX 재생성 주의

- ADC 전역 인터럽트를 켜면 `stm32f4xx_it.c`에 `ADC_IRQHandler`가 생겨 `adc.c`의 것과 링크 충돌이 난다. 그때는 `adc.c`의 핸들러를 지운다.
- HSE는 BYPASS(8 MHz, ST-LINK 입력)다. 크리스털 16 MHz로 두면 보드가 절반 속도로 돈다 (UART 깨짐).
