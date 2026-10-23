# Turret — 작업물 정리 지침

> 사람과 AI 모두 읽는다. 문서를 새로 만들거나 옮길 때 이 파일의 구조와 규칙을 따른다.
> 학습 방식(문항, 채점, 진행 차단)은 `learning/GUIDE.md`가 정한다. 이 파일은 **무엇을 어디에 두는가**만 정한다.

---

## 1. 구조

```
Turret/
├─ README.md          이 파일. 구조와 정리 규칙
├─ problem.md         전역 목표(G)·우선순위(P)·불변조건(I). 1페이지. 세션 시작 시 가장 먼저 읽는다
├─ decision.html      결정 트리. 버린 선택지는 흐리게, 누르면 이유가 뜬다. 결정마다 4문 레코드 (4절)
├─ flow.html          Step 흐름도. 생성물이므로 직접 고치지 않는다 (5절)
│
├─ Steps/             Step마다 파일 하나 = 관문 기록 (질문과 답, 기준, 결과, 할 일)
│  ├─ Step1.md … Step4.md, Step5pre.md, Step5.md … Step8.md, Step9A.md, Step10.md, Step9B.md, Step11.md
│  └─ logs/           반복 실험의 경과. 필요한 Step만 (예: logs/Step8.md)
│                     (Step 파일의 "이전 판 N절"은 `FPV_Target` 브랜치의 원본 Step 문서를 가리킨다)
│
├─ docs/              코드와 함께 바뀌는 것
│  ├─ interfaces.html MCU ↔ PC 경계의 약속: 패킷 형식(바이트 배치)·의미(스케일·시간축·플래그)·규칙(파서·끊김), 같이 고칠 짝
│  ├─ firmware.html   MCU 내부 구조: 모듈, 데이터 흐름, 클럭, DMA 핑퐁, 송신 큐, 방향 계산, 메모리·CPU, 빌드·CubeMX
│  ├─ parameter.html  튜닝 파라미터의 값·근거·실험 결과·검증할 것 (원본 parameter.json, 화면에서 편집 후 내보내기)
│  └─ run.md          두 번 이상 실행하는 절차: 배치 방법, 녹음·분석 명령
│
├─ learning/          학습 기록
│  ├─ GUIDE.md        학습형 개발 지침
│  ├─ profile.md      학습자 배경 (모든 프로젝트 공통)
│  ├─ concepts.html   점검에서 틀린 개념: 키워드·간략 설명·쓰인 Step. 이해 표시·제거는 사람이 직접
│  └─ notes/          본인이 쓴 개념 노트, 시각 자료(helper html)
│     └─ ML_Classifier/ 드론 분류(Step6·8)에 쓰인 머신러닝 강의 노트북만 골라 둔 공부 자료
│
├─ reports/           스크립트가 만든 출력 (표, 그래프). 판정은 쓰지 않는다
├─ Tools/flow/        gen_flow.py, flow_template.html
├─ hardware/          기구 설계·사진 (enclosure_v0 사진, enclosure_v1 STL/STEP·생성 스크립트)
└─ Core/ Drivers/ Tools/ config/ DataSet/ …   코드와 데이터
```

---

## 2. 어디에 둘까

위에서부터 처음 해당하는 곳에 둔다.

| 질문 | 위치 |
|---|---|
| 스크립트가 만든 출력인가? | `reports/` |
| 코드가 바뀌면 같이 바뀌어야 하는가? | `docs/` |
| 두 번 이상 실행할 절차인가? | `docs/run.md` |
| 여러 선택지 중 하나를 고른 것인가? | `decision.html` |
| 점검에서 틀린 개념인가? | `learning/concepts.html` (키워드·간략 설명·쓰인 Step) |
| 반복 실험에서 무슨 일이 있었나? (날짜, 결과, 해석) | `Steps/logs/StepN.md` |
| 그 Step의 질문, 기준, 판정, 할 일인가? | `Steps/StepN.md` |
| 프로젝트 전체의 목표·제약인가? | `problem.md` |

헷갈리는 짝:

