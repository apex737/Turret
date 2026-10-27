---
name: knowledge-checkpoint-protocol
description: 점검은 learning/GUIDE.md v2.5 트리거(T1 ~ T4, R 복습)에서만. 틀린 개념만 learning/concepts.json에 기록, 교재는 만들지 않음
metadata:
  node_type: memory
  type: feedback
  originSessionId: 470d7d64-0cf0-4834-97c1-a647e6464cf6
  modified: 2026-10-27T01:47:52.868Z
---

`learning/GUIDE.md` v2.5를 따른다 (전역 사본 `~/.claude/learning-dev-guide.md`도 v2.5, 2026-10-27 맞춤). 트리거와 예산은 GUIDE 4절이 원본이고, 요약은 [[user-junior-wants-to-learn]].

- 문항: 서술형, 프로젝트 실제 숫자, 힌트·객관식 없음, 채점 기준을 답 보기 전에 정함, "모름도 답이다, 확신 상/중/하". 면접관 질문 형태 ([[user-career-goal]]).
- 채점: 대화에서 ✅ △ ❌ ⚠ + 맞은 것 / 빠진 것. △/❌/⚠ 개념만 `learning/concepts.json`에 기록 (concepts.html은 보는 UI). 기록 전에 바로 아래 기초를 먼저 확인해 가장 낮은 빈칸을 적는다.
- `wrong_count`는 AI만 올리고 줄이지 않는다. understood는 R 복습에서 맞혔을 때만 AI가 true로.
- 문항과 답은 파일에 남기지 않는다.

**Why:** 2026-10-22 사용자 결정. 이해 점검은 중요하지만 AI가 쓴 보충 교재는 선행 개념이 끝없이 이어지고(FFT → DFT → DTFT …) 수준도 안 맞아 효과가 없었다. background.html·퀴즈 파일 폐기.

**How to apply:** 교재·도우미 페이지·개념 설명 아티팩트를 만들지 않는다. concepts 항목을 지우지 않는다 (제거는 사용자). 답이 없는 T2/T3 결정은 적용하지 않는다. Step 상태는 구현 통과 + 남은 concepts 항목 수 두 가지로 보고. 배경 수준은 [[user-background-level]].
