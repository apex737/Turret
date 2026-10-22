# Step5pre 로그 — 원음 조사·선정

## 원음 조사 (2026-10-14)
- 결과: 지상 원거리에서 실제 FPV를 녹음한 공개 데이터는 Salford의 DJI FPV 하나뿐. 우크라이나형 7~10인치 자작 FPV를 지상에서 녹음한 공개 자료는 찾지 못함. 실전 녹음 연구(arXiv 2608.14287)는 데이터 비공개.

| 원음 | 내용 | 쓰는 곳 | 한계 |
|---|---|---|---|
| [Salford DroneNoise](https://salford.figshare.com/articles/dataset/DroneNoise_Database/22133411) (CC BY 4.0) | 지상 마이크 9개, 고도 10 m 통과. DJI FPV 15 m/s × 3회, Mini 3 Pro 통과·호버, Matrice 300, Yuneec H520E. 마이크별 보정 신호 | FPV 양성, 실제 음압 | FPV는 상용 DJI 한 기종, 호버 없음, 독립 사건 3회 |
| [Western Sydney](https://research-data.westernsydney.edu.au/published/1f8cceb0801b11f189a547c836cf5bee/) (CC BY-SA 4.0) | DJI Air 3, 지상 24채널 48 kHz, GPS 로그, 드론 없는 배경음 | 정답 방위가 있는 다채널, 배경음 | FPV 아님 |
| [Lund Ljungbyhed](https://vision.maths.lth.se/drone_sound/) | 12채널 배열, 여러 드론, 위치 정답 | 방향 추정 예비 | 받지 않음 |
| [DDL (Zenodo)](https://zenodo.org/records/6459183) (CC BY 4.0, 17 GB) | Mini 2, Phantom 4 Pro, 방위·거리·고도가 파일명에 | 비FPV 양성 예비 | 받지 않음 |
| [32종 드론](https://arxiv.org/html/2509.04715v1) | DJI FPV·Avata 포함 | 보류 | MacBook 마이크, 5초, 원본·라이선스 없음 |
| [DroneAudioset](https://arxiv.org/html/2510.15383v1) | F450/F330 고정, 마이크 25~50 cm | 탈락 | 기체 근접 소음 |
| [DADS](https://huggingface.co/datasets/geronimobasso/drone-audio-detection-samples) | 여러 데이터셋을 16 kHz로 합침 | 사전 실험용 | 대역 판단 불가 |

- 선정 기준 (Roadmap 4.5): 무편집 원본, 16 kHz 초과·비손실, 지상 원거리 수음, 기종·프롭 정보, 독립 비행, 명확한 라이선스.
- 다음: D5pre-1

## FPV 음압 (2026-10-18)
- 바꾼 것: Salford 보정 신호로 LAFmax 계산 (보정기 94 dB 가정, 지면판이면 음원은 6 dB 더 작음)
- 결과: DJI FPV 15 m/s 통과·고도 10 m에서 59–61 dBA → 1 m 환산 약 80 dBA. Mini 3 Pro 47–50 dBA, 호버 51–53 dBA. 현장 배경 21–23 dBA
- 해석: 탐지거리 추정에서 가정했던 1 m 80–90 dBA(문헌 기체 환산값)는 낙관적이었다 (구 Fail_Log 2026-10-18, 결과 0, 실측 Salford 녹음, 라벨 AI)
- 다음: problem.md 열린 결정 (목표 거리, 장치 음압 보정)

## FPV 양성 추가 후보 (2026-10-18, Step8 v1 미달 뒤)
| 출처 | 내용 | 라이선스 | 판단 |
|---|---|---|---|
| [Freesound 524331](https://freesound.org/people/5deMayo/sounds/524331/) (5deMayo) | 5인치 프리스타일 쿼드 통과 비행 여러 번, Tascam DR-40, 22 s | CC0 | 사용. MP3 128 kbps (5 kHz 아래는 영향 작음) |
| [Freesound 677833](https://freesound.org/people/Sadiquecat/sounds/677833/) (Sadiquecat) | TinyHawk 2 마이크로 FPV 실내 호버, Zoom H5, 96 kHz WAV, 45 s | CC0 | 사용. 실내 잔향, 작은 기체 |
| [Freesound 854646](https://freesound.org/people/qubodup/sounds/854646/) (qubodup) | Orqa MRM2-10 (10인치 군용 FPV) 이륙·이탈, DVIDS 영상에서 추출, 바람 제거 처리, 5.8 s | CC0 (원본 DVIDS 공공 영역) | 보조. 짧고 처리됨 |
| [Freesound 854352](https://freesound.org/people/qubodup/sounds/854352/), 854464~854466 (qubodup) | 미군 FPV 훈련 영상에서 추출. 854464~6은 1인칭(기체 쪽) 소리일 가능성 | CC0 | 보조. 기체 쪽 소리는 지상 수음과 다르다 |
| Freesound 680584 | DJI FPV 전원 켜기 | — | 제외. 시험 기체와 같은 기종 |
| Freesound 733938 등 LimitlessDrones | 1~2 s "swoosh" 효과음 팩 | CC0 | 제외. 가공된 효과음 |
| DVIDS B-roll 영상 ([저작권 안내](https://api.dvidshub.net/docs/copyright)) | 미군 FPV 훈련의 무편집 촬영 영상, 지상 카메라 소리. 예: [Predator's Run 26](https://www.dvidshub.net/video/1016337/b-roll-predators-run-26-mrf-d-marines-conduct-flight-missions-with-neros-archer-drone), [26th MEU CPX 2](https://www.dvidshub.net/video/1020900/26th-meus-command-post-exercise-2-attack-drone-training), [24th MEU FPV Drones](https://www.dvidshub.net/video/1006580/24th-meu-fpv-drones), [1-23 IN Archer LFX](https://www.dvidshub.net/video/1008636/1-23-neros-archer-uas-lfx), [Project Flytrap](https://www.dvidshub.net/video/966534/british-soldiers-fly-fpv-drones-cuas-training-during-project-flytrap), [WTI 1-26 Archer](https://www.dvidshub.net/video/985163/wti-1-26-neros-archer-first-person-view-drone-demonstration) | 공공 영역 (항목별 표기 확인, 다운로드는 무료 가입) | 가장 큰 후보. 대부분 Neros Archer, 일부 Orqa. 카메라 마이크·압축·바람·말소리가 섞여 구간을 골라야 한다 |

- Freesound에서 실제 FPV 녹음은 이것이 거의 전부다 ("fpv" 태그 60개 중 다수는 1인칭 걷기 녹음).
- 다음: Step8 v2 (D8-3)

## 시도 기록 (구 Fail_Log)
범례는 [Step8 로그](Step8.md)에 있다.

| 날짜 | 시도 | 결과 | 왜 (원인 한 줄) | 근거 | 라벨 | 이해 |
|---|---|---|---|---|---|---|
| 2026-10-18 | 탐지거리 추정에서 FPV 음원 세기를 1 m 80–90 dBA로 가정 | 0 | 문헌 기체 환산값으로 잡은 가정이 낙관적이었음. Salford 보정 녹음으로 재 보니 DJI FPV는 10 m 통과에서 59–61 dBA, 1 m 환산 약 80 dBA (보정기 94 dB 가정) | 실측 (Salford 녹음) | AI | |
