# Turret — 작업물 정리 지침

> 사람과 AI 모두 읽는다. 문서를 새로 만들거나 옮길 때 이 파일의 구조와 규칙을 따른다.
> 학습 방식(문항, 채점, 진행 차단)은 `learning/GUIDE.md`가 정한다. 이 파일은 **무엇을 어디에 두는가**만 정한다.

---

## 1. 구조

```
Turret/
├─ README.md          이 파일. 구조와 정리 규칙
├─ problem.md         전역 목표(G)·우선순위(P)·불변조건(I). 1페이지. 세션 시작 시 가장 먼저 읽는다
├─ decisions.md       결정 로그. 결정마다 4문 레코드 (4절)
├─ flow.html          Step 흐름도. 생성물이므로 직접 고치지 않는다 (5절)
├─ migration.md       2026-10-22 구조 개편 때 이전 문서의 각 절이 어디로 갔는지 (1회성 기록)
│
├─ Steps/             Step마다 파일 하나 = 관문 기록 (질문과 답, 기준, 결과, 할 일)
│  ├─ Step1.md … Step4.md, Step5pre.md, Step5.md … Step8.md, Step9A.md, Step10.md, Step9B.md, Step11.md
│  └─ logs/           반복 실험의 경과. 필요한 Step만 (예: logs/Step8.md)
│
├─ docs/              코드와 함께 바뀌는 것
│  ├─ protocol.md     PC와 MCU가 맞춰야 하는 약속: 패킷 형식, CRC, 시간축, 스케일
│  ├─ firmware.md     모듈 구조, 동작 모드, 빌드·IDE 설정, CubeMX 주의사항
│  └─ run.md          두 번 이상 실행하는 절차: 배치 방법, 녹음·분석 명령
│
├─ learning/          학습 기록
│  ├─ GUIDE.md        학습형 개발 지침
│  ├─ profile.md  concepts.md  quiz.md
│  ├─ background.html 보완 교재. 수준 확인을 거쳐 AI가 만든다 (GUIDE.md 교재 절)
│  └─ notes/          본인이 쓴 개념 노트, 시각 자료(helper html)
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
| 여러 선택지 중 하나를 고른 것인가? | `decisions.md` |
| 둘 이상의 Step이 쓰는 개념인가? | `learning/concepts.md` (ID와 판정만) |
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
7. **통과 기준은 실험 전에 확정하고 날짜를 적는다.** 결과를 본 뒤 바꾸면 decisions.md에 이유를 남긴다.
8. **AI가 쓴 개념 설명은 Step·docs·decisions에 남기지 않는다.** 개념은 `learning/concepts.md`에 ID로 올리고 문항으로 확인한다. AI가 만드는 교재는 `learning/background.html` 한 곳에만 두고, 만들 때마다 대상 개념의 수준을 먼저 확인한다 (질의 또는 시험 결과, `learning/GUIDE.md` 교재 절). `notes/`에는 본인이 쓴 것만 둔다.
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
status: {impl: 통과, explain: 0/3}   # impl: 대기 | 진행 | 미통과 | 통과
---

## 질문과 답
**Q.** (이 Step이 답할 질문 한 줄 = 중간 목표)

**A. (한 줄 결론: 예 / 아니오 / 아직 모름 / 고른 답).** (핵심 숫자와 기준 1~2문장. 숫자는 아래 결과 표에 근거가 있어야 한다)

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

## 의존 개념
| ID | 개념 | 판정 |
|---|---|---|

## 남은 일
- [ ] …

## 관련 결정
- D7-1 (decisions.md)
```

`explain`은 의존 개념 중 ✅ 개수 / 전체다. 진단 전이면 `0/N`.

### decisions.md

```markdown
### D7-1 배경 교차 스펙트럼 빼기(D1) 채택  · Step7 · 2026-10-16
- 버린 선택지·이유:
- 근거 숫자:
- 대가:
- 다시 결정할 조건:
- 영향: (G·P·I 중 무엇에) · 원인 수정 / 증상 수정
- 기대는 개념: (ID와 판정)
```

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
- Step 파일을 고쳤으면 다시 실행한다.
