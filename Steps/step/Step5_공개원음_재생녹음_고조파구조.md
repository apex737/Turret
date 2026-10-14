# Step 5 — 공개 원음 선정 + 재생 녹음 + 고조파 구조

> 작성: 2026-10-14 | 브랜치: `FPV_Target`
> 위치: [Step4.5_Roadmap.md](Step4.5_Roadmap.md). 다음은 Step6 학습 v0과 Step7 방향 방식 결정 (같은 녹음 사용)

## 0. 이 단계가 답할 질문

1. **FPV 소리의 고조파는 어떻게 생겼나?** f0 범위, 쓸 만한 고조파 수, 선 폭, 에너지가 있는 주파수의 상한
2. **이 장치(스피커 → MAX4466 → 50 kHz ADC)로 들어도 그 빗이 남는가?**

| 결과 | 정해지는 것 |
| --- | --- |
| 에너지 상한 → f_use | FIR 설계, ↓4(12.5 kHz) 또는 ↓2(25 kHz), 전송 구조 (Step8) |
| f0 범위, 고조파 수 H, 선 폭 | 고조파 검출기의 후보 범위·H·마스크 폭 (Step6 B0, Step7) |
| 원본 대비 장치 녹음에서 남는 빗살 수 | 재생음을 학습·검증 데이터로 쓸 수 있는 범위 |
| 원음 목록과 등급 | Step6의 학습·시험 분할 |

---

## 1. 원음 후보 (2026-10-14 조사)

**결론: 지상 원거리에서 실제 FPV를 녹음한 공개 데이터는 Salford의 DJI FPV 하나뿐이다.** 우크라이나형 7~10인치 자작 FPV를 지상에서 녹음한 공개 자료는 찾지 못했다. 실전 녹음 연구(arXiv 2608.14287)는 데이터를 공개하지 않았다.

### A — 핵심 후보

