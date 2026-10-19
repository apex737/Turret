# Tools

모든 명령은 `Tools/`에서 실행한다: `.\.venv\Scripts\python.exe <폴더>\<스크립트>.py ...`

| 폴더 | 용도 | 스크립트 |
| --- | --- | --- |
| `board/` | 보드 시리얼 수신 (펌웨어 APP_MODE와 짝) | `dump_viewer` 패킷 파서·원파형 보기, `burst_rx` BURST, `stream_capture` STREAM, `verify_preproc` VERIFY, `frame_sync_noise` 보드 간섭 측정 |
| `doa/` | 방향 추정 | `gcc_phat` GCC-PHAT 기준 구현, `doa_live` 스냅 모드 실시간 나침반, `doa_stream` 지속음 방향(STREAM 녹음), `eval_doa_synth` 정답 있는 합성 시험, `test_doa_host` MCU doa.c 호스트 빌드 비교, `compare_mcu` 보드 결과 대 PC 기준 |
| `preproc/` | MCU와 같은 전처리 (FIR·↓4) | `fir_design` 계수 생성 → `Core/app/inc/fir_coeffs.h`, `frontend` PC 기준 전처리, `test_preproc_host` + `hosttest/` MCU 코드 PC 빌드 비교 |
| `audio/` | 공개 원음 분석·스피커 재생 | `to_listen` 듣기용 변환, `harmonic_survey`·`f0_probe` 고조파 분석, `make_playback` 재생 파일, `playback_check` 재생 녹음 비교 |
| `ml/` | 학습 분류 (Step6·8) | `dataset_v0` 목록·split, `embed_v0` CNN14 임베딩, `train_v0` 평가, `augment` 증강 함수, `embed_v1` 증강·장치 임베딩, `train_v1` 증강 설정별 비교, `fpv_candidates` 영상에서 FPV 후보 구간 + 듣기 라벨 페이지, `embed_v2`·`train_v2` 새 FPV 출처 평가, `fsd50k_fetch` FSD50K에서 고른 클립만 받기, `embed_v3`·`train_v3` 어려운 비드론 평가, `train_v4` MLP 비교, `diag_v4_curve` 오탐 예산별 곡선 |
| `dumps/` | 보드에서 받은 녹음 (git 제외) | |

다른 폴더의 모듈은 `from board.dump_viewer import ...`처럼 폴더 이름을 붙여 import한다.
