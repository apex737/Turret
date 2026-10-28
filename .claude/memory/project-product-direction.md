---
name: project-product-direction
description: "Turret product direction — small fixed-wing recon UAV, fixed-site area defense, existing 3 mics + 1 out-of-plane elevation mic (2026-10-28), low-cost embedded, SBC ok"
metadata:
  node_type: memory
  type: project
  originSessionId: 470d7d64-0cf0-4834-97c1-a647e6464cf6
  modified: 2026-10-28T14:54:01.418Z
---

2026-10-26 사용자 결정, 2026-10-27 문서 반영 (problem.md 대상 줄·비목표, decision.html D4-3):
- 대상: 소형 고정익 정찰 무인기 (2014·2017·2022 북한 침투형 급). FPV는 대상에서 내림. 대형(샛별)·자폭드론은 범위 밖
- 형태: 설치형 지역 방위. 음향 모듈 = 카메라를 돌려 주는 **큐잉 센서** (판별은 카메라, 유인기는 소리로 못 거름)
- 자원: STM32F446 Nucleo + MAX4466 3개(평면, 70 mm 정삼각형) **+ 고도각용 평면 밖 MAX4466 1개** (2026-10-28, D8c-2, 브랜치 `four-mic`, Step8e). 고성능 마이크·여러 개 추가는 여전히 범위 밖. PC 자리는 라즈베리파이·젯슨이 대신 가능 (SBC 허용)
- 목표: 비용 효율 좋은 저가 임베디드 제품, 포트폴리오로는 "예측 → 실측 → 원인 → 설계 변경" 사례가 핵심

**Why:** 평면 3마이크 norm으로 고도 0 ~ 24°를 가르지 못한 실측(elev_real, 2026-10-28) 뒤 사용자가 4마이크로 전략 수정. 지나가는 차를 거를 유일한 단서가 고도각.
**How to apply:** 마이크 추가 제안은 이 1개 외에는 하지 말 것. 소프트웨어·배치·기구 개선과 MCU에서 도는 방법을 우선. problem.md·decision.html 수정은 사용자가 요청할 때만. ([[knowledge-checkpoint-protocol]] 와 별개).
