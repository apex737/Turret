# Tools

모든 명령은 `Tools/`에서 실행한다: `.\.venv\Scripts\python.exe <폴더>\<스크립트>.py ...`

| 폴더 | 용도 | 스크립트 |
| --- | --- | --- |
| `board/` | 보드 시리얼 수신 (펌웨어 APP_MODE와 짝) | `dump_viewer` 패킷 파서·원파형 보기, `burst_rx` BURST, `stream_capture` STREAM, `verify_preproc` VERIFY, `frame_sync_noise` 보드 간섭 측정 |
| `doa/` | 방향 추정 | `gcc_phat` GCC-PHAT 기준 구현, `doa_live` 스냅 모드 실시간 나침반, `doa_compass` STREAM 모드 실시간 나침반(보드 계산 결과, 데모용), `doa_scope` STREAM 신호 사슬 뷰어(PCM 파형·스펙트럼, 방향 계산 중간 단계를 PC가 다시 계산, MCU·PC 비교), `doa_stream` 지속음 방향(STREAM 녹음), `eval_doa_synth` 정답 있는 합성 시험, `test_doa_host` MCU doa.c 호스트 빌드 비교, `compare_mcu` 보드 결과 대 PC 기준, `mask_phat` 대역 상한·PHAT 칸 고르기 합성 비교 |
| `preproc/` | MCU와 같은 전처리 (FIR·↓4) | `fir_design` 계수 생성 → `Core/app/inc/fir_coeffs.h`, `frontend` PC 기준 전처리, `test_preproc_host` + `hosttest/` MCU 코드 PC 빌드 비교 |
| `audio/` | 공개 원음 분석·스피커 재생 | `to_listen` 듣기용 변환, `harmonic_survey`·`f0_probe` 고조파 분석, `make_playback` 재생 파일, `make_devpath_playback` 장치 경로 학습·시험용 재생 파일, `playback_check` 재생 녹음 비교 |
| `ml/` | 학습 분류 (Step6·8) | `dataset_v0` 목록·split, `embed_v0` CNN14 임베딩, `train_v0` 평가, `augment` 증강 함수, `embed_v1` 증강·장치 임베딩, `train_v1` 증강 설정별 비교, `fpv_candidates` 영상에서 FPV 후보 구간 + 듣기 라벨 페이지, `embed_v2`·`train_v2` 새 FPV 출처 평가, `fsd50k_fetch` FSD50K에서 고른 클립만 받기, `embed_v3`·`train_v3` 어려운 비드론 평가, `train_v4` MLP 비교, `diag_v4_curve` 오탐 예산별 곡선, `embed_v5`·`train_v5` 장치 경로 녹음 정렬·학습 평가 |
| `fusion/` | 판정·방위 결합 (Step9A) | `combine` 결합 규칙, `eval_9a` 정답 타임라인 + 12방향 녹음으로 결합 규칙 채점·고장 주입 |
| `track/` | 방위 추적 (Step8c) | `kf` 2상태 KF [θ, ω], `sim_kf` 정답 있는 합성 방위열 시험 |
| `notebooks/` | 실험 흐름 (GUIDE 10절) | 실험마다 `py`(계산)와 짝을 이루는 `ipynb`. 단계별 그림 + 결론 후보. VS Code에서 커널을 `Tools/.venv`로 열면 저장된 출력이 바로 보인다. `doa_mask_phat` ↔ `doa/mask_phat.py`, `kf_synth` ↔ `track/kf.py`·`sim_kf.py` |
| `dumps/` | 보드에서 받은 녹음 (git 제외) | |

다른 폴더의 모듈은 `from board.dump_viewer import ...`처럼 폴더 이름을 붙여 import한다.
