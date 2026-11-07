# Turret — 음향 드론 탐지·방향 모듈

STM32F446RE + MAX4466 마이크 4개로 소리의 방위·고도각을 재고, PC의 학습 분류와 결합해 카메라를 돌리는 설치형 탐지 모듈. 대상은 소형 고정익 정찰 무인기다.

## 구조

```
Turret/
├─ Core/              펌웨어 (app/ = 직접 쓴 코드, Src·Inc = CubeMX)
├─ Tools/             PC 도구 (<영역>/*.py) · 녹음 (dumps/, git 밖) · .venv
├─ reports/           스크립트가 만든 출력 (수치)
├─ config/            마이크 좌표·채널 지연, 전처리 설정
├─ hardware/          기구 설계·사진
└─ data/              데이터셋 목록·split (원본 DataSet/은 git에 올리지 않음)
```
