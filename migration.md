# 구조 개편 기록 (2026-10-22)

> 1회성 기록. 브랜치 `restructure-docs` (출발점 `FPV_Target` bdb380c). 이전 문서는 `FPV_Target` 브랜치에 그대로 남아 있다. Step 파일에서 "이전 판 N절"은 이 브랜치의 원본 파일 절을 뜻한다.
> 아래에 이전 문서의 모든 `##` 절이 한 번씩 나온다. "옮기지 않음"은 이유를 적었다. 숫자와 판정은 원문 그대로 옮겼다.

## 파일 단위 이동

| 이전 | 새 위치 | 방식 |
|---|---|---|
| `Steps/step/Step1_ADC_DMA_DoubleBuffer_MicCheck.md` | [Steps/Step1.md](Steps/Step1.md) | git mv 후 재작성 |
| `Steps/step/Step2_UART_Dump_Capture_SignalCheck.md` | [Steps/Step2.md](Steps/Step2.md) | git mv 후 재작성 |
| `Steps/step/Step3_GCC_PHAT_Python_MCU_DOA.md` | [Steps/Step3.md](Steps/Step3.md) | git mv 후 재작성 |
| `Steps/step/Step4_드론음향_탐지추정_설계.md` | [Steps/Step4.md](Steps/Step4.md) | git mv 후 재작성 |
| `Steps/step/Step5_공개원음_재생녹음_고조파구조.md` | [Steps/Step5pre.md](Steps/Step5pre.md) | git mv 후 재작성 |
| `Steps/step/Step5_연속수음_전처리_기록.md` | [Steps/Step5.md](Steps/Step5.md) | git mv 후 재작성 |
| `Steps/step/Step6_데이터_split_평가규칙.md` | [Steps/Step6.md](Steps/Step6.md) | git mv 후 재작성 |
| `Steps/step/Step7_지속음_방향추정.md` | [Steps/Step7.md](Steps/Step7.md) | git mv 후 재작성 |
| `Steps/step/Step8_PC_학습_드론분류.md` | [Steps/Step8.md](Steps/Step8.md) | git mv 후 재작성 |
| `Steps/step/Step4.5.2_Roadmap_축소.md`, `Step4.5_Roadmap.md` | problem.md, Step frontmatter, Step9A·9B·10·11 | 흡수 후 삭제 |
| `Steps/FPV_MAX4466_3MIC_학습_파이프라인_실행계획.md`, `Steps/FPV_Step5-14_실험과제_구현목표_통과기준.md` | Step 통과 기준에 쓰인 부분만 | 삭제 |
| `Steps/decisions.md` | [decisions.md](decisions.md) | git mv 후 4문 레코드로 재작성 |
| `Steps/decision.html` | [decisions.md](decisions.md) D4-1 ~ D8-6, DO-1·2 | 카드 내용을 레코드로 옮기고 삭제 |
| `Steps/Fail_Log.md` | `Steps/logs/Step5pre·5·7·8.md` "시도 기록" | 행을 Step별로 나누고 삭제. 범례는 logs/Step8.md |
| `Steps/helper/Step1~4_helper.html`, `TDOA_튜닝_배경지식.md` | [learning/notes/](learning/notes/) | git mv (내용 그대로) |
| `Steps/userBackgound/background.md` | [learning/concepts.md](learning/concepts.md) | git mv 후 템플릿 형식으로 재작성 |
| `Steps/userBackgound/background_quiz.md` | [learning/quiz.md](learning/quiz.md) | git mv, 끝에 채점 절 추가 |
| `Steps/userBackgound/checkpoint_protocol.md` | 옮기지 않음 | [learning/GUIDE.md](learning/GUIDE.md)(`~/.claude/learning-dev-guide.md` 복사)가 같은 규칙을 일반화해 담고 있음 (아래 절 참고) |
| `Plots/CubeMonitor1·2.png` | `reports/step1/` | git mv |
| `Plots/dump_plot.png` | `reports/step2/` | git mv |
| `Plots/build_analyze.png` | `reports/step3/` | git mv (2026-10-12 추가) |
| `Plots/deg30_rotate_test.jpg` | `learning/notes/` | git mv (시험 배치 사진, 스크립트 출력 아님) |
| `Plots/instruments_v0/`, `Plots/instruments_v1/` | `hardware/enclosure_v0/`, `hardware/enclosure_v1/` | git mv (사용자 결정, 내용 그대로) |
| `README.md` | [README.md](README.md) | 새 정리 지침으로 교체 |
| `Tools/README.md`, `reports/step5·7·8/*` | 그대로 | — |

## 절 단위 대응

이전 문서의 `##` 절 제목을 그대로 적었다. `##` 절이 없는 파일(`Steps/Fail_Log.md`, `Steps/decision.html`)은 맨 아래에 따로 적었다. **사용자 판단**으로 표시한 줄은 보고에 모았다.

### `Plots/instruments_v1/README.md`

