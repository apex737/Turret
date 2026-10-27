---
name: reference-drone-audio-sources
description: "드론(특히 FPV) 공개 음원 조사 결과 — 어디에 무엇이 있고 무엇이 막혔는지 (2026-10-13, 10-14)"
metadata:
  node_type: memory
  type: reference
  originSessionId: 22b71e3d-c38f-4a45-b943-59b7839e02f2
  modified: 2026-10-27T01:48:11.813Z
---

> **FPV 시절 기록.** 2026-10-26 대상이 고정익 정찰기로 바뀌어 FPV 음원은 비교·음성(negative) 자료로만 쓴다. 고정익·소형 엔진 음원은 아직 조사 안 함 ([[project-product-direction]]).

사용자는 실제 기체가 없어 공개 원음에 의존한다 ([[project-no-real-fpv]]). 전체 후보표와 등급은 `Steps/Step5.md`.

2026-10-14 조사 핵심:
- **지상 원거리 실제 FPV 공개 데이터는 Salford DroneNoise Database뿐** (salford.figshare.com/articles/dataset/DroneNoise_Database/22133411, CC BY 4.0, 742 MB). 파일 코드 `Ed_Fp_10_F15_*` = DJI FPV, 10 m 고도 15 m/s 통과 × 3회 × 지상 마이크 9개. `3p` Mini 3 Pro, `M3` Matrice 300, `Yn` Yuneec H520E. 보정 신호 포함. figshare 웹은 403 → `api.figshare.com/v2/articles/22133411/files`로 조회됨.
- 상용 Sound Ex Machina "Quadcopters" — **2026-10-14 사용자 결정으로 사용하지 않음.** FPV 양성은 Salford DJI FPV뿐.
- Western Sydney DJI Air 3 24ch 48 kHz + GPS 로그 (DOI 10.26183/07nm-4p35) — 방향 추정 오프라인 검증용.
- 탈락/보조: 32종(MacBook 마이크, 원본 미공개), DroneAudioset(기체 근접), DADS(16 kHz 합본), 실전 녹음 arXiv 2608.14287(비공개).
- 2026-10-13: Shahed 공개 데이터셋 없음. 위키미디어 영상은 해설·음악 때문에 못 씀.

도구: `Tools/audio/f0_probe.py` (기본 후보 60~500 Hz, H=10 고정 — FPV용으로 넓혀야 함). 영상 변환은 Octave 설치본의 ffmpeg.

2026-10-18 추가 조사 (Step8 v1 미달 뒤 FPV 다양화): Freesound 실제 FPV는 524331(5인치 통과, CC0, MP3), 677833(TinyHawk 2 실내, CC0, WAV) 정도뿐. qubodup의 DVIDS 추출 클립(Orqa MRM2-10 등)은 짧고 처리됨. **가장 큰 후보는 DVIDS B-roll** (미군 FPV 훈련 무편집 영상, 공공 영역, 다운로드는 무료 가입, 기종 대부분 Neros Archer). 목록은 Step5 원음 문서 끝 표. Freesound·DVIDS 모두 다운로드에 사용자 계정이 필요.
2026-10-19: DVIDS 3편(24th MEU FPV Drones, Predator's Run 26, 26th MEU CPX 2) + Freesound 2개를 사람 라벨로 넣은 Step8 v2에서 FPV 재현율 0.17 → 0.38. DVIDS 방식(ffmpeg 추출 → 유사도 정렬 후보 → 로컬 듣기 페이지 라벨)이 통한다. AudioSet은 5인치 FPV를 전동공구·드릴로 분류하므로 FPV 골라내기에 못 쓴다.