| 원음 | 내용 | 장점 | 한계 |
| --- | --- | --- | --- |
| **[Salford DroneNoise Database](https://salford.figshare.com/articles/dataset/DroneNoise_Database/22133411)** (CC BY 4.0, 742 MB) | 지상 마이크 9개, 고도 10 m 통과 비행. **DJI FPV** 15 m/s × 3회, DJI Mini 3 Pro 통과 + 호버, Matrice 300, Yuneec H520E. 마이크별 보정 신호 포함 | 유일한 지상 원거리 FPV. 무편집 계측용 녹음. 보정 신호가 있어 실제 음압을 알 수 있음 | FPV는 상용 DJI 한 기종. 통과 비행뿐이고 호버가 없음. 독립 사건은 3회 (마이크 9개는 같은 사건). 샘플레이트는 받아서 헤더로 확인 |

### B — FPV는 아니지만 쓸모가 큰 것

| 원음 | 내용 | 쓰는 곳 |
| --- | --- | --- |
| **[Western Sydney UAV Acoustic Localization](https://research-data.westernsydney.edu.au/published/1f8cceb0801b11f189a547c836cf5bee/)** (CC BY-SA 4.0, researchdata.edu.au 기재. 다운로드 페이지에서 재확인) | DJI Air 3, 지상 24채널 48 kHz, GPS 비행 로그 100 ms, 드론 없는 배경음 | **Step7**: 정답 방위가 있는 다채널이라 BPF 대 고조파를 장치 없이도 비교 가능. Step6: 음성(배경) |
| [Lund Ljungbyhed](https://vision.maths.lth.se/drone_sound/) (사이트 CC BY-SA 4.0) | 12채널 배열, 여러 드론, 위치 정답 | Step7 예비 |
| [DDL (Zenodo)](https://zenodo.org/records/6459183) (CC BY 4.0, 17 GB) | DJI Mini 2, Phantom 4 Pro, 배열 녹음. 방위·거리·고도가 파일명에 있음. 합성본 포함 | Step6 비FPV 양성, Step7 예비 |

### C — 참고만 하거나 탈락

| 원음 | 판정 | 이유 |
| --- | --- | --- |
| [32종 드론 데이터셋](https://arxiv.org/html/2509.04715v1) | 보류 | DJI FPV·Avata 포함. 하지만 MacBook 내장 마이크, 5초 클립, 원본 다운로드·라이선스 없음. 저자에게 요청할 수는 있음 |
| [DroneAudioset](https://arxiv.org/html/2510.15383v1) | 탈락 | 프레임에 고정한 F450/F330, 마이크 25~50 cm. 기체 근접 소음 |
| [DADS (Hugging Face)](https://huggingface.co/datasets/geronimobasso/drone-audio-detection-samples) | 보조 | 여러 데이터셋을 16 kHz로 합친 것. 대역 판단에는 못 쓰고 Step6 사전 실험용 |
| Freesound: Orqa MRM2-10 (10인치 군용 FPV), 5인치 통과 비행 등 | 청취 참고 | 영상에서 추출하거나 바람 제거를 거침. 라이선스·원본 형식 개별 확인 필요 |
| Svanström 다중 센서 (Hubsan H107D+) | 보조 | 완구급 기체, 오디오 90개 |

### 이 단계의 선택

- **사용**: Salford(전체), Western Sydney(1개 세션부터). `DataSet/`에 받음 (git 제외).
- **사용 안 함**: 상용 Sound Ex Machina "Quadcopters"(자작 5·8인치 FPV 포함, 2026-10-14 사용자 결정). 그래서 FPV 양성은 Salford DJI FPV 하나뿐이다. Step6은 "FPV 대 일반 멀티로터"를 구분하지 않고 "멀티로터 대 배경"으로 시작한다.

---

## 2. 작업

### 5-1 원본 분석 — 고조파 검출기 v0 (PC) ✅ 2026-10-14

> **결과**: [reports/step5/harmonics.md](../../reports/step5/harmonics.md). 고조파 선은 모든 기체에서 약 2 kHz 아래(FPV는 4번째 고조파 ~2.1 kHz까지)에 있다. 선 에너지 99%는 6 kHz 아래다. → **f_use = 5 kHz, ↓4(12.5 kHz) 유지.** FPV는 로터마다 회전수가 달라 빗이 4번째 차수 위로 흐트러진다. 도구: `Tools/harmonic_survey.py`, 듣기용 변환: `Tools/to_listen.py`.

### 5-2 burst 캡처 (펌웨어) ✅ 구현·빌드 2026-10-14, 보드 확인 전

- `Core/app/test/burst.c/h`: 50 kHz 3채널을 트리거 없이 8프레임(8192샘플, 164 ms)씩 끊김 없이 모아 보낸다. 모으는 도중 프레임이 유실되면 그 burst를 버린다.
- 프레임은 dump 송신 버퍼에 바로 채운다. 송신 버퍼를 8프레임(48 KB)으로 늘리고, `dump_payload()`와 `dump_send_payload()`를 추가했다. 패킷은 기존 RAW 형식 그대로이고, `n = 8192`, flags에 `DUMP_FLAG_BURST`(0x10)를 쓴다.
- `app.c`의 `APP_MODE_BURST 1`(기본값)이 burst 모드, 0이면 기존 스냅 모드다.
- 빌드 결과: 경고 없음. RAM은 data + bss 70.9 KB / 128 KB.
- 송신 한 번에 약 0.53 s가 걸리므로 burst는 약 0.7 s마다 하나씩 온다.
- PC 수신: `python Tools/burst_rx.py --port COMx --label <이름> --count <개수>` → `Tools/dumps/step5/<이름>/b_*.npz`

### 5-3 재생 녹음 — 보드에서 할 일

재생 파일은 `python Tools/make_playback.py`로 만들고 `DataSet/_playback/`에 있다. burst는 아무 시점에서나 잘리므로, 시간 정렬이 필요 없는 신호만 쓴다.

| 순서 | 재생 | 녹음 | 무엇을 보나 |
| --- | --- | --- | --- |
| 0 | 없음 (조용히) | `--label quiet --count 20` | 장치 잡음 바닥 |
| 1 | `01_pink_30s` | `--label pink --count 40` | 스피커 → MAX4466 크기 응답 |
| 2 | `02_tone550_steps` (−36 ~ 0 dBFS를 6 dB씩) | `--label tone --count 40` | 음량별 고조파 왜곡 → 재생 음량 상한 |
| 3 | `11~13_fpv_ev1~3`, `14_mini3pro_hover`, `15_air3` (반복 재생) | `--label fpv_ev1 --count 40` … | 원본 대 장치 고조파 |

- 스피커는 **유선**을 쓴다. 블루투스는 손실 압축을 거친다. 배열에서 약 1 m, 같은 높이에 둔다.
- PC 볼륨은 2번에서 정한 상한 아래로 고정하고, 3번 내내 바꾸지 않는다. 터미널에 `CLIP!`이 뜨면 볼륨을 낮춘다.
- 같이 할 것: 실제 마이크 간격을 자로 잰다 (Step7용).

### 5-4 비교와 결정

```
python Tools/playback_check.py --pink pink --silence quiet --tone tone --drone fpv_ev1=11_fpv_ev1 fpv_ev2=12_fpv_ev2 fpv_ev3=13_fpv_ev3 mini3pro=14_mini3pro_hover air3=15_air3
```

- 출력: −10 dB 응답 대역, 채널 간 차이, 왜곡 없는 최대 음량, 원음별 "연속으로 쓸 만한 고조파 수"(원본 → 장치). 그림은 `reports/step5/playback_*.png`.
- **판정**:
  - 응답 대역이 FPV 고조파 대역(약 0.4~2.1 kHz)을 덮고, 장치에서도 FPV 고조파가 3개 이상 남으면 → 재생음을 Step6·7 데이터로 쓴다. f_use = 5 kHz, ↓4 확정.
  - 장치에서 고조파가 크게 줄면 → 스피커 문제인지(응답 대역) 거리·음량 문제인지 가르고, 재생음으로 할 수 있는 검증의 범위를 Roadmap 4절에 적는다.

---

## 3. 통과와 산출물

**통과**: FPV 원음이 하나 이상 장치로 녹음되어 있고, f_use와 ↓ 비율을 숫자로 정했다.

| 산출물 | 내용 |
| --- | --- |
| `data/sources.csv` | 원음 목록: 출처, 라이선스, 기체, 샘플레이트, 등급, 사건 ID |
| `reports/step5/harmonics.md` | 원음별 f0 분포, 빗살별 SNR, 선 폭, 에너지 상한. 원본 대 장치 비교 플롯 |
| `reports/step5/playback.md` | 스피커 모델, 응답 대역, 재생 음량 상한, 원본 대 장치 고조파, 마이크 간격 실측값 |
| `Tools/dumps/step5/` | burst 녹음 (git 제외) |

끝나면 decisions.md에 **f_use와 ↓ 비율**, **원음 선정**만 남긴다.
