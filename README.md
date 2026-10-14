# Turret — 마이크 3개로 소리 방향 찾기

STM32F446RE에서 마이크 3개를 동시에 샘플링하고, GCC-PHAT으로 도달 시간차(TDOA)를 구해 음원 방향을 계산한다.
PC 쪽 Python 도구로 원파형을 받아 같은 계산을 다시 하고, MCU 결과와 비교한다.

- 현재 동작: 스냅·박수 같은 **순간음**의 방향 검출 (Step 1~3)
- 진행 중: **드론(지속 고조파음)** 탐지와 방향 추정으로 전환 (Step 4)

---

## 폴더 구조

```
Turret/
├── Core/
│   ├── app/                 ← 직접 작성한 코드는 전부 여기
│   │   ├── inc/
│   │   │   ├── app.h        앱 진입점 (app_init, app_main)과 하드웨어 핸들 묶음
│   │   │   ├── adc.h        ADC 3채널 + DMA 핑퐁 버퍼 (프레임 1024샘플)
│   │   │   ├── tdoa.h       GCC-PHAT 방향 계산과 모든 튜닝 상수 (대역, FFT 크기, 마이크 간격 …)
│   │   │   └── def.h        공통 include, error_handle
│   │   ├── src/
│   │   │   ├── app.c        초기화와 메인 루프. 캡처 → TDOA 계산 → 결과 송신을 연결
│   │   │   ├── adc.c
│   │   │   ├── tdoa.c
│   │   │   └── def.c
│   │   └── test/            ← PC로 데이터를 보내는 디버그 모듈
│   │       ├── capture.c/h  소리가 나면 프레임을 잡아 둠 (RMS 트리거, 잡음 바닥 학습, holdoff)
│   │       └── dump.c/h     패킷(헤더 + CRC)을 만들어 UART DMA로 송신
│   ├── Inc/, Src/           CubeMX 생성 코드 (main.c가 app_init / app_main 호출)
│   └── Startup/             시작 어셈블리
├── Drivers/                 STM32 HAL, CMSIS, CMSIS-DSP (FFT에 사용). 직접 고치지 않음
├── Tools/                   PC 쪽 Python 도구
│   ├── dump_viewer.py       덤프 수신 + 시간파형 / FFT 보기, npz로 저장
│   ├── gcc_phat.py          GCC-PHAT 프로토타입 (MCU 구현의 정답지). 합성 신호 자체 시험, 대역 비교
│   ├── doa_live.py          실시간 방향 나침반, 정답 각도 세션(--truth), MCU 결과와 비교
│   ├── f0_probe.py          녹음 파일(wav)에서 고조파 구조와 f0를 읽음 (Step 4)
│   ├── requirements.txt
│   └── dumps/               측정 데이터 (git에 올리지 않음)
├── Steps/                   단계별 설계·기록 문서 (아래 표)
├── Plots/                   문서에 쓰는 그림
├── Turret.ioc               CubeMX 설정 (핀, 클럭, ADC, 타이머, UART)
├── STM32F446RETX_FLASH.ld   링커 스크립트
├── STM32F446RETX_RAM.ld
└── .cproject, .project      STM32CubeIDE 프로젝트 파일
```

`Debug/`(빌드 결과), `*.launch`(개인 디버그 설정), `Tools/dumps/`는 `.gitignore`에 들어 있다.

---

## 데이터 흐름

```
마이크 3개 → ADC1~3 동시 변환 (50 kHz, TIM2 트리거) → DMA 핑퐁 버퍼
  → adc.c   프레임 1024샘플 복사
  → capture.c   소리가 났는지 판정
  → tdoa.c   GCC-PHAT → 지연 3개 → 각도
  → dump.c   UART 921600 bps (원파형 + 결과 패킷)
  → Tools/   dump_viewer.py, doa_live.py 가 수신해 PC에서 다시 계산하고 비교
```

---

## 같이 고쳐야 하는 짝

한쪽만 바꾸면 MCU와 PC의 결과가 맞지 않는다.

| MCU                                    | PC                                       | 맞춰야 하는 것                    |
| -------------------------------------- | ---------------------------------------- | --------------------------------- |
| `Core/app/inc/tdoa.h` 상수             | `Tools/gcc_phat.py` 기본값               | 대역, 분석 구간, FFT 크기, 간격 등 |
| `Core/app/test/dump.h` 패킷 형식       | `Tools/dump_viewer.py`, `doa_live.py`    | 헤더 필드, 버전, 패킷 종류         |
| `TDOA_FS`, `ADC_SAMPLES_PER_HALF`      | `Turret.ioc` 타이머 설정                 | 샘플링 주파수, 프레임 길이         |

---

## Steps 문서

| 문서                                   | 내용                                                         |
| -------------------------------------- | ------------------------------------------------------------ |
| `Step1_ADC_DMA_DoubleBuffer_MicCheck`  | ADC 3채널 동시 샘플링, DMA 핑퐁, 마이크 확인                 |
| `Step2_UART_Dump_Capture_SignalCheck`  | 소리가 났을 때만 원파형을 PC로 보내기                        |
| `Step3_GCC_PHAT_Python_MCU_DOA`        | GCC-PHAT을 Python으로 먼저 만들고 MCU로 이식, 결과 비교. 기준선 정의 |
| `Step4_드론음향_탐지추정_설계`         | 순간음 검출기를 드론 탐지 + 방향 추정으로 바꾸는 설계        |
| `TDOA_튜닝_배경지식`                   | 원리, 파라미터 카드, 튜닝 실험 절차                          |
| `decisions.md`                         | 방향을 좌우한 설계 결정과 근거                               |
| `Step*_helper.html`                    | 각 단계의 원리를 그림으로 설명하는 페이지 (브라우저로 열기)  |

---

## 빌드와 실행

- **펌웨어:** STM32CubeIDE로 프로젝트를 열고 빌드 → 보드에 다운로드
- **PC 도구:**
  ```
  cd Tools
  pip install -r requirements.txt
  python dump_viewer.py --port COM5
  python doa_live.py --port COM5
  ```
  포트 이름은 장치 관리자에서 확인한다. 각 스크립트의 사용법은 파일 맨 위 주석에 있다.
