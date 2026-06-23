# followup_filter ↔ 오케스트레이터/차트 연동 계약서 (v1 draft)

> 목적: 예약 후(BOOKED) 보호자 메시지를 처리하는 **경과필터(followup_filter)** 가
> "경과가 아닌 요청(예약 변경·병원 질문 등)"을 만났을 때, **스스로 답하지 않고**
> ① 보호자에게 짧게 확인질문을 던지고 ② 확인되면 기존 에이전트(reception/schedule)로
> 넘기도록 하는 데 필요한 **에이전트 간 인터페이스**를 고정한다.
>
> 이 문서는 **구현 전 합의용 계약서**다. 합의되면 소유자별로 동시 구현한다.
> 작성: followup_filter 담당 / 합의 대상: 오케스트레이터(리드), DB·모델, 차트.

---

## 0. 용어 (혼동 방지)

- **followup = 경과(진료 사후 보고)**. "후속 질문(conversational follow-up)"이 아니다.
  코드베이스 전체에서 일관됨. `followup_filter` = **경과필터**.
- **BOOKED** = 예약 확정 이후 채팅이 열려 있는 상태. 진료 시작 10분 이내에는
  `followup_limited=true`로 이번 예약 메모 저장·예약 변경/취소만 제한하고, 채팅과 병원/예약 정보 확인은 유지한다.
  (`ai/orchestrator/state.py:build_context`)

---

## 1. 현재 코드의 한계 (계약이 필요한 이유)

| # | 사실 | 근거 |
|---|---|---|
| L1 | `AgentResult.handoff`는 **아무도 소비하지 않는다**. followup_filter가 `handoff=RECEPTION`을 세팅해도 재라우팅이 안 일어나고 캔드 멘트만 나간다. | `graph.py`는 노드 1개 실행 후 `END`. `orchestrator_service.process_turn`은 `result.handoff` 미참조. |
| L2 | BOOKED 라우팅 후보 = `[reception, followup_filter, redirect]`. **schedule(재예약) 도달 불가.** | `ai/orchestrator/router.py:_candidates` |
| L3 | `Flow.SCHEDULING` 분기가 죽어 있다(아무도 `active_flow="scheduling"`을 세팅 안 함). | `router.py:111` + grep 결과 |
| L4 | 차트는 **예약 확정 시 1회** triage+chat_history로 생성되며 **followupDB를 읽지 않는다.** 경과 요약이 차트로 가는 경로 없음. | `schedules.py:_build_chart_payload`, `ai/graph.py:_chart_node` |
| L5 | followupDB에 category/severity/요약 전용 컬럼이 없어 분류 신호가 **저장 시 유실**된다. | `ai/agents/followup_filter/repository.py:9` (TODO) |

---

## 2. 설계 원칙 (합의됨)

1. **followup_filter는 경과 분류·요약·저장만 한다.** triage/응급 재분류를 타지 않는다.
2. **경과가 아니면 followup_filter가 직접 답하지 않는다.** 병원 정보/예약 변경은
   followup_filter에 사실수집·슬롯 로직이 없으므로 **기존 에이전트(reception/schedule)** 가 처리한다.
3. **자가 판단보다 확인질문 우선.** 비경과로 보이면(애매/명확 무관) **항상 짧은 확인질문**을 던지고
   보호자 선택을 받은 뒤 넘긴다. (결정: "항상 확인질문")
4. 경과는 **요약만** 차트/EMR로 전달한다(원문 복붙·진단 금지).

---

## 3. 계약 A — followup_filter 출력 (followup_filter 담당이 구현)

### 3.1 분류 결과 (`schema.FollowupClassification` 확장)

```python
class FollowupClassification(BaseModel):
    # --- 기존 유지 ---
    is_followup: bool = False
    category: Category = Category.OTHER          # 기존 enum 재사용 (+ 아래 NEW 값)
    severity_hint: SeverityHint = SeverityHint.STABLE
    summary_delta: str = ""                       # 차트/EMR용 짧은 의료 메모
    assistant_reply: str = ""
    reason: str = ""                              # 로그 전용
    # --- NEW ---
    confidence: float = 0.0                       # 0.0~1.0
    intent: FollowupIntent = FollowupIntent.PROGRESS   # 아래 enum
```

### 3.2 비경과 의도 enum (NEW)

