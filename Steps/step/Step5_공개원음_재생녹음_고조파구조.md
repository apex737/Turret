# Step 5 (사전 측정) — 공개 원음 선정과 고조파 구조

> 작성: 2026-10-14, 정리: 2026-10-18 | 브랜치: `FPV_Target`
> 상태: **완료.** 원음 선정과 대역 결정의 기록이다. Step 번호는 [Roadmap v0.4](Step4.5.2_Roadmap_축소.md)를 따른다. burst·재생 녹음 절차는 git 기록(커밋 `0cdb3a6`의 판)에 있다.

## 결론

| 질문 | 답 | 근거 |
| --- | --- | --- |
| 쓸 대역은? | **f_use = 5 kHz, 50 → 12.5 kHz (↓4).** 고조파 선은 모든 기체에서 약 2 kHz 아래 (FPV는 4번째 고조파 약 2.1 kHz까지), 선 에너지 99%는 6 kHz 아래 | [harmonics.md](../../reports/step5/harmonics.md) |
| 스피커로 재생해도 쓸 만한가? | **쓸 수 있다.** FPV 고조파는 원본 4개 중 장치에서 3개 남는다. 노트북 스피커는 270 Hz 아래가 약하다 | [playback.md](../../reports/step5/playback.md) |
| FPV 소리는 실제로 얼마나 큰가? | **DJI FPV 15 m/s 통과, 고도 10 m에서 LAFmax 59–61 dBA → 1 m 환산 약 80 dBA.** 같은 조건 Mini 3 Pro는 47–50 dBA, 호버 51–53 dBA. 현장 배경 21–23 dBA | Salford 보정 신호로 계산 (2026-10-18). 보정기 94 dB 가정, 지면판이면 음원은 6 dB 더 작다 |

FPV는 로터마다 회전수가 달라 빗이 4번째 차수 위로 흐트러진다.

## 원음 (2026-10-14 조사)

**지상 원거리에서 실제 FPV를 녹음한 공개 데이터는 Salford의 DJI FPV 하나뿐이다.** 우크라이나형 7~10인치 자작 FPV를 지상에서 녹음한 공개 자료는 찾지 못했다. 실전 녹음 연구(arXiv 2608.14287)는 데이터를 공개하지 않았다.

