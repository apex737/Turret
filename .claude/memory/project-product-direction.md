---
name: project-product-direction
description: "Turret product direction set 2026-10-26 — target small fixed-wing recon UAV, fixed-site area defense, existing hardware only, low-cost embedded product"
metadata:
  node_type: memory
  type: project
  originSessionId: 470d7d64-0cf0-4834-97c1-a647e6464cf6
  modified: 2026-10-26T06:07:43.497Z
---

2026-10-26 사용자 결정 (대화에서, 저장소 문서에는 아직 반영 안 함):
- 대상: 소형 고정익 정찰 무인기 (2014·2017·2022 북한 침투형 급). FPV는 대상에서 내림. 대형(샛별)은 범위 밖
- 형태: 설치형 지역 방위
- 자원: 기존 보유 자원만 (STM32F446 Nucleo, MAX4466 마이크 3개, 현재 배열). 마이크 추가·고성능 마이크·추가 처리장치는 고려하지 않음
- 목표: 비용 효율 좋은 저가 임베디드 제품

**Why:** 예산 제약과 실제 도입 시나리오(저가 임베디드)를 우선한다.
**How to apply:** 제안할 때 하드웨어 추가·SBC·PC 상시 처리를 해법으로 내지 말 것. 소프트웨어·배치·기구(방풍재 등) 개선과 MCU에서 도는 방법(고조파 센서, KF 추적 등)을 우선. problem.md·decision.html 수정은 사용자가 요청할 때만 ([[knowledge-checkpoint-protocol]] 와 별개).