| 절 | 새 위치 |
|---|---|
| 출력 수량 | `hardware/enclosure_v1/` 그대로 |
| 확정 반영 치수 | `hardware/enclosure_v1/` 그대로 |
| 층간 조립 | `hardware/enclosure_v1/` 그대로 |
| 2–3층 미끄럼 단면 | `hardware/enclosure_v1/` 그대로 |
| 확인 결과와 남은 사항 | `hardware/enclosure_v1/` 그대로 |
| 재생성 | `hardware/enclosure_v1/` 그대로 |

### `Plots/instruments_v1/reports/검사결과.md`

| 절 | 새 위치 |
|---|---|
| 발견해서 수정한 문제 | `hardware/enclosure_v1/` 그대로 |
| 통과한 자동 검사 | `hardware/enclosure_v1/` 그대로 |
| 아직 검증하지 않은 사항 | `hardware/enclosure_v1/` 그대로 |

### `README.md`

| 절 | 새 위치 |
|---|---|
| 폴더 구조 | [docs/firmware.md](docs/firmware.md) 모듈 구조, 새 README 1절 |
| 데이터 흐름 | docs/firmware.md 데이터 흐름 (STREAM 기준으로 갱신) |
| 같이 고쳐야 하는 짝 | docs/firmware.md 같이 고쳐야 하는 짝 |
| Steps 문서 | 옮기지 않음 (파일 목록 표. 새 구조와 README가 대신함) |
| 빌드와 실행 | [docs/run.md](docs/run.md) 준비 |

### `Steps/FPV_MAX4466_3MIC_학습_파이프라인_실행계획.md`

| 절 | 새 위치 |
|---|---|
| 1. 최종 목표와 완료 범위 | 옮기지 않음 — Roadmap 4.5(v0.2)가 이 계획서의 P0~P9를 Step5~14로 나눠 흡수했고, 통과 기준은 Roadmap 4.5.2와 상세 계획에서 가져왔다 |
| 2. 기존 구현에서 유지할 것과 바꿀 것 | 옮기지 않음 — Roadmap 4.5(v0.2)가 이 계획서의 P0~P9를 Step5~14로 나눠 흡수했고, 통과 기준은 Roadmap 4.5.2와 상세 계획에서 가져왔다 |
| 3. 권장 전체 파이프라인 | 옮기지 않음 — Roadmap 4.5(v0.2)가 이 계획서의 P0~P9를 Step5~14로 나눠 흡수했고, 통과 기준은 Roadmap 4.5.2와 상세 계획에서 가져왔다 |
| 4. 하드웨어와 MAX4466 검증 | 옮기지 않음 — Roadmap 4.5(v0.2)가 이 계획서의 P0~P9를 Step5~14로 나눠 흡수했고, 통과 기준은 Roadmap 4.5.2와 상세 계획에서 가져왔다 |
| 5. 데이터 전략 | 옮기지 않음 — Roadmap 4.5(v0.2)가 이 계획서의 P0~P9를 Step5~14로 나눠 흡수했고, 통과 기준은 Roadmap 4.5.2와 상세 계획에서 가져왔다 |
| 6. 학습 전략 | 옮기지 않음 — Roadmap 4.5(v0.2)가 이 계획서의 P0~P9를 Step5~14로 나눠 흡수했고, 통과 기준은 Roadmap 4.5.2와 상세 계획에서 가져왔다 |
| 7. 방향 추정과 분류 결과의 결합 | 옮기지 않음 — Roadmap 4.5(v0.2)가 이 계획서의 P0~P9를 Step5~14로 나눠 흡수했고, 통과 기준은 Roadmap 4.5.2와 상세 계획에서 가져왔다 |
| 8. 접근 인식: 검출과 분리해서 검증 | 옮기지 않음 — Roadmap 4.5(v0.2)가 이 계획서의 P0~P9를 Step5~14로 나눠 흡수했고, 통과 기준은 Roadmap 4.5.2와 상세 계획에서 가져왔다 |
| 9. MCU·PC·SBC 분담과 통신 | 옮기지 않음 — Roadmap 4.5(v0.2)가 이 계획서의 P0~P9를 Step5~14로 나눠 흡수했고, 통과 기준은 Roadmap 4.5.2와 상세 계획에서 가져왔다 |
| 10. 상태 관리와 카메라 확장 | 옮기지 않음 — Roadmap 4.5(v0.2)가 이 계획서의 P0~P9를 Step5~14로 나눠 흡수했고, 통과 기준은 Roadmap 4.5.2와 상세 계획에서 가져왔다 |
| 11. 단계별 액션플랜 | 옮기지 않음 — Roadmap 4.5(v0.2)가 이 계획서의 P0~P9를 Step5~14로 나눠 흡수했고, 통과 기준은 Roadmap 4.5.2와 상세 계획에서 가져왔다 |
| 12. 시험 지표와 임시 합격선 | 옮기지 않음 — Roadmap 4.5(v0.2)가 이 계획서의 P0~P9를 Step5~14로 나눠 흡수했고, 통과 기준은 Roadmap 4.5.2와 상세 계획에서 가져왔다 |
| 13. 일정과 우선순위 | 옮기지 않음 — Roadmap 4.5(v0.2)가 이 계획서의 P0~P9를 Step5~14로 나눠 흡수했고, 통과 기준은 Roadmap 4.5.2와 상세 계획에서 가져왔다 |
| 14. 구현 산출물 구조 제안 | 옮기지 않음 — Roadmap 4.5(v0.2)가 이 계획서의 P0~P9를 Step5~14로 나눠 흡수했고, 통과 기준은 Roadmap 4.5.2와 상세 계획에서 가져왔다 |
| 15. 중단·변경 판단표 | 옮기지 않음 — Roadmap 4.5(v0.2)가 이 계획서의 P0~P9를 Step5~14로 나눠 흡수했고, 통과 기준은 Roadmap 4.5.2와 상세 계획에서 가져왔다 |
| 16. 참고 근거 | 옮기지 않음 — Roadmap 4.5(v0.2)가 이 계획서의 P0~P9를 Step5~14로 나눠 흡수했고, 통과 기준은 Roadmap 4.5.2와 상세 계획에서 가져왔다 |

