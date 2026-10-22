# Step6 로그 — 데이터

## 데이터 v0 (2026-10-15)
| 출처 | 라벨 | 쓰는 부분 | 양 |
|---|---|---|---|
| Salford DroneNoise (CC BY 4.0) | 드론 | 4기종 × 호버·통과 비행, 사건마다 마이크 9개 중 M1·M5·M9 | 18사건 |
| Western Sydney DJI Air 3 (CC BY-SA 4.0) | 드론 | `device_1_nosync.wav` 5채널, 82–112 s와 200–240 s | 2사건 |
| ESC-50 (CC BY-NC 3.0) | 비드론 | 50범주 2000클립 중 1996개 | 약 2.3시간 (무음 창 제외) |

- 드론 사건은 모두 21개. 창 수는 드론 2116, 비드론 16822, 불확실 899 (1 s 창, 0.5 s 이동).
- 산출물: `data/dataset_manifest.csv` (항목 2056), `data/splits.json`. 원본 오디오는 `DataSet/`에 있고 git에서 제외된다.
- fold: fold1 Fp(DJI FPV) + ESC f1, fold2 3p(Mini 3 Pro) + ESC f2, fold3 M3(Matrice 300) + ESC f3, fold4 Yn(Yuneec) + ESC f4, fold5 A3(WS Air 3) + ESC f5 (`dataset_v0.py`).

| 규칙 | 해결하려는 문제 | 근거 |
|---|---|---|
| split 단위 = 사건 (`event`) | 같은 비행을 9개 마이크가 동시에 녹음 → 마이크가 갈리면 같은 소리가 학습·시험에 동시에 | 사건의 모든 마이크·창을 같은 fold에. 스크립트가 `assert`로 확인 |
| ESC-50 원본 4개 제외 | `src_file`이 같은 클립 4개(시계·닭)가 두 fold에 걸침 | 누수 방지 |
| Salford 마이크 3개만 | 9개를 다 쓰면 계산량 3배, 정보는 겹침 | 같은 사건 안의 중복이라 독립 표본이 늘지 않음 |
| 통과 비행·WS는 `near_only` | 멀리 있는 앞뒤 구간은 정답이 불확실 | 500 Hz 위 대역 레벨이 파일 최대 −20 dB 이내만 양성, 나머지 −1 |
| Western Sydney를 별도 fold로 | 모델이 "녹음기 차이"를 드론으로 배울 수 있음 | fold5 = 처음 보는 녹음기에서의 성능 |
