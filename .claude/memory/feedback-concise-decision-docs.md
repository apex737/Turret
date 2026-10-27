---
name: feedback-concise-decision-docs
description: 설계 결정은 방향·성패를 좌우하는 것만 짧게. 결정 기록은 루트 decision.html (버린 길 흐리게, 클릭 시 이유). Mermaid 금지
metadata:
  node_type: memory
  type: feedback
  originSessionId: eed15040-5a5f-4fee-9360-60e3313a6eac
  modified: 2026-10-19T22:40:16.880Z
---

설계 결정 기록은 프로젝트의 방향이나 성패를 크게 좌우하는 결정만 간소하게 적는다. 분기점에는 반드시 실제로 검토한 선택지가 둘 이상 있어야 한다.

**시각화 규칙 (2026-10-20 사용자 결정):** Mermaid는 쓰지 않는다. 그림은 HTML 애니메이션으로만 통일한다. 계기: Step4 이후 결정 트리를 Mermaid 한 장에 넣었더니 글자가 안 보일 만큼 작아짐. **2026-10-22: 결정 기록 전체가 루트 `decision.html` 하나** (decisions.md 삭제). 사용자 요구: 버린 경로는 opacity를 낮추고, 노드를 클릭했을 때만 왜 버렸나/왜 채택했나를 띄우는 반응형 트리 — 아래로 설명을 늘어놓아 문서가 길어지는 단점을 이걸로 보완한다 (profile.md 시각화 선호).

**Why:** 2026-10-11에 28개짜리 초안을 보고 사용자가 지적함. "2-1~3이 너무 장황하다 (HW 제약상 당연히 가장 빠른 보레이트 + TX DMA)", "CMSIS-DSP 파일 고르기 같은 건 설계 결정이라 하기 힘들다", "앞 결정에서 따라오는 것은 따로 세우지 말 것". 2026-10-20: 결정 트리는 버린 이유, 고른 이유, 실패 시 되돌아갈 곳이 한눈에 보여야 한다고 요구.

**How to apply:**
- HW 제약에서 당연히 나오는 선택, 구현 세부, 앞 결정의 귀결은 독립 항목으로 만들지 않는다.
- 결정 하나 = 선택 / 버림(이유) / 근거 / 실패 신호 → 백트래킹 대상.
- 새 결정이 생기면 루트 `decision.html`의 `D` 배열에 한 항목 추가 (형식은 README 4절). 다른 문서에서는 `decision.html#D7-1`로 링크. 설명문을 화면에 펼쳐 두지 말고 클릭 시에만.
- 다시 볼 결정·진행 중 표시는 주황 하나만 쓴다.
- Step 문서에 새 Mermaid를 넣지 않는다. 필요한 그림은 HTML(helper 또는 decision.html)로.

관련: [[workflow-baseline-pivoting]], [[user-junior-wants-to-learn]], [[feedback-lean-step-docs]]