### `Steps/FPV_Step5-14_실험과제_구현목표_통과기준.md`

| 절 | 새 위치 |
|---|---|
| 1. 변경 방향 | 옮기지 않음 — 원칙은 새 README 규칙 7·11과 같음 |
| 2. 공통 운영 규칙 | 2.2 판정 상태 → Step status 매핑 (아래 상태 매핑 표). 2.1·2.3 → 옮기지 않음 (새 Step 형식과 Step6 남은 일 "평가 규칙 고정"이 대신함) |
| 3. 전체 단계와 의존성 | 옮기지 않음 (Roadmap 4.5.2의 순서를 따름) |
| Step5. 연속 수음·전처리·기록 경로 검증 | 옮기지 않음 — 같은 기준이 Roadmap 4.5.2 3절에 반영되어 그쪽을 옮김 |
| Step6. 평가 데이터셋과 시험 규칙 고정 | 옮기지 않음 — 같은 기준이 Roadmap 4.5.2 3절에 반영되어 그쪽을 옮김 |
| Step7. 방향 추정 알고리즘 선정 | 옮기지 않음 — 같은 기준이 Roadmap 4.5.2 3절에 반영되어 그쪽을 옮김 |
| Step8. 드론 분류기 선정 | 옮기지 않음 — 같은 기준이 Roadmap 4.5.2 3절에 반영되어 그쪽을 옮김 |
| Step9. 드론 분류와 방향의 대응 검증 | 옮기지 않음 — 같은 기준이 Roadmap 4.5.2 3절(Step9A·9B)에 반영되어 그쪽을 옮김 |
| Step10. 에지 실시간 실행 검증 | 옮기지 않음 — 같은 기준이 Roadmap 4.5.2 3절에 반영되어 그쪽을 옮김 |
| Step11. 실제 FPV 검출·방위 추정 최종 검증 | [Steps/Step11.md](Steps/Step11.md) 통과 기준·남은 일 |
| Step12. 접근·비접근 판별 검증 | problem.md 비목표 표 (진입 조건) |
| Step13. 카메라 연결 — 선택 확장 | problem.md 비목표 표 (진입 조건) |
| Step14. MCU 단독 분류 — 선택 확장 | problem.md 비목표 표 (진입 조건) |
| 4. 공통 지표 정의 | 옮기지 않음 — Step9B·11 기준에 쓰인 정의(공동 성공률, 방해음 오지향률)는 기준 문장에 풀어 씀. 전체 정의 표를 Step6 평가 규칙으로 둘지 **사용자 판단** |
| 5. Step 문서 작성 템플릿 | 옮기지 않음 (새 README 4절 형식으로 대체) |
| 검증 질문 | 옮기지 않음 (5절 템플릿의 일부, 새 README 4절 형식으로 대체) |
| 입력·선행 조건 | 옮기지 않음 (5절 템플릿의 일부, 새 README 4절 형식으로 대체) |
| 실험·구현 과제 | 옮기지 않음 (5절 템플릿의 일부, 새 README 4절 형식으로 대체) |
| 측정 지표·통과 기준 | 옮기지 않음 (5절 템플릿의 일부, 새 README 4절 형식으로 대체) |
| 산출물 | 옮기지 않음 (5절 템플릿의 일부, 새 README 4절 형식으로 대체) |
| 실패 시 조치 | 옮기지 않음 (5절 템플릿의 일부, 새 README 4절 형식으로 대체) |
| 최종 판정 | 옮기지 않음 (5절 템플릿의 일부, 새 README 4절 형식으로 대체) |
| 6. 바로 시작할 작업 | 옮기지 않음 (이미 진행됨) |
| 7. 설계 참고 자료 | 옮기지 않음 (참고 문헌) |

### `Steps/decisions.md`

| 절 | 새 위치 |
|---|---|
| Step 1 — ADC-DMA | D1-1, D1-2 |
| Step 2 — 덤프 / 캡처 | D2-1 ~ D2-4 |
| Step 3 — GCC-PHAT | D3-1 ~ D3-6 |
| Step 4 이후 | D4-1 이후 (decision.html에서 옮김) |

### `Steps/helper/TDOA_튜닝_배경지식.md`

