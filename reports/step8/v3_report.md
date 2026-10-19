# Step8 v3 — FSD50K 어려운 비드론 추가 (CNN14 임베딩 + 로지스틱 회귀, 기체 하나씩 빼는 5-fold)

> `Tools/ml/train_v3.py`가 만든 파일. FSD50K(곤충·새·전동공구·엔진·항공기 등 1,070 클립)와 새 FPV는 학습 전용이고 시험 데이터는 v0과 같다.
> 문턱: 학습 데이터 안 교차검증에서 비드론 창 오탐 1%. 사건·클립 판정은 연속 3창 중 2창.

| 설정 | FPV 창 재현율 | FPV 창 AUC | FPV 대 곤충 AUC | Matrice 통과 AUC | 5기종 평균 창 재현율 | 평균 창 AUC | 사건 (2-of-3) | 오탐/시간 (클립) | 장치 경로 재현율 (FPV / Mini3 / Air3) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v2 | 0.43 | 0.956 | 0.75 | 0.446 | 0.47 | 0.897 | 17/21 | 10.0 (26) | 0.13 / 0.34 / 0.46 |
| v3 | 0.33 | 0.953 | 0.74 | 0.447 | 0.37 | 0.878 | 17/21 | 4.2 (11) | 0.06 / 0.15 / 0.11 |
| v3-bug | 0.44 | 0.961 | 0.83 | 0.443 | 0.45 | 0.884 | 17/21 | 8.8 (23) | 0.16 / 0.38 / 0.53 |
| v3m | 0.33 | 0.940 | 0.75 | 0.593 | 0.35 | 0.888 | 17/21 | 2.7 (7) | 0.10 / 0.10 / 0.02 |

## 오탐 범주 (5 fold 합, 클립 수)

| 설정 | 오탐 범주 |
| --- | --- |
| v2 | insects 4, vacuum_cleaner 3, chirping_birds 2, washing_machine 2, airplane 2, chainsaw 2, door_wood_creaks 2, can_opening 1, rain 1, car_horn 1 |
| v3 | insects 4, washing_machine 3, chirping_birds 1, vacuum_cleaner 1, siren 1, snoring 1 |
| v3-bug | vacuum_cleaner 5, washing_machine 4, airplane 3, chainsaw 2, chirping_birds 1, rain 1, car_horn 1, siren 1, door_wood_creaks 1, insects 1 |
| v3m | vacuum_cleaner 2, washing_machine 2, car_horn 1, mouse_click 1, crackling_fire 1 |
