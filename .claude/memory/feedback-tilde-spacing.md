---
name: feedback-tilde-spacing
description: "md에서 범위는 \"A ~ B\"처럼 물결표 앞뒤에 공백. \"A~B\"는 같은 줄의 다른 ~와 짝지어 취소선이 됨"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 22b71e3d-c38f-4a45-b943-59b7839e02f2
  modified: 2026-10-22T12:04:06.833Z
---

Markdown에 범위를 쓸 때 물결표 앞뒤를 한 칸씩 띄운다: `150 ~ 2000 Hz`, `ADC1 ~ 3`, `+2 ~ +24°`.

**Why:** GitHub·VS Code 미리보기는 물결표 하나(`~text~`)도 취소선으로 처리해서, 한 줄에 `A~B`가 두 번 나오면 그 사이가 취소선이 됐다. 2026-10-22 사용자가 지적해 저장소의 md 전체(117줄)를 고쳤다.

**How to apply:** 새로 쓰는 md, 표, 결정 기록, 보고서 생성 스크립트(`reports/` md를 만드는 Python의 f-string 포함)에서 `A~B`를 쓰지 않는다. 코드 블록·인라인 코드·URL 안은 예외.
