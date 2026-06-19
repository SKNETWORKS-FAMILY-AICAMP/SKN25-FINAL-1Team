# Triage 에이전트 Input / Output 명세 (평가팀용)

오케스트레이터 v2 기준. 라이브 경로:
`chat.py send_message` → `orchestrator_service.process_turn` → `graph.run_turn` →
(router가 단일 노드 선택) → `ai/agents/triage/node.py TriageNode.run`.

> 한 턴에 **에이전트는 1개만** 실행된다(LangGraph 조건부 엣지). triage는 router가
> 발화를 `symptom`/`booking`으로 분류했고 PRE_BOOKING일 때, 또는 문진 진행 중
> (`active_flow == triaging`)일 때 선택된다.

---

## 1. INPUT — `SessionContext`

정의: [`ai/orchestrator/contracts.py`](../ai/orchestrator/contracts.py) `SessionContext`.
매 턴 [`state.build_context`](../ai/orchestrator/state.py)가 DB에서 만들어 넘긴다.

triage 노드가 **실제로 읽는** 필드:

| 필드 | 타입 | 의미 | 출처 |
|------|------|------|------|
| `user_message` | str | 이번 턴 보호자 발화 | 요청 body |
| `history` | list[dict] | 최근 대화(최근 8개 사용) | `chat_historyDB.messages` |
| `pet_info` | dict | 이름/종/품종/성별/체중/중성화 | `petDB` |
| `triage_state` | dict | 문진 진행 상태(슬롯·턴카운트·섹션·red_flag) | `chat_historyDB.orch_state.triage_state` |
| `emrid` | int \| None | 문진 완료 시 발급/재사용 | `chat_historyDB.emrid` |
| `db`, `session` | runtime | DB 적재 핸들(저장 안 함) | 런타임 |

`triage_state` 내부 키(노드가 턴마다 갱신):
`section`(현재 섹션), `fields`(누적 슬롯), `turn_count`, `red_flag`(bool), `red_flag_followup`.

---

## 2. OUTPUT — `AgentResult` (프론트/상태)

정의: [`contracts.py`](../ai/orchestrator/contracts.py) `AgentResult`.

| 필드 | 의미 |
|------|------|
| `reply` | 보호자에게 보일 답(질문 또는 마무리 인사) |
| `quick_replies` | pill 버튼(완료 시엔 `[]` — 예약창은 프론트가 염) |
| `state_patch` | `orch_state`에 머지: `{triage_state, active_flow}` |
| `events` | 완료 시 `triage_complete` 이벤트 1개 |

`triage_complete` 이벤트 `data`: `urgency`, `chief_complaints`, `suspected_conditions`,
`symptom_keywords`, `triage_summary`. (프론트가 예약 추천 API 호출에 사용)

### 진행 중 vs 완료
- **진행 중**: `reply`+`quick_replies` 반환, `state_patch.active_flow = "triaging"`.
- **완료**(LLM `done=true` / 5턴 도달 / red_flag면 1턴 더): `triage_resultDB` 적재 +
  `active_flow = "idle"` + `triage_complete` 이벤트.

---

## 3. OUTPUT — `triage_resultDB` (★ 평가의 주 대상)

완료 시 [`crud/triage.build_triage_result`](../backend/app/crud/triage.py)로 1 row 적재.
**현재 triage 노드가 채우는/안 채우는 컬럼**:

| 컬럼 | 채워짐? | 값 / 비고 |
|------|---------|-----------|
| `urgency_level` | ✅ | `RED/ORANGE/YELLOW/GREEN` (engine 결정론 산출, **LLM 아님**) |
| `urgency_level_num` | ✅ | 1=RED … 4=GREEN |
| `vtl_basis` | ✅ | 판단 근거. `결정론 근거 \| LLM 임상서술` 형식 (아래 4절) |
| `chief_complaint` | ✅ | 주증상(명사) |
| `symptom_keywords` | ✅ | 키워드 list |
| `suspected_diseases` | ✅ | 의심질환 list |
| `symptom_summary` | ✅ | 한 줄 평서형 요약 |
| `symptom_onset` | △ | 슬롯 `onset`이 잡혔을 때만 |
| `red_flags` | △ | red_flag면 `["red_flag"]`, 아니면 `[]` |
| `recommended_action` | ❌ null | 현재 미설정 |
| `need_photo` | ❌ False | 현재 미설정(기본값) |
| `need_followup` | ❌ null/False | 현재 미설정 — 경과 게이트가 읽는 값. **별도 채움 필요(미정)** |
| `followup_reason` | ❌ null | 현재 미설정 |

> ⚠️ 평가팀 주의: `recommended_action`/`need_photo`/`need_followup`/`followup_reason`은
> 현재 triage 노드가 채우지 않아 항상 null/기본값이다. 이 컬럼을 평가 항목에 넣으려면
> 노드 보강이 선행돼야 한다(현재 미합의).

---

## 4. `vtl_basis` 구성 (응급도 판단 근거)

응급도는 [`engine.urgency`](../ai/agents/triage/engine.py)가 `vet_triage.json` 점수표로
**결정론** 산출한다(LLM이 등급을 정하지 않음). 따라서 근거도 점수와 일치해야 한다:

```
vtl_basis = "<결정론 근거> | <LLM 임상서술>"
```

- **결정론 근거** = `engine.urgency_basis(...)`:
  `"섹션 호흡 문제 · red_flag · breathing_difficulty=severe(+8) · 점수 12 → RED"`
  (섹션 · red_flag 여부 · 점수 기여 필드 · 합계 · 최종등급 — 채점과 100% 일치)
- **LLM 임상서술** = 노드 출력 `reason`: "왜 이 정도로 봤는지" 한두 문장.

LLM `reason`이 비면 결정론 근거만 저장된다.

---

## 5. 평가 시 입출력 재현 방법

1. 입력: `SessionContext`를 직접 구성하거나, 실제 세션의 `orch_state` 스냅샷 사용.
2. 호출: `await TriageNode().run(ctx, {})` → `AgentResult` 반환.
3. 완료 케이스 검증 대상: 반환 `events[0].data` + 적재된 `triage_resultDB` row.
4. 결정성 검증: `urgency_level`은 `engine.score`/`engine.urgency`로 재계산해 대조 가능.