```python
class FollowupIntent(str, Enum):
    PROGRESS = "progress"            # 경과 보고 → 저장 + 차트 요약
    BOOKING_CHANGE = "booking_change"# 예약 시간 변경/취소 의사 → schedule로
    HOSPITAL_INFO = "hospital_info"  # 병원 위치/시간/전화/수의사 → reception으로
    AMBIGUOUS = "ambiguous"          # 의도 불명확 → 확인질문
    UNRELATED = "unrelated"          # 잡담/무관 → 가볍게 종결(redirect 성격)
```

> `Category`(symptom_change 등)는 **무엇에 관한 경과인지**, `FollowupIntent`는
> **이 발화로 무엇을 하려는지**를 가른다. 책임이 다르므로 둘 다 둔다.

### 3.3 비경과일 때 followup_filter의 `AgentResult` (확인질문 패턴)

`intent != PROGRESS` 이면 followup_filter는 **답을 만들지 않고** 확인질문을 반환한다:

```python
AgentResult(
    reply="혹시 예약 시간을 바꾸고 싶으신 걸까요, 아니면 병원 정보가 궁금하신 걸까요?",
    quick_replies=["예약 변경", "병원 정보", "지금은 상태만 공유"],
    state_patch={
        "pending_handoff": {                # NEW orch_state 키 (계약 B에서 소비)
            "original_message": ctx.user_message,   # 원래 질문 보존(핵심)
            "candidates": ["schedule", "reception"],
        }
    },
    # handoff는 '명확한' 경우에만(아래 3.4). 확인질문 단계에선 비움.
)
```

### 3.4 (선택) 즉시 handoff — 확인 없이 명확할 때만

기본은 확인질문이지만, 보호자가 **이미 명백히** 의도를 말했고 confidence가 높으면
오케스트레이터가 같은 턴에 바로 넘기도록 신호만 준다(계약 B가 소비):

```python
AgentResult(reply="", handoff=Intent.SCHEDULE,
            state_patch={"pending_handoff": {"original_message": ctx.user_message}})
```

> 결정상 기본은 3.3(항상 확인질문). 3.4는 리드와 합의되면 부가 적용.

---

## 4. 계약 B — 오케스트레이터/라우터 (★ 리드 담당, followup_filter 담당 아님)

### 4.1 `pending_handoff` 소비 (확인질문 후속 턴)

`ai/orchestrator/state.py SessionContext`에 필드 추가 + `build_context`/`save_state`에서 로드·저장:

```python
pending_handoff: dict | None = None   # {"original_message": str, "candidates": [str]}
```

`ai/orchestrator/router.py route()` 규칙 추가 (결정론, LLM 전에):

```
if ctx.pending_handoff and ctx.user_message in {"예약 변경","병원 정보","지금은 상태만 공유"}:
    target = {"예약 변경":"schedule", "병원 정보":"reception", "지금은 상태만 공유":"followup_filter"}[...]
    # 원래 질문을 복원해서 대상 에이전트가 '진짜 질문'에 답하게 한다
    if target in ("reception","schedule"):
        ctx.user_message = ctx.pending_handoff["original_message"]
    # pending_handoff 소거(state_patch로)
    return target
```

### 4.2 `handoff` 즉시 재라우팅 (계약 A 3.4 소비)

`ai/orchestrator/graph.py` 또는 `orchestrator_service.process_turn`에서:
노드 실행 결과에 `result.handoff`가 있으면 **같은 턴에 1-hop 재라우팅**한다
(`ctx.user_message`는 `pending_handoff.original_message`로 교체, 무한루프 방지 위해 1회만).

### 4.3 BOOKED 후보에 schedule 추가 (L2 해소)

```python
# router.py _candidates
if ctx.phase == Phase.BOOKED:
    return ["reception", "schedule", "followup_filter", "redirect"]  # schedule 추가
```

그리고 BOOKED에서 schedule 노드가 **재예약(시간 변경)** 을 처리할 수 있는지 확인 필요.
현재 `schedule/node.py`는 슬롯 추천만 한다 → 변경/취소 흐름이 없으면 별도 합의.

### 4.4 죽은 `Flow.SCHEDULING` 분기 정리 (L3)

소비처 없는 분기. 4.1/4.3 도입 시 함께 정리.

---

## 5. 계약 C — 경과 요약 → 차트/EMR (★ DB·모델 + 차트 담당, followup_filter 담당 아님)