- **run.md와 logs/**: 레시피와 요리 일지. run.md는 "어떻게 돌리나"를 최신판 하나로 고쳐 쓰고, logs/는 "돌렸더니 어땠나"를 날짜순으로 덧붙이기만 한다.
- **reports/와 Step 결과**: 증거와 판결. reports/는 스크립트가 만든 전체 수치이고, Step 결과는 기준 대비 판정과 핵심 숫자 몇 개다. Step의 숫자는 reports/의 파일로 거슬러 갈 수 있어야 한다.

---

## 3. 규칙

1. **Step 파일은 80줄 이내.** 넘으면 실험 경과를 `logs/`로 옮기고 본문에는 버전당 한 줄만 남긴다.
2. **같은 내용은 한 곳에만.** 다른 곳에서는 링크한다.
3. **할 일은 그 일을 처리할 Step 파일에만.** 다른 Step으로 넘길 때는 복사하지 않고 옮긴다 (원래 Step에서 지운다).
4. **둘 이상의 Step이 쓰는 사양·개념은 Step 파일에 두지 않는다.**
5. **docs/는 코드와 같은 커밋에서 고친다.** 코드가 원본이고 docs/는 참고표다.
6. **Step 결과의 숫자에는 근거 링크(reports/ 파일)를 단다.** reports/에는 판정을 쓰지 않는다.
7. **통과 기준은 실험 전에 확정하고 날짜를 적는다.** 결과를 본 뒤 바꾸면 decision.html에 이유를 남긴다.
8. **AI가 쓴 개념 설명·교재는 남기지 않는다.** 트리거 점검(`learning/GUIDE.md` 4절)에서 틀린 개념만 `learning/concepts.html`에 키워드·간략 설명·쓰인 Step으로 올린다. 문항과 답은 파일로 남기지 않는다. `notes/`에는 본인이 쓴 것만 둔다.
9. **Step ID는 바꾸지 않는다.** 사이에 끼울 때는 `Step5b`처럼 붙인다. 순서는 `depends_on`이 정한다.
10. **상태는 Step frontmatter에만 적는다.** 본문이나 다른 파일에 상태 단어(대기·진행·미통과·통과)를 따로 쓰지 않는다. `질문과 답`의 답은 상태가 아니라 질문에 대한 답(예 / 아니오 / 아직 모름 + 핵심 숫자)이다.
11. **측정하지 않은 것은 "미측정"으로 둔다.** 부족한 것을 통과로 표시하지 않는다.

---

## 4. 파일 형식

### problem.md

```markdown
---
project: Turret
goals:
  G1: (최종 목표, 측정 가능한 형태)
priorities:
  P1: (충돌 시 이기는 순서대로)
invariants:
  I1: (깨면 안 되는 것)
---

# 문제 정의
## 한 줄 요약
## 비목표
## 파츠 등급        구현 / 설명 / 블랙박스, 이유 한 줄
## 변경 이력        날짜 · 무엇을 왜
```

### Steps/StepN.md

파일 이름은 `id`와 같아야 한다 (`Step7.md`의 id는 `Step7`).

```markdown
---
id: Step7
title: 지속음 방향 추정
depends_on: [Step5, Step6]
goal_ref: [G2]                 # problem.md의 ID. G를 하나 이상 반드시 포함
exit: "유효 방위 오차 중앙 ≤ 5°, p95 ≤ 10°, 유효율 ≥ 80%"
on_fail: null                  # 기준 미달 시 돌아갈 Step
status: {impl: 통과}   # impl: 대기 | 진행 | 미통과 | 통과
---

## 질문과 답
**Q.** (이 Step이 답할 질문 한 줄 = 중간 목표)

**A. (한 줄 결론: 예 / 아니오 / 아직 모름 / 고른 답).** (핵심 숫자와 기준 1 ~ 2문장. 숫자는 아래 결과 표에 근거가 있어야 한다)

## 최종 목표와의 연결
- G2: (어떻게 기여하는지 한 줄)

## 통과 기준 (YYYY-MM-DD 확정)
| 항목 | 기준 | 측정 조건 |
|---|---|---|

## 결과
| 항목 | 실측 | 판정 | 날짜 | 근거 |
|---|---|---|---|---|

## 파라미터 (있을 때)
| 이름 | 현재 값 | 근거 |
|---|---|---|

## 남은 일
- [ ] …

## 관련 결정
- [D7-1](../decision.html#D7-1)
```

### decision.html

결정 하나 = 파일 안 `D` 배열의 한 항목. 화면(트리, 흐리게, 누르면 뜨는 설명)은 자동으로 만들어진다. 다른 문서에서는 `decision.html#D7-1`로 링크하면 그 결정의 설명이 열린 채로 뜬다.

```js
{id:"D7-1", step:"Step7", date:"2026-10-16", q:"지속음 방향 방식은?",
 o:[{k:"c", n:"D1: GCC-PHAT + 배경 교차 스펙트럼 빼기"},          // k: c 채택 · cf 채택→실패 · cur 진행 중
    {k:"f", n:"D0: 배경 빼기 없음", w:"버린 이유"},                //    f 시도·실패 · r 버림 · h 보류 · n 다음 후보 · a 실패 시 대안
    {k:"h", n:"D2: SRP-PHAT", w:"보류 이유"}],
 why:"{시뮬레이션} 근거 숫자",  cost:"대가",  redo:"다시 결정할 조건",
 eff:"G1 · 원인 수정",  con:"기대는 개념 (ID와 판정)"}
```

- 근거 표시는 `{실측}` `{시뮬레이션}` `{계산}` `{논리}` `{기록 없음}`, 링크는 `[글](주소)`로 쓴다.
- 열린 결정(사용자)은 `open:true`, 선택지는 `k:"oo"`.

### Steps/logs/StepN.md

```markdown
## v3 — FSD50K 어려운 비드론 추가 (2026-10-19)
- 바꾼 것:
- 결과: (핵심 숫자, 근거 reports/ 링크)
- 해석:
- 다음:
```

---

## 5. flow.html 만들기

```
pip install pyyaml markdown
python Tools/flow/gen_flow.py .
```

- `problem.md`와 `Steps/*.md`의 frontmatter를 읽어 루트에 `flow.html`을 만든다.
- 다음이면 실패하고 HTML을 만들지 않는다: G와 연결되지 않은 Step, 비어 있는 `exit`, 없는 ID를 가리키는 `goal_ref`·`depends_on`·`on_fail`, 순환.
- 어떤 Step도 검증하지 않는 G·I는 경고로 알린다.
- **누가 언제:** `problem.md`나 `Steps/*.md`를 고친 쪽(사람이든 AI든)이 커밋 전에 실행한다. 흐름도를 만드는 동시에 위 규칙을 검사하므로, 직접 고친 뒤 한 번 돌려 보면 규칙을 어겼는지 바로 안다.
- `Tools/.venv`의 파이썬으로 실행한다 (`Tools\.venv\Scripts\python.exe Tools/flow/gen_flow.py .`). 다른 파이썬에서 패키지가 없으면 그렇다고 알려 준다.
