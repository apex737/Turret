# PC ↔ MCU 프로토콜

코드가 원본이다. 이 표는 참고용이며 코드와 같은 커밋에서 고친다.
원본: `Core/app/test/dump.h` (v2), `Core/app/inc/stream.h` (v3), PC 파서 `Tools/board/dump_viewer.py`.

## 공통

- UART: USART2, 921600 bps 8N1, TX DMA. 이론 처리량 약 92 KB/s (바이트당 10비트).
- 모든 값은 little endian. 구조체는 `__attribute__((packed))`이고 `_Static_assert`로 크기를 고정한다.
- 패킷 = `sync FF FF FF FF` + 헤더 + payload + CRC16.
- CRC-16/CCITT-FALSE, 범위 = ver부터 payload 끝까지 (sync 제외). Python `binascii.crc_hqx(data, 0xFFFF)`와 같다.
- PC는 바이트 스트림에서 sync를 찾고, 헤더 검증 → `len`만큼 대기 → CRC가 맞으면 받는다. 틀리면 1바이트만 버리고 다시 sync를 찾는다.

## v2 — 원파형 덤프 (SNAP·BURST·VERIFY 모드)

헤더 20 B (`dump_hdr_t` = sync 4 + 16).

| offset | 크기 | 필드 | 값 |
|---|---|---|---|
| 0 | 4 | sync | `FF FF FF FF` (ADC 값 ≤ 0x0FFF라 payload에 FF 4연속 불가) |
| 4 | 1 | ver | 2 |
| 5 | 1 | type | 0x01 RAW_ADC / 0x02 결과 |
| 6 | 1 | ch | 3 (결과 패킷은 0) |
| 7 | 1 | flags | `0x01` CLIP, `0x02` MANUAL, `0x04` PRETRIG, `0x08` VALID (결과 패킷만), `0x10` BURST (끊김 없는 연속 구간), `0x20` VERIFY (같은 frame_seq의 PCM과 짝) |
| 8 | 4 | seq | 송신 패킷 번호 (패킷 종류와 무관하게 증가, MCU 리셋 시 0부터) |
| 12 | 4 | frame_seq | 마지막 프레임 번호. 같은 frame_seq의 RAW와 결과가 짝 |
| 16 | 2 | n | 채널당 샘플 수 (2프레임 2048, burst 8192) |
| 18 | 2 | len | payload 바이트 수 |
| 20 | len | payload | RAW: `ch0 prev | ch0 현재 | ch1 … | ch2 …`, uint16 |
| 20+len | 2 | crc16 | |

- 2프레임 RAW 패킷 = 12,310 B, 전송 약 134 ms.
- 결과 패킷 (type 0x02): 헤더 20 B + payload 40 B + CRC 2 B = 62 B. PC `RESULT_FMT = "<3f3fffHHI"`.

| offset | 크기 | 필드 |
|---|---|---|
| 0 | 12 | tau[3] — tau12, tau13, tau23 [샘플] (float) |
| 12 | 12 | peak[3] (float) |
| 24 | 4 | angle_deg (float) |
| 28 | 4 | norm (float) |
| 32 | 2 | onset [샘플] |
| 34 | 2 | win_start [샘플] |
| 36 | 4 | proc_us |

- 부호: `tau_ij` = (j 도달 시각) − (i 도달 시각). 양수 = MIC j가 늦게 들음. `tau12 + tau23 = tau13`.
- 각도: 중심에서 MIC1 방향이 0°, 위에서 볼 때 반시계가 +. MIC2 = +120°, MIC3 = −120°.

## v3 — 12.5 kHz PCM 스트림 (STREAM 모드)

헤더 24 B (`stream_hdr_t`). 확정 2026-10-15.

| offset | 크기 | 필드 | 값 |
|---|---|---|---|
| 0 | 4 | sync | `FF FF FF FF` |
| 4 | 1 | ver | 3 |
| 5 | 1 | type | 0x03 PCM / 0x04 DOA 결과 |
| 6 | 1 | ch | 3 |
| 7 | 1 | flags | `0x01` CLIP, `0x02` RESYNC, `0x04` VERIFY, `0x08` GAP |
| 8 | 4 | seq | 송신 번호. PCM과 DOA가 따로 센다. 큐에서 버린 PCM도 번호를 소비 → PC가 빈 번호로 큐 유실을 앎 |
| 12 | 4 | frame_seq | ADC 프레임 번호 (ISR이 매김) |
| 16 | 2 | n | 채널당 샘플 수 (PCM 256, DOA 1) |
| 18 | 2 | len | payload 바이트 (PCM 1536, DOA 52) |
| 20 | 1 | drop | ADC 프레임 유실 누계 (mod 256) |
| 21 | 1 | ovr | ADC overrun 누계 (mod 256) |
| 22 | 1 | qdrop | 송신 큐 유실 누계 (mod 256) |
| 23 | 1 | cpu | 직전 프레임 전처리 + 큐 적재 시간 (20.48 ms 대비 %) |
| 24 | len | payload | PCM: `ch0[256] | ch1[256] | ch2[256]`, int16 |
| 24+len | 2 | crc16 | |

- PCM 패킷 1562 B / 20.48 ms = 76.3 KB/s (921600 bps의 약 83%).
- PCM에는 FF FF FF FF가 나올 수 있어 sync만 믿지 않는다. ver·type·len·CRC가 모두 맞아야 받는다.

**PCM 규약**

| 항목 | 값 |
|---|---|
| 스케일 | `x = adc − 2048` → FIR·↓4 → `×16` → 반올림(nearest-even, `np.rint`와 같음) → int16 포화 |
| 출력 위상 | `y[k] = Σ b[j]·x[4k − j]` (블록의 첫 샘플 시점) |
| 시간축 | 블록 첫 샘플 번호 = (frame_seq − 1) × 256 (12.5 kHz) |
| 끊김 | 번호 건너뜀 또는 overrun → FIR 상태 0 + `RESYNC`·`GAP`. 첫 19샘플(= ⌈75/4⌉)은 과도 구간. 큐 유실 → `GAP`만 (MCU 필터는 연속) |
| 검증 | VERIFY 모드: 같은 8프레임의 원본(burst, v2)과 PCM을 같이 보내고 PC가 같은 계수로 비교 |

**DOA 결과 payload (type 0x04, 52 B, 패킷 78 B, 관측 창마다 = 초당 약 4개)**. PC `DOA_FMT`.

| offset | 크기 | 필드 |
|---|---|---|
| 0 | 4 | s0 — 관측 창 첫 샘플 번호 (PCM 시간축) |
| 4 | 12 | tau[3] — 채널 지연 보정 후 [샘플 @12.5 kHz] (1,2) (1,3) (2,3) |
| 16 | 12 | peak[3] |
| 28 | 4 | angle [deg] |
| 32 | 4 | norm |
| 36 | 4 | snr_db (배경이 없으면 0) |
| 40 | 1 | flags — `0x01` VALID, `0x02` PRESENT, `0x04` BG(D1), `0x08` LEARNING |
| 41 | 1 | reserved (0) |
| 42 | 2 | proc_us (65535에서 포화) |
| 44 | 4 | bg_s0 |
| 48 | 4 | bg_n (0 = 배경 없음, D0) |

- DOA 패킷 헤더의 drop·ovr·cpu는 0, qdrop만 참고용. UART가 비면 DOA가 PCM보다 먼저 나간다.