> followup_filter는 "요약만 차트로". 단, 차트는 예약 확정 시 1회 생성되므로(L4)
> **차트 재생성이 아니라** 'EMR에 경과 요약을 누적 표시'하는 형태가 현실적이다.

### 5.1 followupDB 컬럼 추가 (DB·모델 담당, `app/models/followup.py` + 마이그레이션)

```
category        VARCHAR  NULL   # FollowupClassification.category
severity_hint   VARCHAR  NULL   # stable|worse|urgent_possible
# ai_summary(기존)에 누적 요약 유지, emergency_alert(기존) 유지
```

### 5.2 저장 (followup_filter 담당, 컬럼 생긴 뒤)

`repository.save_followup(..., category, severity_hint)` 인자 추가. (모델 변경 선행 필요)

### 5.3 소비 (차트/EMR 담당)

EMR/차트 화면이 `category`/`severity_hint`/`ai_summary`로 경과 요약을 표시.
`severity_hint != stable`만 하이라이트하는 식. (`emr.py`, `crud/patient.py` 등 — followup_filter 담당 아님)

---

## 6. 턴 시퀀스 (확인질문 기본 흐름)

```
[Turn N]  BOOKED, 보호자: "예약 시간 좀 바꿀 수 있어요?"
  route → followup_filter (BOOKED 후보)
  followup_filter: classify → intent=BOOKING_CHANGE(or AMBIGUOUS)
    → AgentResult(reply="예약을 변경하고 싶으신 걸까요?",
                  quick_replies=["예약 변경","병원 정보","지금은 상태만 공유"],
                  state_patch={pending_handoff:{original_message:"예약 시간 좀 바꿀 수 있어요?", ...}})

[Turn N+1] 보호자: "예약 변경"(pill)
  route: pending_handoff 감지 + pill="예약 변경" → target=schedule,
         ctx.user_message ← "예약 시간 좀 바꿀 수 있어요?"(원문 복원), pending_handoff 소거
  schedule: 실제 변경/추천 응답
```

경과인 경우는 기존과 동일: classify(PROGRESS) → 요약 머지 → followupDB 저장 → 자연스러운 응답.

---

## 7. 소유권 매트릭스

| 항목 | 파일 | 소유자 | 의존 |
|---|---|---|---|
| FollowupIntent enum, confidence, 확인질문 분기 | `ai/agents/followup_filter/{schema,agent,prompts}.py` | **followup_filter(나)** | 없음(독립 구현 가능) |
| `pending_handoff` 필드 + 로드/저장 | `ai/orchestrator/state.py`, `contracts.py` | 리드 | — |
| 라우터 pending_handoff/pill 규칙, BOOKED schedule 후보 | `ai/orchestrator/router.py` | 리드 | state 변경 |
| `handoff` 즉시 재라우팅 | `ai/orchestrator/graph.py` or `orchestrator_service.py` | 리드 | — |
| schedule 노드의 '예약 변경' 처리 가능 여부 | `ai/agents/schedule/node.py` | schedule 담당 | — |
| followupDB 컬럼 + 마이그레이션 | `app/models/followup.py` | DB·모델 | — |
| EMR/차트에서 경과 요약 표시 | `app/api/emr.py`, `crud/patient.py`, `ai/agents/chart/` | 차트 담당 | followupDB 컬럼 |

**나(followup_filter)만으로 끝까지 작동하지 않는다.** 4·5는 위 담당자들의 변경이 있어야
확인질문 후 "기존 에이전트로 잘 도와주기"가 완성된다.

---

## 8. Open Questions (합의 필요)

1. 확인질문 pill 문구/개수 표준 — UX와 i18n(번역) 영향. (`frontend i18n` 담당과 조율)
2. `handoff` 즉시 재라우팅(3.4/4.2)을 v1에 넣을지, pending_handoff(3.3/4.1)만으로 갈지.
3. schedule 노드가 **예약 변경/취소**를 실제로 지원하는가, 아니면 추천만인가. 미지원이면 별도 작업.
4. 차트는 1회 생성 유지 + EMR에 경과 누적 표시(권장) vs 차트 재생성(비용·혼선) — 차트 담당 결정.
5. `pending_handoff`를 보호자가 무시하고 새 경과를 말하면? → followup_filter가 pending 소거하고 정상 경과 처리(제안). 합의 필요.
