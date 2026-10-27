---
name: project-product-direction
description: "Turret product direction set 2026-10-26 — target small fixed-wing recon UAV, fixed-site area defense, existing hardware only, low-cost embedded product"
metadata:
  node_type: memory
  type: project
  originSessionId: 470d7d64-0cf0-4834-97c1-a647e6464cf6
  modified: 2026-10-26T06:07:43.497Z
---

2026-10-26 사용자 결정, 2026-10-27 문서 반영 (problem.md 대상 줄·비목표, decision.html D4-3, Step8c·parameter 고정익 숫자):
- 대상: 소형 고정익 정찰 무인기 (2014·2017·2022 북한 침투형 급). FPV는 대상에서 내림. 대형(샛별)은 범위 밖
- 형태: 설치형 지역 방위
- 자원: 기존 마이크·배열만 (STM32F446 Nucleo, MAX4466 마이크 3개, 현재 배열). 마이크 추가·고성능 마이크는 고려하지 않음. **2026-10-27 정정:** PC 자리는 라즈베리파이·젯슨이 대신할 수 있고 카메라도 거기서 돌린다 → SBC는 허용, 'PC 상시 처리 배제'는 철회
- 목표: 비용 효율 좋은 저가 임베디드 제품

**Why:** 예산 제약과 실제 도입 시나리오(저가 임베디드)를 우선한다.
**How to apply:** 제안할 때 마이크 쪽 하드웨어 추가를 해법으로 내지 말 것. 판정 경로에 SBC(라즈베리파이·젯슨)가 들어가는 것은 괜찮다. 소프트웨어·배치·기구(방풍재 등) 개선과 MCU에서 도는 방법(고조파 센서, KF 추적 등)을 우선. 그 밖의 problem.md·decision.html 수정은 사용자가 요청할 때만. ([[knowledge-checkpoint-protocol]] 와 별개).
