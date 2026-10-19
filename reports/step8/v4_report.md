# Step8 v4 (C1) — 분류기만 MLP로 (CNN14 임베딩, 기체 하나씩 빼는 5-fold)

> `Tools/ml/train_v4.py`가 만든 파일. 데이터·fold·문턱 규칙·시험 데이터는 v2·v3과 같고 분류기만 다르다.
> 문턱: 학습 데이터 안 교차검증에서 비드론 창 오탐 1%. 사건·클립 판정은 연속 3창 중 2창. MLP는 시드 2개.

| 데이터 | 분류기 | FPV 창 재현율 | FPV 창 AUC | FPV 대 곤충 AUC | Matrice 통과 AUC | 5기종 평균 재현율 | 평균 창 AUC | 사건 | 오탐/시간 (클립) | 장치 경로 재현율 (FPV / Mini3 / Air3) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v2 | 직선 | 0.43 | 0.956 | 0.75 | 0.446 | 0.47 | 0.897 | 17/21 | 10.0 (26) | 0.13 / 0.34 / 0.46 |
| v3-bug | 직선 | 0.44 | 0.961 | 0.83 | 0.443 | 0.45 | 0.884 | 17/21 | 8.8 (23) | 0.16 / 0.38 / 0.53 |
| v3m | 직선 | 0.33 | 0.940 | 0.75 | 0.593 | 0.35 | 0.888 | 17/21 | 2.7 (7) | 0.10 / 0.10 / 0.02 |
| v2 | MLP 시드 0 | 0.56 | 0.964 | 0.86 | 0.225 | 0.49 | 0.858 | 17/21 | 8.0 (21) | 0.31 / 0.38 / 0.47 |
| v2 | MLP 시드 1 | 0.57 | 0.955 | 0.82 | 0.282 | 0.49 | 0.868 | 17/21 | 11.1 (29) | 0.30 / 0.52 / 0.41 |
| v3-bug | MLP 시드 0 | 0.52 | 0.965 | 0.85 | 0.297 | 0.48 | 0.869 | 18/21 | 9.6 (25) | 0.29 / 0.22 / 0.61 |
| v3-bug | MLP 시드 1 | 0.45 | 0.960 | 0.80 | 0.334 | 0.43 | 0.853 | 18/21 | 7.3 (19) | 0.20 / 0.41 / 0.47 |
| v3m | MLP 시드 0 | 0.28 | 0.953 | 0.69 | 0.607 | 0.30 | 0.881 | 16/21 | 3.1 (8) | 0.09 / 0.16 / 0.01 |
| v3m | MLP 시드 1 | 0.38 | 0.951 | 0.81 | 0.599 | 0.36 | 0.890 | 17/21 | 3.8 (10) | 0.07 / 0.08 / 0.07 |

## 오탐 범주 (5 fold 합, 클립 수)

| 데이터 | 분류기 | 오탐 범주 |
| --- | --- | --- |
| v2 | 직선 | insects 4, vacuum_cleaner 3, chirping_birds 2, washing_machine 2, airplane 2, chainsaw 2, door_wood_creaks 2, can_opening 1 |
| v3-bug | 직선 | vacuum_cleaner 5, washing_machine 4, airplane 3, chainsaw 2, chirping_birds 1, rain 1, car_horn 1, siren 1 |
| v3m | 직선 | vacuum_cleaner 2, washing_machine 2, car_horn 1, mouse_click 1, crackling_fire 1 |
| v2 | MLP 시드 0 | insects 4, chirping_birds 3, vacuum_cleaner 3, washing_machine 3, airplane 3, door_wood_creaks 2, car_horn 1, chainsaw 1 |
| v2 | MLP 시드 1 | insects 5, chirping_birds 4, vacuum_cleaner 3, washing_machine 3, can_opening 2, car_horn 2, siren 2, snoring 1 |
| v3-bug | MLP 시드 0 | airplane 5, insects 4, washing_machine 3, chainsaw 3, siren 2, chirping_birds 1, car_horn 1, rain 1 |
| v3-bug | MLP 시드 1 | insects 4, washing_machine 3, airplane 2, chainsaw 2, chirping_birds 1, car_horn 1, rain 1, vacuum_cleaner 1 |
| v3m | MLP 시드 0 | insects 2, washing_machine 2, chirping_birds 1, door_wood_creaks 1, crackling_fire 1, airplane 1 |
| v3m | MLP 시드 1 | washing_machine 3, chirping_birds 2, insects 2, helicopter 1, crackling_fire 1, airplane 1 |