| 절 | 새 위치 |
|---|---|
| 0. 이 문서를 읽는 법 | learning/notes/TDOA_튜닝_배경지식.md 그대로 (사용자 결정: 팀/본인 자료) |
| 1. 전체 지도 | learning/notes/TDOA_튜닝_배경지식.md 그대로 (사용자 결정: 팀/본인 자료) |
| 2. 사인파와 페이저: 지연은 회전이다 | learning/notes/TDOA_튜닝_배경지식.md 그대로 (사용자 결정: 팀/본인 자료) |
| 3. 샘플링과 앨리어싱 | learning/notes/TDOA_튜닝_배경지식.md 그대로 (사용자 결정: 팀/본인 자료) |
| 4. DFT, bin, FFT | learning/notes/TDOA_튜닝_배경지식.md 그대로 (사용자 결정: 팀/본인 자료) |
| 5. 주파수 영역 BPF | learning/notes/TDOA_튜닝_배경지식.md 그대로 (사용자 결정: 팀/본인 자료) |
| 7. 피크 찾기와 포물선 보간 | learning/notes/TDOA_튜닝_배경지식.md 그대로 (사용자 결정: 팀/본인 자료) |
| 8. 정밀도와 신뢰도의 원리 | learning/notes/TDOA_튜닝_배경지식.md 그대로 (사용자 결정: 팀/본인 자료) |
| 9. 기하: 시간차에서 각도로 | learning/notes/TDOA_튜닝_배경지식.md 그대로 (사용자 결정: 팀/본인 자료) |
| 11. 실시간성 기초 | learning/notes/TDOA_튜닝_배경지식.md 그대로 (사용자 결정: 팀/본인 자료) |
| 12. 성능지표와 측정 | learning/notes/TDOA_튜닝_배경지식.md 그대로 (사용자 결정: 팀/본인 자료) |
| 13. 파라미터 카드 | learning/notes/TDOA_튜닝_배경지식.md 그대로 (사용자 결정: 팀/본인 자료) |
| 14. 튜닝 실험 절차 | learning/notes/TDOA_튜닝_배경지식.md 그대로 (사용자 결정: 팀/본인 자료) |
| 15. 자주 하는 오해 | learning/notes/TDOA_튜닝_배경지식.md 그대로 (사용자 결정: 팀/본인 자료) |
| 16. 용어집 | learning/notes/TDOA_튜닝_배경지식.md 그대로 (사용자 결정: 팀/본인 자료) |
| 17. 자가 점검 문제 | learning/notes/TDOA_튜닝_배경지식.md 그대로 (사용자 결정: 팀/본인 자료) |
| 18. 참고 | learning/notes/TDOA_튜닝_배경지식.md 그대로 (사용자 결정: 팀/본인 자료) |
| 개정 이력 | learning/notes/TDOA_튜닝_배경지식.md 그대로 (사용자 결정: 팀/본인 자료) |

### `Steps/step/Step1_ADC_DMA_DoubleBuffer_MicCheck.md`

| 절 | 새 위치 |
|---|---|
| 0. 배경 — 재는 일과 방향 계산의 원리 | 옮기지 않음 (개념 설명). learning/concepts.md에 T0, S1, F4, T1 출처로 기록. 0.4의 보간 오차 표도 설명 예시라 옮기지 않음 |
| 1. 이 단계의 목표 | Step1 exit, 통과 기준 |
| 2. 하드웨어 / 클럭 / 주변장치 설정 | docs/firmware.md 클럭·ADC·DMA (클럭원은 현재 HSE로 갱신) |
| 3. 버퍼 구조와 타이밍 | docs/firmware.md 버퍼 줄. 3.1 핑퐁 직관 설명은 옮기지 않음 (R1 개념) |
| 4. 이중 버퍼 구현 (`Core/Src/adc.c`, `Core/Src/app.c`) | docs/firmware.md 클럭·ADC·DMA 아래 설명 |
| 5. STM32CubeMonitor로 확인하기 | Step1 결과 (측정 표). 5.1 미측정 표 → Step1 결과 "미측정" 줄 |
| 6. 남은 이슈 / 다음 할 일 | 클리핑·채널 매핑(완료) → Step1 결과. OVR 등록 → Step5에서 해결(`adc_service`). 클리핑 카운터·UART 덤프·장시간 잡음 바닥 → Step2·Step5에서 완료. DWT 콜백 주기 → Step10 남은 일. 동시 샘플링 검증 → D4.5-5로 버림. 전체 로드맵 1~5 → 완료, 6 터렛 제어 → problem.md 선택 확장(서보) |

### `Steps/step/Step2_UART_Dump_Capture_SignalCheck.md`

