# ML_Classifier — 드론 분류(Step6·8)에 쓰인 머신러닝 공부 자료

강의 노트북 가운데 이 프로젝트의 분류 작업과 맞닿는 것만 남겼다. 파일 이름은 원본 그대로다 (Easy = 이론, 실습-문제 / 과제-문제 = 연습).

| 폴더 | 다루는 것 | 프로젝트에서 쓰인 곳 |
| --- | --- | --- |
| `01_분류모델_평가/` | 로지스틱 회귀, 표준화, train/test 분할·교차검증·데이터 누수, 평가 지표 | Step6 split·평가 규칙, Step8 v0 `train_v0.py` (StandardScaler + LogisticRegression) |
| `02_MLP_PyTorch/` | 퍼셉트론·MLP, PyTorch 학습 루프 | Step8 v4 `train_v4.py` MLP 분류기 (D8-5에서 기각), CNN14가 PyTorch 모델 |
| `03_임베딩_유사도/` | 임베딩 벡터, 임베딩 위의 분류, Cos 유사도 (토큰화 부분은 NLP용) | Step8 CNN14 임베딩 + 분류기 (D8-1), v2 `fpv_candidates.py` 코사인 유사도로 FPV 후보 정렬 |
| `04_전이학습_증강/` | Fine-tuning·Linear Probing, 도메인 차이, 데이터 증강 | Step8 고정 임베딩 + 직선 분류기(= Linear Probing), v1 증강, v5 장치 경로 |

뺀 것 (2026-10-23): 토큰화·RNN·Attention 실습, LLM 데이터 생성, Transformer·멀티모달, LangGraph·RAG·에이전트, LLM PEFT·양자화 — 이 프로젝트에서 쓰지 않는다.