| 원음 | 내용 | 쓰는 곳 | 한계 |
| --- | --- | --- | --- |
| **[Salford DroneNoise](https://salford.figshare.com/articles/dataset/DroneNoise_Database/22133411)** (CC BY 4.0) | 지상 마이크 9개, 고도 10 m 통과. **DJI FPV** 15 m/s × 3회, Mini 3 Pro 통과·호버, Matrice 300, Yuneec H520E. 마이크별 보정 신호 | FPV 양성, 실제 음압 | FPV는 상용 DJI 한 기종, 호버 없음, 독립 사건 3회 |
| **[Western Sydney](https://research-data.westernsydney.edu.au/published/1f8cceb0801b11f189a547c836cf5bee/)** (CC BY-SA 4.0) | DJI Air 3, 지상 24채널 48 kHz, GPS 로그, 드론 없는 배경음 | 정답 방위가 있는 다채널, 배경음 | FPV 아님 |
| [Lund Ljungbyhed](https://vision.maths.lth.se/drone_sound/) | 12채널 배열, 여러 드론, 위치 정답 | 방향 추정 예비 | 받지 않음 |
| [DDL (Zenodo)](https://zenodo.org/records/6459183) (CC BY 4.0, 17 GB) | Mini 2, Phantom 4 Pro, 방위·거리·고도가 파일명에 | 비FPV 양성 예비 | 받지 않음 |
| [32종 드론](https://arxiv.org/html/2509.04715v1) | DJI FPV·Avata 포함 | 보류 | MacBook 마이크, 5초, 원본·라이선스 없음 |
| [DroneAudioset](https://arxiv.org/html/2510.15383v1) | F450/F330 고정, 마이크 25~50 cm | 탈락 | 기체 근접 소음 |
| [DADS](https://huggingface.co/datasets/geronimobasso/drone-audio-detection-samples) | 여러 데이터셋을 16 kHz로 합침 | 사전 실험용 | 대역 판단 불가 |

**선택:** Salford(전체)와 Western Sydney를 `DataSet/`에 받는다 (git 제외). 상용 Sound Ex Machina "Quadcopters"(자작 5·8인치 FPV 포함)는 쓰지 않는다 (2026-10-14 사용자 결정). 그래서 FPV 양성은 Salford DJI FPV 하나뿐이고, 학습은 "멀티로터 대 배경"으로 시작했다.

## FPV 양성 추가 후보 (2026-10-18 조사, Step8 v1 미달 뒤)

Step8 v1에서 증강만으로는 FPV가 늘지 않았다 (FPV 출처가 Salford DJI FPV 하나). 다른 출처의 FPV를 학습에 넣고 Salford FPV는 시험으로 남기는 것이 목적이다.

| 출처 | 내용 | 라이선스 | 판단 |
| --- | --- | --- | --- |
| [Freesound 524331](https://freesound.org/people/5deMayo/sounds/524331/) (5deMayo) | 5인치 프리스타일 쿼드 통과 비행 여러 번, Tascam DR-40, 22 s | CC0 | **사용.** MP3 128 kbps (5 kHz 아래는 영향 작음) |
| [Freesound 677833](https://freesound.org/people/Sadiquecat/sounds/677833/) (Sadiquecat) | TinyHawk 2 마이크로 FPV 실내 호버, Zoom H5, 96 kHz WAV, 45 s | CC0 | **사용.** 실내 잔향, 작은 기체 |
| [Freesound 854646](https://freesound.org/people/qubodup/sounds/854646/) (qubodup) | Orqa MRM2-10 (10인치 군용 FPV) 이륙·이탈, DVIDS 영상에서 추출, 바람 제거 처리, 5.8 s | CC0 (원본 DVIDS 공공 영역) | 보조. 짧고 처리됨 |
| [Freesound 854352](https://freesound.org/people/qubodup/sounds/854352/), 854464~854466 (qubodup) | 미군 FPV 훈련 영상에서 추출. 854464~6은 1인칭(기체 쪽) 소리일 가능성 | CC0 | 보조. 기체 쪽 소리는 지상 수음과 다르다 |
| Freesound 680584 | DJI FPV 전원 켜기 | — | 제외. 시험 기체(DJI FPV)와 같은 기종 |
| Freesound 733938 등 LimitlessDrones | 1~2 s "swoosh" 효과음 팩 | CC0 | 제외. 가공된 효과음 |
| **DVIDS B-roll 영상** ([저작권 안내](https://api.dvidshub.net/docs/copyright)) | 미군 FPV 훈련의 무편집 촬영 영상, 지상 카메라 소리. 예: [Predator's Run 26](https://www.dvidshub.net/video/1016337/b-roll-predators-run-26-mrf-d-marines-conduct-flight-missions-with-neros-archer-drone), [26th MEU CPX 2](https://www.dvidshub.net/video/1020900/26th-meus-command-post-exercise-2-attack-drone-training), [24th MEU FPV Drones](https://www.dvidshub.net/video/1006580/24th-meu-fpv-drones), [1-23 IN Archer LFX](https://www.dvidshub.net/video/1008636/1-23-neros-archer-uas-lfx), [Project Flytrap 영국군 FPV](https://www.dvidshub.net/video/966534/british-soldiers-fly-fpv-drones-cuas-training-during-project-flytrap), [WTI 1-26 Archer 시연](https://www.dvidshub.net/video/985163/wti-1-26-neros-archer-first-person-view-drone-demonstration) | 공공 영역 (연방 제작물. 항목별 별도 표기 확인, 다운로드는 무료 가입) | **가장 큰 후보.** 기종은 대부분 Neros Archer, 일부 Orqa. 카메라 마이크·압축·바람·말소리가 섞여 구간을 골라야 한다 |

Freesound에서 실제 FPV 녹음은 이것이 거의 전부다 ("fpv" 태그 60개 중 다수는 1인칭 걷기 녹음).