| 절 | 새 위치 |
|---|---|
| 1. 이 단계의 목표 | Step2 exit, 통과 기준 |
| 2. 폴더 구조 / 빌드 / 개발환경 | docs/firmware.md 빌드·IDE, docs/run.md 준비 |
| 3. UART 설정과 연결 | docs/firmware.md UART |
| 4. 왜 덤프/캡처인가 — "차량 블랙박스" 방식 | D2-1, D2-2. 4.1 "실시간처럼 보이는 이유"·블랙박스 비유는 옮기지 않음 (설명) |
| 5. capture — 트리거 방식 | 파라미터 → Step2 파라미터. 5.1 흐름·5.4 상태 → 옮기지 않음 (코드가 원본, capture.c 주석). 5.2 용어 → concepts.md S2·S3. 5.3 frame_stats 유도 → 옮기지 않음 (설명). 5.5 EMA → concepts.md E1. 5.6 조정 방향 → 옮기지 않음 (설명). 5.7 한계 → logs/Step2.md, D2-3. 5.8 관찰 코드 제거 → logs/Step2.md. 5.9 연속음 대상일 때 → 옮기지 않음 (Step7 D1로 실현됨) |
| 6. dump — 패킷 형식 | docs/protocol.md v2. 6.3 typedef → concepts.md L1. 6.4 구현 포인트 → docs/firmware.md UART, concepts.md L2 |
| 7. dump_viewer.py — 결과 읽는 법 | 콘솔 카운터 → docs/run.md SNAP. 그래프 3단 읽는 법·7.1 수신 순서 → 옮기지 않음 (도구 사용법, 스크립트 머리 주석). 7.2 seq 22 해석 → logs/Step2.md |
| 8. 왜 GCC-PHAT을 Python에서 먼저 만드나 | D2-4 |
| 9. 남은 이슈 / 다음 할 일 | 뷰어 저장 이름 → Step2 남은 일. adc_get_frame_seq → Step5에서 `adc_get_frame(out, &seq)`로 해결. 비대칭 EMA·짧은 소리 → D2-3 보류 (대상 변경으로 진행 안 함). 게인 맞춤·채널 매핑·B1 잡음 캡처·배치 실측·대상 소리 결정 → Step5·Step5pre에서 완료. 수직이등분선 동시성 → D4.5-5. MIC3 고주파 부족 → Step5 남은 일 (ch3 고역 잡음). 다음 단계 gcc_phat → Step3에서 완료. 전체 로드맵 → 완료 |

### `Steps/step/Step3_GCC_PHAT_Python_MCU_DOA.md`

| 절 | 새 위치 |
|---|---|
| 0. 기준선 `baseline-v1` | 0.1 설정 → Step3 파라미터, docs/firmware.md 짝 표. 0.2 성능 → Step3 결과. 0.3 → Step3 결과 "미측정" 줄과 남은 일. 0.4 실험 규칙 → 옮기지 않음 (새 README 규칙 7과 decisions.md가 대신함). 0.5 기준선 이력 → Step3 남은 일 (`baseline-v2` 태그), D3-1 |
| 1. 이 단계의 목표 | Step3 exit |
| 2. 결과 요약 | Step3 결과 |
| 3. 추가/변경된 파일 | 옮기지 않음 (git 기록이 원본) |
| 4. GCC-PHAT 파이프라인 | 단계 순서 → docs/firmware.md tdoa.c. 4.1 부호·각도 규칙 → docs/protocol.md v2. 4.2~4.5 이유·지표 설명 → 옮기지 않음 (concepts.md F3, F5, T2, E3). 4.5 신뢰 판정 근거 → D3-5. 4.6 onset 정수 연산 → logs/Step3.md, D2-4 |
| 5. 파라미터 | Step3 파라미터, docs/firmware.md 짝 표. 5.1·5.2 대역 근거 → logs/Step3.md, D3-1 |
| 6. Python 도구 | docs/run.md SNAP. 6.1 화면 요소 설명 → 옮기지 않음 (도구 사용법). 6.2 검증 → logs/Step3.md |
| 7. MCU 구현 | 7.1 CMSIS 파일·7.2 IDE·7.3 tdoa.c·7.4 연결 → docs/firmware.md. 7.5 결과 패킷 → docs/protocol.md. 7.6 모드 → docs/firmware.md 동작 모드, D3-6. 7.7 → docs/firmware.md tdoa.c |
| 8. MCU와 PC 비교 결과 | logs/Step3.md (8.1, 8.2, 8.3 포함) |
| 9. 측정에서 관찰한 것과 한계 | logs/Step3.md 관찰과 한계. 구조적 한계 표 → 옮기지 않음 (스냅 경로의 한계, Step7에서 지속음으로 해소) |
| 10. 남은 이슈 / 다음 할 일 | 스냅 경로 항목 → Step3 남은 일. 대상 소리 결정 → 완료 (D4-1). 트리거·분석 구간 재결정 → Step7에서 해소. 동시 샘플링·콜백 흔들림·B1 잡음(이월) → D4.5-5·Step10·Step5. 펌웨어 완료 항목 → 옮기지 않음. `r.valid` → 터렛 제어 → problem.md 선택 확장(서보). adc_get_frame_seq → Step5에서 해결. 도구/정리 → Step3 남은 일 (README·decisions 커밋은 완료). 터렛 제어로 연결 1~4 → problem.md 선택 확장(서보). 평활화·센서퓨전 → 옮기지 않음 (Step9A 결합 규칙이 대신함, **사용자 판단**) |

### `Steps/step/Step4.5.2_Roadmap_축소.md`

