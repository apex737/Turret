# Turret — 음향 드론 탐지·방향 모듈

STM32F446RE + MAX4466 마이크 4개로 소리의 방위·고도각을 재고, PC의 학습 분류와 결합해 카메라를 돌리는 설치형 탐지 모듈. 대상은 소형 고정익 정찰 무인기다.

- 목표(G)·우선순위(P)·불변 조건(I)·Step 계획: [GUIDE/project/project.md](GUIDE/project/project.md)
- 결정 기록: [GUIDE/project/decisions.html](GUIDE/project/Docs/decisions.html) · 튜닝 값: [GUIDE/project/params.html](GUIDE/project/Docs/params.html) · 함수 흐름: [GUIDE/project/FlowChart.html](GUIDE/project/Docs/FlowChart.html) (VS Code Live Preview 같은 로컬 서버로 열면 JSON을 자동으로 읽는다)
- 개발 방식(학습형, AI와 함께): [GUIDE/README.md](GUIDE/README.md) — AI는 루트 [CLAUDE.md](CLAUDE.md)를 따른다

## 구조

```
Turret/
├─ CLAUDE.md          학습형 개발 공통 규칙 (AI). GUIDE/의 프로필·트랙 지침을 함께 읽는다
├─ GUIDE/             학습·기록 — 무엇을 어디에 둘지는 GUIDE/project/project.md 3절
│  ├─ README.md       사람용 안내 (내가 쓰는 말, 페이지 쓰는 법)
│  ├─ profile.md      나: 배경·목표 직무·프로젝트 이력 (모든 프로젝트 공통)
│  ├─ concepts.json   점검에서 틀린 개념 (보기 concepts.html, 기록 tools/concepts.py)
│  ├─ project/        project.md · Steps/StepN.md + logs/ · notebooks/(근거 노트북)
│  │                  Docs/ — decisions · params · FlowChart 페이지, interfaces.html(MCU ↔ PC 약속) · firmware.html(MCU 내부) · run.md(실행 절차)
│  ├─ practice/       실습 트랙 (지침과 목록)
│  ├─ notes/          본인이 쓴 개념 노트·강의 노트북
│  ├─ TIL/            본인이 쓴 하루 개발 흐름 (AI는 사실 오류만 고친다)
│  └─ references/     강의자료 (비공개, git에 올리지 않음)
├─ reports/           스크립트가 만든 출력 (수치만, 판정은 Step 파일에)
├─ Core/              펌웨어 (app/ = 직접 쓴 코드, Src·Inc = CubeMX)
├─ Tools/             PC 도구 (<영역>/*.py) · 녹음 (dumps/, git 밖) · .venv
├─ config/            마이크 좌표·채널 지연, 전처리 설정
├─ hardware/          기구 설계·사진
└─ data/              데이터셋 목록·split (원본 DataSet/은 git에 올리지 않음)
```

검사: `python GUIDE/tools/concepts.py check` (개념·결정·값·Step 기록의 형식과 서로 맞는지).
