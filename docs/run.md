# 실행 절차

두 번 이상 실행하는 절차의 최신판. 결과는 `Steps/logs/`에 적는다.
스크립트 목록은 [Tools/README.md](../Tools/README.md). 모든 명령은 `Tools/`에서 `.\.venv\Scripts\python.exe <폴더>\<스크립트>.py`로 실행한다. 포트 이름은 장치 관리자에서 확인한다 (ST-LINK 가상 COM, 예: COM8). COM 포트는 한 프로그램만 열 수 있다.

## 준비

```
cd Tools
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

- 펌웨어: STM32CubeIDE로 열고 빌드 → 다운로드. 모드는 `app.c`의 `APP_MODE` ([firmware.md](firmware.md)).
- `Debug/`, `*.launch`, `Tools/.venv/`, `Tools/dumps/`, `DataSet/`은 git에서 제외된다.

## SNAP 모드 (스냅 방향, Step3)

```
board\dump_viewer.py --port COM8                 # 원파형 수신, 그래프 3단, npz 저장
board\dump_viewer.py --replay dumps\100.npz      # 저장 파일 다시 보기
doa\gcc_phat.py --selftest                       # 합성 신호로 구현 검증
doa\gcc_phat.py dumps\<세션>\f_000012.npz        # 파일 1개: 결과 + 그래프
doa\gcc_phat.py dumps\<세션>                     # 폴더 전체 표
doa\gcc_phat.py dumps\<세션> --sweep             # 대역 × 구간 비교
doa\doa_live.py --port COM8                      # 실시간 나침반 + MCU 비교 (dumps\<날짜_시각>\ 세션 폴더)
doa\doa_live.py --port COM8 --truth 90           # 실제 각도를 알고 측정
doa\doa_live.py --replay dumps\<세션>
```

- 결과 전용 모드(`CAPTURE_SEND_RAW 0`)에서는 npz 없이 `log.csv`만 남는다. 알고리즘·파라미터를 바꾼 뒤에는 원파형 모드로 한 번 검증한다.
- `dump_viewer.py` 콘솔: `crc_fail`(보레이트 불일치·printf 혼입), `bad_hdr`(거의 0), `seq_gap`(PC가 놓침, 리셋 직후 1회는 정상).
- B1 버튼: 학습·holdoff를 무시하는 수동 캡처 (조용한 상태 잡음 기준, 송신 경로 시험).

## Step5 보드 시험 (BURST · VERIFY · STREAM)

| 순서 | 모드 | 명령 | 통과 |
|---|---|---|---|
| 1 | BURST | `board\burst_rx.py` (quiet, pink, tone, 드론 재생) + 마이크 간격·채널 순서 실측 | 채널 순서, 클리핑 없는 재생 음량, `config/geometry.json` |
| 2 | VERIFY | `board\verify_preproc.py --port COMx --pairs 20` (조용히 / 말소리 / 재생음) | 모든 쌍 최대 차이 ≤ 2 LSB |
| 3 | STREAM | `board\stream_capture.py --port COMx --label quiet_10min --minutes 10` | `summary.json`의 `passed: true` |
| 4 | STREAM | 같은 명령으로 스피커 재생 10분, 선풍기 10분 | 같음. 클리핑이 나면 게인·음량 조정 후 재시험 |

- 실행 중 2초마다 KB/s(약 76이어야 함), 채널 레벨, CPU 최대, 유실 수가 나온다. `cpu` = 프레임마다 전처리 + 큐 적재 시간 / 프레임 주기.
- 실패하면 `summary.json`의 `delta_drop_ovr_qdrop`로 가른다: drop = main이 늦음, ovr = ADC DMA, qdrop = UART 대역폭.
- 호스트 시험 (보드 없이): `preproc\test_preproc_host.py`, `stream_capture.py --replay`.

## Step7 실제 각도 시험 (STREAM 모드)

**배치** — 노트북은 고정하고 배열을 돌린다.
- 각도 정의: 위에서 볼 때 배열 중심에서 MIC1 쪽이 0°, 반시계 방향이 + (MIC2 = 120°, MIC3 = 240°).
- 소리는 노트북 왼쪽 스피커 하나로 (`21_doa_left_100s.wav`, 원음 5개 × 20 s, 왼쪽 채널만). 배열 중심에서 1 m, 마이크와 같은 높이.
- 책상에 종이 각도판을 고정한다. 중심에서 왼쪽 스피커로 향하는 선을 0으로 하고 시계 방향으로 30°마다 0 … 330을 적는다. 브레드보드에 배열 중심(삼각형 무게중심)과 MIC1 화살표를 표시하고 각도판 중심에 맞춘다.
- 배열을 시계 방향으로 돌려 MIC1 화살표가 가리키는 눈금 = 그 녹음의 각도. 배열을 시계 방향으로 θ 돌리면 음원은 배열 기준 +θ에 온다.
- 눈금 ±2° 안 (1 m에서 3.5 cm). 볼륨 고정. 사람은 스피커와 배열 사이에 서지 않는다.

**녹음** — 12방향 × 1회, 배경 2회

| 순서 | 할 일 | 명령 |
|---|---|---|
| 0 | 재생 없이 배경 1분 | `board\stream_capture.py --port COM8 --label doa_bg --minutes 1` |
| 1–12 | 배열을 θ에 맞춤 → 명령 → 바로 `21_doa_left_100s.wav` 한 번 재생 → 끝까지 조용히 | `board\stream_capture.py --port COM8 --label doa_az000 --minutes 2` (`az030` … `az330`) |
| 13 | 재생 없이 배경 1분 | `--label doa_bg2 --minutes 1` |

- 상태 줄의 `clip`이 0보다 커지면 볼륨을 낮추고 0번부터 다시 한다.
- 0°·120°·240°는 마이크 쪽, 60°·180°·300°는 두 마이크 사이다.

**분석**: `doa\doa_stream.py "dumps/stream/doa_az*" --bg dumps/stream/doa_bg` (배경 변화 확인: `--bg dumps/stream/doa_bg2`). 옵션 `--global-offset`(공통 회전 제거), `--no-delay-cal`(채널 지연 보정 끔).
- 편향이 모든 각도에서 같으면 0° 기준이 돌아간 것 (배치 오차). 부호가 각도에 따라 뒤집히면 회전 방향이나 채널 순서가 틀린 것.

**채널 지연 보정 측정** (`cal_d0`, `cal_d180`): 캡슐을 한 점에 모아 0°·180° 두 번 녹음하고 평균. 결과는 `config/geometry.json`의 `channel_delay_us`. 마이크 모듈이나 게인 트리머를 바꾸면 다시 잰다.

**합성 시험**: `doa\eval_doa_synth.py` → `reports/step7/synth_eval.txt`. 실제 녹음: `doa\doa_stream.py "dumps/stream/*_10min" --bg dumps/stream/quiet_10min`.

## Step7 MCU 방향 보드 시험

1. 빌드·다운로드 (새 파일이 안 잡히면 F5).
2. `board\stream_capture.py --port COM8 --label mcu_doa --minutes 2` 실행 직후 B1(파란 버튼)을 한 번 누르고 10 s 조용히 → `21_doa_left_100s.wav` 재생. 상태 줄에 `방위 … 유효 D1`.
3. `doa\compare_mcu.py dumps/stream/mcu_doa`

B1을 녹음 중에 누르는 이유: 부팅 때 배운 배경은 PC가 받지 못한 구간이라 재현할 수 없다. 호스트 시험: `doa\test_doa_host.py`.

## Step8 학습 재현

```
cd Tools
.venv/Scripts/python.exe ml/dataset_v0.py      # data/dataset_manifest.csv, data/splits.json
.venv/Scripts/python.exe ml/embed_v0.py        # DataSet/_cache/emb_v0.npz (약 10분, CPU)
.venv/Scripts/python.exe ml/train_v0.py        # reports/step8/v0_report.md
.venv/Scripts/python.exe ml/embed_v1.py        # DataSet/_cache/emb_v1_aug.npz, emb_v1_dev.npz (약 10분)
.venv/Scripts/python.exe ml/train_v1.py        # reports/step8/v1_report.md (약 2분)
# v2: DataSet/DVIDS_FPV/*.mp4 → ffmpeg로 DataSet/_extract/DVIDS_FPV/*.wav, 사람 라벨 DataSet/_listen/FPV_candidates/labels.csv
.venv/Scripts/python.exe ml/embed_v2.py        # DataSet/_cache/emb_v2_fpv.npz
.venv/Scripts/python.exe ml/train_v2.py        # reports/step8/v2_report.md
.venv/Scripts/python.exe ml/fsd50k_fetch.py    # DataSet/FSD50K/audio (1,070 클립, 약 1 GB, Range로 필요한 것만)
.venv/Scripts/python.exe ml/embed_v3.py        # DataSet/_cache/emb_v3_neg.npz
.venv/Scripts/python.exe ml/train_v3.py        # reports/step8/v3_report.md
.venv/Scripts/python.exe ml/train_v4.py        # reports/step8/v4_report.md (약 17분, MLP)
.venv/Scripts/python.exe ml/diag_v4_curve.py   # reports/step8/v4_curve.png
.venv/Scripts/python.exe audio/make_devpath_playback.py  # DataSet/_playback/30_devpath_A·B.wav, 30_devpath.csv
# 보드 녹음 devpath_A·B (아래)
.venv/Scripts/python.exe ml/embed_v5.py        # DataSet/_cache/emb_v5_dev.npz
.venv/Scripts/python.exe ml/train_v5.py        # reports/step8/v5_report.md
```

(이전 판 기록에는 `dataset_v0.py`·`embed_v0.py`·`train_v0.py`가 `Tools/` 바로 아래로 적혀 있었다. 현재 위치는 `Tools/ml/`이다.)

## Step8 v5 장치 경로 녹음 (사용자)

speaker_10min과 같은 배치·노트북 음량. 알림음·음향 효과는 끈다. 보드는 STREAM 모드.

```
cd Tools
.venv/Scripts/python.exe board/stream_capture.py --port COMx --label devpath_A --minutes 25
#   시작 메시지가 뜨면 DataSet/_playback/30_devpath_A.wav 재생 (1분 안에 재생을 시작한다)
.venv/Scripts/python.exe board/stream_capture.py --port COMx --label devpath_B --minutes 25
#   같은 방법으로 30_devpath_B.wav
```

통과 조건: 각 녹음 `summary.json`의 clip 0, 소리 구간 레벨이 speaker_10min과 비슷 (약 −30 dBFS). 시계 차이·시작 시각은 `embed_v5.py`가 찾는다.

## 흐름도

```
pip install pyyaml markdown
python Tools/flow/gen_flow.py .
```

Windows 콘솔(cp949)에서는 마지막 출력 줄에서 `UnicodeEncodeError`가 날 수 있다 (`flow.html`은 이미 만들어진 뒤). `PYTHONIOENCODING=utf-8`을 주고 실행한다.