| 절 | 새 위치 |
|---|---|
| 0. 현재 상태와 다음 순서 (2026-10-18) | 상태 → 각 Step frontmatter `status`. 순서 → depends_on. 열린 결정 → problem.md, DO-1. mermaid → flow.html |
| 1. 첫 완성 목표와 범위 | problem.md 한 줄 요약·G·비목표. 번호 변경 안내 → Step4 본문, migration.md |
| 2. 작업 순서 | Step frontmatter depends_on. 진행 원칙 4개 → problem.md P1·P3 |
| 3. 단계별 구현과 통과 기준 | Step5~10, 9A, 9B 통과 기준·남은 일. Step8 v1 계획 → logs/Step8.md v1, Step8 통과 기준 아래 문장 |
| 4. 선택·조건부 확장 | problem.md 비목표 표, Step11 |
| 5. 개발 지침 | problem.md P2. 지침 3 "도입 근거를 매 Step md에 Mermaid와 함께" → 옮기지 않음 — 새 README 규칙(Step 80줄)과 충돌. 코드 블록별 도입 이유는 docs/firmware.md 표로 둠. **사용자 판단** |
| 6. 판정·기록 원칙과 바로 할 일 | 원칙 → 새 README 규칙 7·11, problem.md I5. 바로 할 일 → Step8·9A·10 남은 일 |

### `Steps/step/Step4.5_Roadmap.md`

| 절 | 새 위치 |
|---|---|
| 1. 전체 흐름 | 옮기지 않음 (Roadmap 4.5.2 번호로 대체, flow.html이 흐름도). 머리말 분할 원칙·전제 → problem.md 변경 이력, D4.5-1, D4.5-4 |
| 2. 결정 | 2-1 → D4.5-1, 2-2 → D4.5-5, 2-3 → D4.5-6, 2-4·2-5 → D4.5-7 |
| 3. 원음 선정 기준 | logs/Step5pre.md 원음 조사 (기준 한 줄). 재생 경로 세 가지 표 → 옮기지 않음 (설명, D4.5-7·D8-6) |
| 4. 남은 위험 | D4.5-1 대가, D5pre-1 |

### `Steps/step/Step4_드론음향_탐지추정_설계.md`

| 절 | 새 위치 |
|---|---|
| 1. 왜 바꾸나: 대상 소리의 성질이 정반대 | 옮기지 않음 (설명). D4-1 |
| 2. 정밀도 식은 어디서 나오나 | 옮기지 않음 (개념 설명). concepts.md F2, F4 출처 |
| 3. 다이얼과 결과값 | 옮기지 않음 (설명). 3.5 튜닝 순서는 TDOA 배경지식 14절과 겹침 |
| 4. 처리 속도와 FIR 필터: 왜 50 kHz로 재고 12.5 kHz로 처리하나 | 결론·비교 → D4-2. 4.3 탭 수 표·4.6 시뮬레이션 → logs/Step4.md. 4.4 조건 → Step4 파라미터 "FIR 조건", concepts.md C4·C3. 4.2·4.7 설명 → 옮기지 않음 |
| 5. 고조파 검출기 설계 | 옮기지 않음 (D4.5-2로 주 경로에서 빠짐). concepts.md E4·E5·T4 출처. 5.7 손계산 표 → logs/Step4.md |
| 6. 목표 파이프라인 | 옮기지 않음 (Roadmap 4.5.2로 대체. 현재 파이프라인은 docs/firmware.md) |
| 7. 대상 소리: 아는 것과 모르는 것 | 7.1 → D4-1. 7.2 조사 → logs/Step4.md. 7.3 예상 → 옮기지 않음 (Step5pre에서 실측으로 대체) |
| 8. 현재 스냅 검출기 대비 변경점 | 옮기지 않음 (Step5·7·8이 실제 변경을 기록) |
| 9. 사전 지식의 사용 범위 | 옮기지 않음 — 원칙 "방향 추정은 기종 학습 지식에 의존하지 않는다"는 현재 D1에서 지켜지고 있음. problem.md 불변조건으로 올릴지 **사용자 판단** |
| 10. 강건성: 재밍·기만 대응 | 옮기지 않음 — 첫 완성 범위 밖 (JAM 플래그 미구현). **사용자 판단** |
| 11. 구현 단계 | 옮기지 않음 — 4-0 → Step5, 4-1 → Step5pre, 4-3 → Step6, 4-6 → Step7 MCU 이식, 4-2·4-4·4-5·4-7·4-8 → D4.5-2로 범위 변경 |
| 12. 미결 사항 | f0·f_use → Step5pre (D5pre-2). N·창 이동 → Step7 파라미터. d → D7-0. 12.5 kHz 한 경로 → Step5에서 확인. 창 함수·마스크 폭·곁봉우리 → 고조파 마스크 기각(D7-1)으로 불필요. M-of-N → Step8 3창 중 2창. 음성·음악 → Step8 데이터. 자기 소음(모터·젯슨 팬)·PWM → problem.md 선택 확장(서보), **사용자 판단**. 모듈 상태·채널 불일치 → Step5 ch3, D7-2. 마이크 4개 이상 → 옮기지 않음 (DO-1에서 50 m 선택 시) |
| 13. 요구사항 추가 후보 (요구사항 문서 v0.3 반영 예정) | 옮기지 않음 — 요구사항 문서(v0.2)가 저장소에 없음. **사용자 판단** |
| 14. 참고 | 옮기지 않음 (참고 문헌). Knapp & Carter (1976)는 TDOA 배경지식 18절에도 있음 |

