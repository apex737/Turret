# Step8 v5 — 장치 경로 녹음 추가 (CNN14 임베딩 + 로지스틱 회귀, 기체 하나씩 빼는 5-fold)

> `Tools/ml/train_v5.py`가 만든 파일. 장치 경로 = 노트북 스피커 → MAX4466 → 보드 STREAM (`30_devpath_A·B`).
> 문턱: 학습 데이터 안 교차검증에서 비드론 창 오탐 0.5% (채택 운용점). 사건·클립·구간 판정은 연속 3창 중 2창.

| 설정 | 공개: FPV 창 재현율 | 공개: FPV 사건 | 공개: 사건 | 공개: 오탐/시간 | 장치: FPV 창 재현율 | 장치: FPV 20 s 구간 검출 | 장치: Mini3 / Air3 창 재현율 | 장치: 오탐/시간 (ESC 클립) | 장치: 창 오탐률 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v3m | 0.22 | 3/3 | 17/21 | 0.77 (2) | 0.05 | 6/18 | 0.06 / 0.01 | 82.3 (12/0.15 h) | 0.068 |
| v5p | 0.32 | 3/3 | 16/21 | 1.15 (3) | 0.14 | 12/18 | 0.08 / 0.02 | 130.3 (19/0.15 h) | 0.096 |
| v5 | 0.24 | 3/3 | 15/21 | 0.77 (2) | 0.07 | 7/18 | 0.00 / 0.00 | 34.3 (5/0.15 h) | 0.042 |

## 장치 경로 오탐 범주 (5 fold 합, 클립 수)

| 설정 | 범주 |
| --- | --- |
| v3m | sneezing 2, drinking_sipping 2, clock_alarm 1, breathing 1, can_opening 1, door_wood_knock 1, washing_machine 1, coughing 1, glass_breaking 1, rooster 1 |
| v5p | door_wood_knock 2, washing_machine 2, drinking_sipping 2, clock_alarm 1, sea_waves 1, breathing 1, train 1, pouring_water 1, can_opening 1, cat 1 |
| v5 | breathing 1, can_opening 1, door_wood_knock 1, washing_machine 1, sneezing 1 |
