---
name: project-goal-drone-detection
description: "Turret 프로젝트의 최종 검출 대상은 비행체(드론). TDoA는 카메라를 그쪽으로 빠르게 돌리는 단서이고, 카메라와 퓨전해 락온하는 구조"
metadata:
  node_type: memory
  type: project
  originSessionId: eed15040-5a5f-4fee-9360-60e3313a6eac
  modified: 2026-10-27T01:48:07.624Z
---

사용자가 2026-10-11에 밝힌 프로젝트 구상.

- **최종 검출 대상은 비행체(드론)다.** 스냅·박수는 개발용 시험 소리일 뿐이다.
- 동작: IDLE에서는 정해진 구간이나 360도를 천천히 회전 → 드론/비행물체가 접근하는 소리가 들리면 그 방향으로 카메라를 빠르게 이동. 이것이 TDoA의 목적 중 하나.
- TDoA의 각도 오차는 인정하고, 카메라와 퓨전해 물체를 락온한 뒤 이후 절차에 따라 행동.
- 기본 레퍼런스: 우크라이나의 저가형 마이크 네트워크로 드론 위치를 탐지하는 시스템. 이를 모방·보완.
- ~~추후 구상: 노드를 이동형으로~~ → 2026-10-26 설치형 지역 방위로 확정. 대상은 소형 고정익 정찰기 ([[project-product-direction]]).

**Why:** 현재 기준선(baseline-v1)은 스냅으로 맞춘 충격음 전용이다(적응 문턱 트리거, onset 주변 5ms 분석, 대역 500~3000Hz). 드론 소리는 계속 나는 음조 성분이라 이 세 곳이 모두 다시 결정 대상이다.

**How to apply:** 대역·트리거·분석 구간·마이크 간격을 논할 때는 스냅이 아니라 드론 소리(연속, 고조파) 기준으로 판단하고, 스냅 데이터로 얻은 결론은 그 한계를 밝힌다. 이론 설명은 Markdown이 아니라 HTML 시각화/애니메이션(Steps의 helper)으로 하기를 원한다. 관련: [[workflow-baseline-pivoting]], [[feedback-concise-decision-docs]]