### `Steps/step/Step5_공개원음_재생녹음_고조파구조.md`

| 절 | 새 위치 |
|---|---|
| 결론 | Step5pre 결과, D5pre-2 |
| 원음 (2026-10-14 조사) | logs/Step5pre.md, D5pre-1 |
| FPV 양성 추가 후보 (2026-10-18 조사, Step8 v1 미달 뒤) | logs/Step5pre.md |

### `Steps/step/Step5_연속수음_전처리_기록.md`

| 절 | 새 위치 |
|---|---|
| 0. 질문 | Step5 질문, 통과 기준 |
| 1. 확정한 규약 (A2, 2026-10-15) | docs/protocol.md v3 PCM 규약, Step5 파라미터 (FIR) |
| 2. 구조와 도입 이유 | docs/firmware.md 데이터 흐름·STREAM 코드 블록·동작 모드 |
| 3. PC에서 확인한 것 (보드 없이) | logs/Step5.md, Step5 결과 |
| 4. 보드에서 할 일 | 절차 → docs/run.md, 결과 → logs/Step5.md, Step5 결과 |
| 5. 남은 위험·다시 볼 조건 | HSI → logs/Step5.md, D5-1. UART 여유 → Step10 남은 일. CubeMX·makefile → docs/firmware.md. 프레임 동기 간섭·ch3 → logs/Step5.md, Step5 남은 일. overrun 재시작 시간 → docs/firmware.md |

### `Steps/step/Step6_데이터_split_평가규칙.md`

| 절 | 새 위치 |
|---|---|
| 0. 질문 | Step6 질문 |
| 1. 데이터 v0 | logs/Step6.md, Step6 결과 |
| 2. 규칙과 도입 이유 | D6-1, logs/Step6.md 규칙 표 |
| 3. 평가 규칙 (Step8 v0에서 사용) | Step6 파라미터 |
| 4. 한계 (부족한 것을 통과로 표시하지 않음) | Step6 남은 일 |

### `Steps/step/Step7_지속음_방향추정.md`

| 절 | 새 위치 |
|---|---|
| 0. 질문 | Step7 질문, 통과 기준 |
| 1. 방식 | D7-1, Step7 파라미터 |
| 2. 코드 블록별 도입 이유 | Step7 파라미터(값), logs/Step7.md (D0 실패 원인). 나머지 설명 → 옮기지 않음 (concepts.md E2, T3) |
| 3. 합성 시험 결과 (`reports/step7/synth_eval.txt`) | logs/Step7.md |
| 4. 실제 녹음 (정답 방위 없음, 2026-10-16) | logs/Step7.md |
| 5. 실제 각도 시험 (보드에서 할 일) | 배치·녹음·분석 → docs/run.md, 결과 → logs/Step7.md, Step7 결과, D7-2 |
| 6. MCU 이식 (2026-10-18) | 설계 표 → docs/firmware.md doa.c, 시험 결과 → logs/Step7.md, 절차 → docs/run.md, 기준 → Step7 통과 기준, D7-3 |
| 7. 다음 | Step9A 남은 일, Step7 남은 일, D7-1 다시 결정할 조건 |

### `Steps/step/Step8_PC_학습_드론분류.md`

| 절 | 새 위치 |
|---|---|
| 0. 질문 | Step8 질문 |
| 1. v0 모델 선택 | D8-1, Step8 파라미터 |
| 2. 파이프라인과 도입 이유 | Step8 파라미터. 코드별 이유 표 → 옮기지 않음 (각 스크립트 주석이 원본) |
| 3. 결과 (`reports/step8/v0_report.md`) | logs/Step8.md v0 |
| 4. 해석 | logs/Step8.md v0 |
| 5. 다음 갈림길 → A 선택 (2026-10-18) | D8-2 |
| 6. v1 — 증강 + 장치 잡음 음성 (2026-10-18): 미달 | logs/Step8.md v1 |
| 7. v2 — Salford 밖 FPV 양성 추가 (2026-10-19): 개선, 목표 미달 | logs/Step8.md v2, D8-3 |
| 8. v3 — FSD50K 어려운 비드론 추가 (2026-10-19): 오탐은 줄지만 재현율과 맞교환 | logs/Step8.md v3, D8-4 |
| 9. v4 (C1) — 분류기만 MLP로 + 운용점 분석 (2026-10-19): MLP 기각, v3m 직선 채택 | logs/Step8.md v4, D8-5, Step8 결과 |
| 10. v5 — 장치 경로 녹음을 학습에 (2026-10-19): 녹음 대기 | logs/Step8.md v5, D8-6, docs/run.md v5 녹음 |
| 11. 재현 | docs/run.md Step8 학습 재현 |

### `Steps/userBackgound/background.md`

| 절 | 새 위치 |
|---|---|
| 1. 진단 요약 | learning/concepts.md 1절 |
| 2. Step별 의존 개념 | concepts.md 2절, 각 Step "의존 개념" |
| 3. 개념 목록과 판정 | concepts.md 3절 (mermaid 선후 그림 → "선행 개념" 열) |
| 4. 보완 순서 | concepts.md 4절 (볼 곳 링크를 새 위치로 갱신). 0단계 고칠 점 → quiz.md 채점 절 |
| 5. 다시 진단하는 법 | concepts.md 5절 |
| 부록 — 문항별 채점 | learning/quiz.md 채점 절 |

### `Steps/userBackgound/background_quiz.md`

| 절 | 새 위치 |
|---|---|
| 푸는 방법 | learning/quiz.md 그대로 (사용자 답 원문 유지, 머리말의 `background.md` 언급만 `concepts.md`로) |
| Step 1 — ADC 3채널 동시 샘플링, DMA 핑퐁 | learning/quiz.md 그대로 (사용자 답 원문 유지, 머리말의 `background.md` 언급만 `concepts.md`로) |
| Step 2 — UART 덤프, 소리 트리거 | learning/quiz.md 그대로 (사용자 답 원문 유지, 머리말의 `background.md` 언급만 `concepts.md`로) |
| Step 3 — GCC-PHAT, 방향 추정 | learning/quiz.md 그대로 (사용자 답 원문 유지, 머리말의 `background.md` 언급만 `concepts.md`로) |
| Step 4 — 드론 대상 설계: FIR과 데시메이션 | learning/quiz.md 그대로 (사용자 답 원문 유지, 머리말의 `background.md` 언급만 `concepts.md`로) |
| Step 5 — 연속 수음과 전처리 | learning/quiz.md 그대로 (사용자 답 원문 유지, 머리말의 `background.md` 언급만 `concepts.md`로) |
| Step 6 — 데이터 split과 평가 규칙 | learning/quiz.md 그대로 (사용자 답 원문 유지, 머리말의 `background.md` 언급만 `concepts.md`로) |
| Step 7 — 지속음 방향 추정 | learning/quiz.md 그대로 (사용자 답 원문 유지, 머리말의 `background.md` 언급만 `concepts.md`로) |
| Step 8 — PC 학습 기반 드론 분류 | learning/quiz.md 그대로 (사용자 답 원문 유지, 머리말의 `background.md` 언급만 `concepts.md`로) |
| Step 9A — 판정과 방위 결합 | learning/quiz.md 그대로 (사용자 답 원문 유지, 머리말의 `background.md` 언급만 `concepts.md`로) |
| Step 10 — STM32 + PC 실시간 통합 | learning/quiz.md 그대로 (사용자 답 원문 유지, 머리말의 `background.md` 언급만 `concepts.md`로) |

### `Steps/userBackgound/checkpoint_protocol.md`

| 절 | 새 위치 |
|---|---|
| 0. 왜 이 규칙이 있나 | GUIDE.md 1절 |
| 1. 언제 끼어드나 (트리거) | GUIDE.md 4절 |
| 2. 문항 만드는 법 — Action A를 거꾸로 분해한다 | GUIDE.md 5절 (Turret 예시 D3-1 표는 빠짐) |
| 3. 채점 | GUIDE.md 6절 |
| 4. 기대에 못 미치면 | GUIDE.md 7절 |
| 5. 진행을 막는 조건 | GUIDE.md 8절 |
| 6. 기록 형식 | GUIDE.md 9·10절 (quiz.md 형식). 이전의 "Part 3 — 진행 중 점검" 위치 지정은 GUIDE의 quiz.md 형식으로 대체 |
| 대기 문항 | GUIDE.md 10절 quiz.md 템플릿의 "대기 문항" |
| 7. T4 단계 게이트의 구성 | GUIDE.md 8절 T4 |
| 8. Claude의 태도 | GUIDE.md 12절 |

### `Steps/decision.html` (`##` 절 없음)

카드 15개(4-1, 4-2, 4.5-1~3, 8-1, 7-0~7-3, 8-2~8-6)와 열린 결정 2개 → decisions.md 같은 번호에 D를 붙임 (D4-1 … D8-6, DO-1, DO-2). "지금 위치" 문구는 Step8 남은 일(v5)로. 시간순 재생 UI는 옮기지 않음 (형식).

### `Steps/Fail_Log.md` (`##` 절 없음)

22행 전부 → logs/Step8.md (7행), logs/Step7.md (8행), logs/Step5.md (6행), logs/Step5pre.md (1행). 머리말 범례 → logs/Step8.md.

## 상태 매핑

| Step | 이전 상태 (원문) | impl |
|---|---|---|
| Step1~3 | 목표 달성 기록 (Roadmap 4.5.2 "기존 Step 문서") | 통과 (기준은 사후 정리) |
| Step4 | 설계 초안 v0.2, 이후 범위 변경 | 통과 (설계 문서 확정) + 범위 변경은 D4.5-2 |
| Step5pre | 완료 | 통과 |
| Step5 | 통과 (2026-10-16) | 통과 |
| Step6 | 개발용 완료 (최소판) | 진행 (성능 판정용 데이터·규칙 미완) |
| Step7 | 통과 (MCU 포함) | 통과 |
| Step8 | 미통과 (근접) | 미통과 |
| Step9A | 미착수 | 대기 |
| Step10 | 일부 (STM32 쪽 방향 결과 패킷 완료) | 진행 |
| Step9B, Step11 | 미착수 / 조건부 | 대기 |
