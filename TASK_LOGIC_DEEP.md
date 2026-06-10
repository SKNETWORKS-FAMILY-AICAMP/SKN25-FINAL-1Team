# MediPaw 코드 로직 심화편 (TASK_LOGIC_DEEP.md)

> [TASK_LOGIC.md](TASK_LOGIC.md)의 후속편. 자주 캐묻히는 5개 핵심 로직을
> **실제 코드 스니펫 + 손으로 따라가는 예제(worked example)** 로 깊게 판다.
> "그 숫자 어디서 나와요?" / "동시에 누르면요?" 류 질문에 코드로 답하기 위함.

목차
1. 트리아지 엔진 — 응급도가 *계산되는 실제 코드*
2. 라이브 문진 한 턴 — *우선순위 체인*(왜 이 순서인지)
3. 예약 동시성 — *race 타임라인*과 3중 방어
4. Validation 4종 — *실제 계산식*과 예제
5. 자동 처방 — *환각(없는 약) 차단* 메커니즘
6. MCP booking — *tool-use 루프*와 슬롯 안전장치
7. LangGraph — *상태전이*와 그래프 배선(병렬/조건부)
+ 부록: Shadow Triage 필드 필터 / need_followup 게이트

---

## 1. 트리아지 엔진 — 응급도가 계산되는 실제 코드

파일: [ai/triage/engine.py](ai/triage/engine.py). **핵심: LLM이 점수를 안 매긴다.** pill에 박힌 숫자를 더할 뿐.

### 1-1. 점수 합산 → 임계 매핑 (`compute_urgency`, [engine.py:396](ai/triage/engine.py#L396))
```python
score = 0
for p in answers:
    score += p.get("urgency_score") or 0
    score += p.get("urgency_modifier") or 0   # timing pill (abrupt/rapid/acute…)

if species == "cat":
    if section in ("RESPIRATORY", "CARDIAC", "UNABLE_TO_WALK"):
        score += 1
    if section == "UROGENITAL" and gender == "male":   # 중성화 정보 없으면 보수적으로 intact 간주
        score += 2

if red_flag or score >= 10: urgency = "RED"
elif score >= 7:            urgency = "ORANGE"
elif score >= 4:            urgency = "YELLOW"
else:                       urgency = "GREEN"
```
- pill 데이터 예: `기침만 해요`=`urgency_score:2`, `숨소리 이상`=7, `입 벌리고 헐떡`=`10 + red_flag:true`.
- timing pill: `abrupt`=`urgency_modifier:3`, `rapid`=2, `acute`=1, `recent`=0.

### 1-2. 손으로 따라가기 (worked examples)
| 선택 경로 | 합산 | 결과 |
|---|---|---|
| `호흡 → 기침만(2) → 지속(5) → recent(0)` | 2+5+0=**7** | ORANGE(2) |
| `호흡 → 기침만(2) → 가끔(2) → acute(+1)` | 2+2+1=**5** | YELLOW(3) |
| `호흡 → 기침만(2) → 지속(5) → abrupt(+3)` | 2+5+3=**10** | RED(1) |
| `호흡 → 입 벌리고 헐떡(red_flag)` | — | **즉시 RED(1)** |
| 위 첫 줄 + 고양이 | 7+1=**8** | ORANGE→그대로(8<10) |

> 즉 "급성 발현(abrupt)"이 같은 증상을 ORANGE→RED로 끌어올린다. 이건 [정량평가](backend/tests/eval)의 차등 테스트가 명세 문서 오류를 잡아낸 바로 그 지점.

### 1-3. 어떤 pill이 다음 노드인지 (`advance`, [engine.py:363](ai/triage/engine.py#L363))
```python
if node_id == START_NODE:                     # 첫 화면: 증상 선택 → 섹션 첫 질문으로
    section = first.get("next_section") or first.get("value")
    return _section_entry_map().get(section)
if any(p.get("red_flag") for p in selected):  # red_flag pill 선택 → 즉시 종료
    return None
for p in selected:
    if p.get("next"): return p["next"]         # pill에 next 있으면 그쪽
return node.get("next")                         # 없으면 질문의 next, 그것도 없으면 종료
```

### 1-4. FREEFORM(트리 밖 증상, 예: 피부)도 같은 임계로 통일 ([engine.py:439](ai/triage/engine.py#L439))
트리에 없는 증상은 pill 점수가 없으니, **일반 심각도 신호를 점수화**해서 같은 compute_urgency에 태운다:
```python
FREEFORM_SIGNAL_SCORES = {
    "systemic_signs": 4,   # 전신증상(발열·기력저하)
    "rapid_worsening": 4,  # 급격 악화/번짐
    "severe_pain": 5, "active_bleeding": 4, "prolonged": 1,
}
# 단일 신호=YELLOW(4점), 두 신호=ORANGE(8점) 정도로 칼리브레이션
```
→ 트리 경로든 자유서술이든 **응급도 기준이 하나**로 통일됨.

---

## 2. 라이브 문진 한 턴 — 우선순위 체인

파일: [session.py:run_triage_turn](ai/triage/session.py#L1037). 한 메시지가 들어오면 **이 순서대로** 처리(앞에서 잡히면 거기서 종료):

```
0. 입력 정규화: raw_user_text + 사진관찰(photo_triage_text) 합쳐 user_text
1. [Red Flag] pill 클릭이 아니고 응급표현 감지 → 즉시 완료(RED, guardian_safe)   ← 최우선
2. [FREEFORM 진행중] 피부 등 자유서술 모드면 슬롯 추가질문(3~5턴) → 충족 시 완료
3. [초기 misc] 첫 화면에서 "기타/피부/눈" 또는 사진이 misc → FREEFORM 진입
4. [pill 선택] 5단 폴백으로 어떤 pill인지 결정 ↓
5. [아무것도 못 잡음] off-topic 리다이렉트 or FREEFORM으로 흡수
```

### 2-1. Red Flag 최우선 ([session.py:1056](ai/triage/session.py#L1056))
```python
clicked_pill = bool(node_id != START_NODE and _match_user_selections(node_id, raw_user_text))
red_flag = None if clicked_pill else (
    _contextual_red_flag(user_text, node_id, section) or detect_red_flag(user_text)
)
if red_flag:
    collected_info = {... "urgency_level_num": 1, "red_flags":[id], "recommended_action":"즉시 내원" ...}
    return TriageTurnResult(reply="바로 진료 예약을 도와드릴게요...", is_complete=True, guardian_safe=True)
```
- **왜 pill 클릭이면 red_flag 스캔을 끄나?** "쓰러졌어요" 카테고리 클릭이 더 긴 red flag 라벨에 부분매칭되는 오탐 방지.

### 2-2. pill 선택 5단 폴백 ([session.py:1161](ai/triage/session.py#L1161)) — LLM이 죽어도 굴러가는 이유
```python
selected = _initial_pill_selection(text) if node_id == START_NODE else []   # 1) 첫 화면 증상
if not selected: selected = _match_user_selections(node_id, text)            # 2) 라벨 정확매칭(클릭)
if not selected and user_text: selected = await _llm_classify_pills(...)     # 3) LLM 분류
if not selected and user_text: selected = _heuristic_classify_pills(...)     # 4) 규칙 휴리스틱
if not selected and user_text and node_id != START_NODE:
    selected = _fallback_free_text_selection(...)                            # 5) 자유텍스트 폴백
```
→ 3)이 실패(타임아웃/JSON깨짐)해도 4)·5)가 받아줌. **LLM은 "분류 보조"일 뿐 필수 의존이 아님.**

### 2-3. 종료 판정 (`_should_finish_triage`, [session.py:414](ai/triage/session.py#L414))
트리 끝(terminal) 도달 또는 충분히 모였을 때 완료. 완료 시 `collected_info`가 채워져 [chat.py:_complete_and_schedule](backend/app/api/chat.py#L213)로 넘어간다.

---

## 3. 예약 동시성 — race 타임라인과 3중 방어

파일: [crud/schedule.py](backend/app/crud/schedule.py). "두 보호자가 같은 시간을 동시에 누르면?"에 대한 답.

### 3-1. 겹침 판정은 점(point)이 아니라 구간(interval) (`has_time_overlap`, [schedule.py:90](backend/app/crud/schedule.py#L90))
```python
ns, ne = to_kst(new_start), to_kst(new_end)
# 같은 의사의 '활성' 예약만 본다
stmt = select(Schedule).where(
    Schedule.confirmed_time.isnot(None), Schedule.deleted_at.is_(None),
    Schedule.status != "CANCELLED", Schedule.doctorid == doctorid)
for s in result.scalars().all():
    ct = to_kst(s.confirmed_time)
    et = to_kst(s.confirmed_end_time) or ct + timedelta(minutes=s.duration_min or 30)
    if ns < et and ne > ct:        # 표준 구간 겹침 공식
        return True
```
- **왜 구간?** 50분 진료가 30분 격자에 안 맞을 때, 점 비교로는 10:30 시작이 10:00(50분) 예약과 안 겹친다고 오판. 구간이면 정확히 잡음.

### 3-2. INSERT 경로 + race 변환 (`create_checkup_schedule`, [schedule.py:125](backend/app/crud/schedule.py#L125))
```python
if await has_time_overlap(db, doctorid, kst_dt, kst_dt + timedelta(minutes=30)):
    return None, None        # ① 앱 사전검사 실패 → 호출부 409
...
db.add(schedule)
try:
    await db.commit()        # ② 통과했어도 DB no_overlap_schedule 제약이 최종 방어
except IntegrityError:
    await db.rollback()
    return None, None        # ③ race로 뚫린 충돌을 500 대신 409로 변환
```

### 3-3. 동시 클릭 타임라인 (worked example)
```
시각  보호자 A (10:00 예약)          보호자 B (10:00 예약)
t0    has_time_overlap → False        has_time_overlap → False   ← 둘 다 통과(아직 INSERT 전)
t1    INSERT + commit ✅
t2                                     INSERT + commit
t3                                     → DB no_overlap_schedule 위반 → IntegrityError
t4                                     rollback → return None → 409 "이미 예약이 있습니다"
```
→ **앱 검사만으로는 t0 race를 못 막지만, DB 제약이 최후의 진실**. 그걸 깔끔한 409로 바꾼 게 핵심.

같은 패턴이 `confirm_schedule`([510](backend/app/crud/schedule.py#L510))·`update_schedule_time`([289](backend/app/crud/schedule.py#L289))에도 동일 적용.

---

## 4. Validation 4종 — 실제 계산식

파일: [ai/agents/validation.py](ai/agents/validation.py). **전부 규칙·산수, LLM 0%** → 같은 입력=같은 결과.

### A. 데이터 완전성 ([validation.py:61](ai/agents/validation.py#L61))
```python
missing = [label for key,label in REQUIRED_FIELDS.items()
           if present.get(key) in (None,"","?","미상","알 수 없음")]
status = "PASS" if not missing else "WARN"
```
필수 5: 종·나이·성별·주증상·발현시점. 점수=`(5-누락)/5`.

### B. 문진–차트 일치도 ([validation.py:115](ai/agents/validation.py#L115))
```python
chart_text = json.dumps(chart_result, ensure_ascii=False)
matched = [k for k in keywords if k in chart_text]   # 문자열 포함 여부
overlap = len(matched) / len(keywords)
status = "PASS" if overlap >= CHART_OVERLAP_THRESHOLD else "WARN"   # 0.5
```
- 예: 문진 키워드 `[구토,설사,식욕부진]`, 차트가 `피부질환` 얘기뿐 → matched 0/3 = **0% < 50% → WARN**. "문진-차트 불일치, 확인 권고".

### C. 예약 안전성 ([validation.py:82](ai/agents/validation.py#L82))
```python
if not duration or duration <= 0: issues.append("진료시간 미산정")
if not slot_window: issues.append("예약창 비어있음")
```

### D. 응급신호 정합성 ([validation.py:184](ai/agents/validation.py#L184)) — 가장 영리한 규칙
```python
signals = _scan_red_flags(text)                     # 응급표현 사전 매칭
urgency_num = int(triage.get("urgency_level_num") or 5)
disagree = bool(signals) and urgency_num >= LOW_URGENCY_THRESHOLD   # 4
# 응급표현 감지됐는데 triage가 낮게(≥4) 봤을 때만 WARN
```
- **감지+응급도도 높음** → 두 신호 일치 → WARN 안 함(배지로 충분, 중복제거).
- **감지+응급도는 낮음** → 모순 → WARN "AI가 응급도를 낮게 봤을 수 있음, 재확인".

종합: 하나라도 WARN이면 `overall="ATTENTION"`. 수의사 화면엔 **WARN(예외)만** 표시(정상은 숨김).

---

## 5. 자동 처방 — "없는 약" 환각 차단

파일: [emr.py:generate_auto_prescription](backend/app/api/emr.py#L187). LLM이 약을 *지어내지* 못하게 하는 2중 장치.

### 5-1. 후보를 DB에서 먼저 추린다
```python
for term in suspected_diseases[:3] + symptoms[:2]:        # 증상/질환 키워드로
    rows = select(Drug).where(or_(Drug.ingredient_kr.ilike(f"%{term}%"), ...)).limit(8)
if len(candidate_drugs) < 15:                             # 부족하면 일반약으로 40개 채움
    general = select(Drug).limit(40)
drug_list_str = "\n".join(f"- {d.name} (성분: {d.ingredient_kr})" for d in candidate_drugs[:40])
```

### 5-2. LLM은 그 목록·허용값 안에서만 선택
```text
[사용 가능한 약품 목록]  ← drugsDB 실제 약만
{drug_list_str}
반드시 아래 허용값 중에서만 선택 (목록 외 값 사용 금지):
- form: PO/IV/SC/IM/외용/점안/흡입
- dosage: 0.5mg/kg … 2정
- frequency: SID/BID/TID/QID/필요시
- duration(정수): 3,5,7,10,14,30
```
→ 약품은 **DB에 실재하는 것만**, 용법은 **enum**만. **수의사 메모를 최우선 참고**. 결과는 초안 → 수의사 확인·수정 후 저장.

---

## 부록 A. Shadow Triage — 보호자 차단 필드 (정확한 코드)

[chat.py:39](backend/app/api/chat.py#L39):
```python
_GUARDIAN_SAFE_FIELDS = ("is_triage_complete", "urgency_level_num", "need_followup", "symptom_keywords")
def _guardian_safe_triage(info):
    return {k: info.get(k) for k in _GUARDIAN_SAFE_FIELDS if k in info}
```
→ `urgency_level`(라벨), `red_flags`, `suspected_diseases`, `vtl_basis`, `symptom_summary`, `recommended_action`은 **보호자에게 안 감**. 수의사 화면(`/doctor/emr/{id}/triage`)에서만 전체 노출. 회귀 테스트 [shadow_triage](backend/tests/shadow_triage/test_guardian_safe.py)가 이게 깨지면 빨갛게 뜸.

## 부록 B. need_followup 게이트 (점수 아닌 '동적 증상군')

[engine.py:compute_need_followup](ai/triage/engine.py#L300):
```python
if red_flags: return True, "응급 징후 — 경과 모니터링"          # red flag면 항상
if urgency_level_num is None or urgency_level_num >= 4:
    return False, None                                          # 일반(GREEN)은 불필요
if section in _MONITORABLE_SECTIONS: return True, ...           # 모니터링 대상 섹션
if dynamic_signals.get("rapid_worsening") or .get("active_bleeding"):
    return True, "악화·출혈 진행"                               # 동적 신호
return False, None
```
- **왜 "점수 ≤2" 단독이 아닌가?** 단순 점수컷은 "지금 아프지만 안정적"인 케이스도 followup을 켜는 오탐이 많아, **진행성/출혈성 등 '동적'인지**로 바꿈. 이 값은 triage 시 1회 산출·저장되고, 이후 [chat.py:629](backend/app/api/chat.py#L629)는 저장값을 그대로 읽음(재계산 안 함).

---

## 6. MCP booking 에이전트 — tool-use 루프 (이 프로젝트의 MCP 핵심)

파일: [ai/agents/booking.py](ai/agents/booking.py) + [ai/mcp_client.py](ai/mcp_client.py) + [backend/scripts/mcp_rag_server.py](backend/scripts/mcp_rag_server.py).
**요지**: 백엔드가 슬롯 함수를 직접 부르지 않고, **MCP 프로토콜(stdio)** 로 MCP 서버의 툴을 호출한다. 이게 "MCP 기반 자동화" 요건을 *실제로* 충족하는 부분.

### 6-1. tool-use 루프 본체 ([booking.py:89](ai/agents/booking.py#L89))
```python
tool_schemas = [s for s in await list_tool_schemas()
                if s["function"]["name"] in _AGENT_TOOLS]   # find_open_slots, search_triage_cases
for _ in range(_MAX_TOOL_ROUNDS):                            # 최대 4라운드
    response = await client.chat.completions.create(
        model=model, messages=messages, tools=tool_schemas,
        tool_choice="auto", max_completion_tokens=600)
    msg = response.choices[0].message

    if not msg.tool_calls:                                   # 더 부를 툴 없음 → 최종 답변(JSON 파싱)
        return {"agent":"booking", "proposed_slots":proposed_slots,
                "message":parsed["message"], "tool_calls":tool_calls_log}

    for tc in msg.tool_calls:                                # LLM이 요청한 툴을 MCP로 실제 호출
        if tc.function.name == "find_open_slots":
            args["limit"] = _SLOT_COUNT                       # ★ 슬롯 개수는 LLM 재량 박탈 → 항상 3개
        result = await call_tool(name, args)                 # ← MCP 프로토콜 호출(아래 6-2)
        if name == "find_open_slots":
            proposed_slots = result.get("slots") or proposed_slots   # ★ DB 결과만 보존
        messages.append({"role":"tool", "tool_call_id":tc.id, "content":json.dumps(result)})
```
**안전장치 3가지**(발표 방어용):
- **슬롯은 LLM이 지어내지 못한다** — `proposed_slots`는 `find_open_slots` 툴 결과(실제 DB)만 담음.
- **개수 고정** — LLM이 limit을 바꿔 보내도 코드가 `_SLOT_COUNT=3`으로 덮어씀.
- **확정 안 함** — booking은 *제안*만. 실제 예약 확정(락·overlap)은 사람이 슬롯 골라 `confirm_schedule`.

### 6-2. MCP 한 번 호출 = 서브프로세스 1회 ([mcp_client.py:76](ai/mcp_client.py#L76))
```python
async def call_tool(name, arguments):
    async with mcp_session() as session:          # stdio_client로 mcp_rag_server.py 서브프로세스 spawn
        result = await session.call_tool(name, arguments or {})   # initialize→call
    return _parse_tool_result(result)             # CallToolResult.content[].text(JSON) → dict
```
- 전송: **stdio** — 백엔드와 같은 venv 파이썬(`sys.executable`)으로 `mcp_rag_server.py`를 띄워 붙음.
- **콜드스타트 비용**: 호출마다 서브프로세스를 새로 띄움 → 데모/저빈도엔 OK, 고빈도는 영속세션/HTTP로 전환 후보(코드 주석에도 명시).
- 서버 쪽 `find_open_slots`([mcp_rag_server.py:132](backend/scripts/mcp_rag_server.py#L132))는 결국 [crud/schedule.py:find_earliest_slots](backend/app/crud/schedule.py#L444)를 호출 → **MCP를 통해도 동일한 DB 슬롯 로직**.

### 6-3. 한 케이스 라운드 흐름 (worked example)
```
R1: LLM → tool_calls=[find_open_slots(urgency=1, duration=40)]   (응급이라 duration 40)
     code → limit=3 강제 → MCP 호출 → {slots:[3개]}  → proposed_slots 채움
R2: LLM(슬롯 받음) → tool_calls 없음 → {"message":"가장 빠른 시간 3개 찾았어요..."} 종료
```
→ 보통 1~2라운드. 4라운드 초과 시 확보한 슬롯이라도 반환([booking.py:143](ai/agents/booking.py#L143)).

---

## 7. LangGraph 오케스트레이션 — 상태전이와 그래프 배선

파일: [ai/graph.py](ai/graph.py) + 러너/상태 [ai/tasks.py](ai/tasks.py).

### 7-1. 전체 파이프라인 상태머신 (`PipelineState`, [tasks.py:44](ai/tasks.py#L44))
```
TRIAGE_STARTED → TRIAGE_COMPLETED → SCHEDULE_PENDING → SCHEDULE_CONFIRMED
   → CHART_GENERATING ─┐
   → VALIDATION_RUNNING ┴→ COMPLETED | FAILED | PARTIAL
```
- **DB 저장 없는 런타임 상태머신** — 운영자가 로그의 `pipeline_state` 키로 현재 단계 추적(마이그레이션 불필요).

### 7-2. 그래프 B = post_booking (조건부 분기) ([graph.py:109](ai/graph.py#L109))
```python
g.set_entry_point("chart")
g.add_edge("chart", "validation")
g.add_conditional_edges("validation", _after_validation, {"judge":"judge", "skip":END})
g.add_edge("judge", END)

def _after_validation(state):                      # judge는 비용 위해 1/5만
    emrid = state.get("emrid")
    return "judge" if (emrid is not None and emrid % JUDGE_SAMPLE_RATE == 0) else "skip"
```
- 각 노드(`_chart_node`/`_validation_node`)는 ① `_task_store[tid]` 갱신(SSE용) ② `save_result(...)` DB 저장 ③ **예외 격리**(try/except로 다음 단계 안 막음).
- validation 노드는 chart 결과를 주입받음(`payload["chart_result"] = state["chart_result"]`) → B(문진-차트 일치도)가 차트를 비교 가능.
- judge 노드는 **DB 저장 없이 audit log만**(`[JudgeAudit]`).

### 7-3. 그래프 A = triage_complete (병렬) ([graph.py:192](ai/graph.py#L192))
```python
g.add_edge(START, "triage_summary")    # ┐ 둘 다 START에서 fan-out
g.add_edge(START, "schedule")          # ┘ → 병렬 실행
g.add_edge("triage_summary", END)
g.add_edge("schedule", END)
```
- **왜 병렬?** triage요약(DB/수의사용)과 schedule(슬롯 계산)은 서로 입력 의존이 없음 → 동시에 돌려 **보호자 슬롯 표시 지연을 0으로**.
- schedule 노드는 플래그로 분기: `agent = "booking" if settings.USE_MCP_BOOKING else "schedule"` ([graph.py:181](ai/graph.py#L181)).

### 7-4. 모든 에이전트 호출은 `monitor_agent`로 감싸짐 ([tasks.py:183](ai/tasks.py#L183))
```python
@monitor_agent("chart")
async def run_chart(payload, update_step, emrid, scheduleid): ...
```
- 데코레이터가 매 실행마다 **latency_ms·success·failure_reason·pet_id·request_id**를 구조화 로그로 남김:
  `logger.info("[AGENT_MONITOR] %s", json.dumps(log_data))`. → 에이전트별 성능/실패율 추적.
- `RUNNERS` dict([tasks.py:320](ai/tasks.py#L320))가 7개 러너를 이름→함수로 매핑 → 그래프 노드·`/api/agent/run`이 공유.

### 7-5. 진행상황은 in-memory task_store + SSE로 ([tasks.py:76](ai/tasks.py#L76))
```python
_task_store: dict[str, dict] = {}          # task_id → {status, step|result|detail}
_TASK_TTL_SEC = 300                         # SSE 미접속 시 5분 후 자동 정리
```
- 노드가 `_task_store[tid] = {"status":"running","step":"..."}` 갱신 → 프론트가 `GET /api/agent/sse/{task_id}`로 1초 폴링 스트리밍([router.py:97](ai/router.py#L97)).
- 완료/에러 시 `cleanup_task_after_ttl`로 TTL 정리, `safe_create_task`가 예외·취소를 자동 상태기록.
- **한계(주석에도 명시)**: 인메모리 dict라 **단일 uvicorn 프로세스 전제**. Gunicorn 멀티워커면 Redis로 교체 필요.

### 7-6. save_result 라우팅 ([tasks.py:333](ai/tasks.py#L333))
```
chart      → reportDB(ai_draft_json) + doctor_alarmDB
validation → validation_resultDB
triage     → triage_resultDB
followup   → 로그만 (followupDB는 보호자 사진/메시지 전용)
judge      → (저장 안 함, audit log만)
```

---

## 질문 → 코드 한 줄 답

| 날카로운 질문 | 코드 근거 |
|---|---|
| "응급도 7이 왜 ORANGE야?" | `compute_urgency`: `score>=7 → ORANGE` ([engine.py:419](ai/triage/engine.py#L419)) |
| "급성이면 더 위급?" | timing pill `abrupt` `urgency_modifier:3` 가산 |
| "둘이 동시에 예약하면?" | 앱검사+`no_overlap_schedule` 제약+`IntegrityError→409` |
| "차트가 엉뚱하면 알아?" | Validation B 키워드 일치율 <50% → WARN |
| "LLM이 가짜 약 쓰면?" | 자동처방: drugsDB 후보 + 허용 enum만 |
| "보호자가 응급도 봐?" | `_GUARDIAN_SAFE_FIELDS` — 응급도 라벨 차단 |
| "문진 중 LLM 죽으면?" | pill 선택 5단 폴백(휴리스틱/자유텍스트) |
| "MCP 진짜 써? 슬롯 지어내는 거 아냐?" | `call_tool`(stdio 서브프로세스) + `proposed_slots=result["slots"]`(DB만) |
| "judge는 왜 가끔만 돌아?" | `_after_validation`: `emrid % JUDGE_SAMPLE_RATE == 0` |
| "요약이랑 슬롯 왜 동시에?" | 그래프 A: `START→{triage_summary, schedule}` 병렬(의존 없음) |
| "에이전트 느린 거 어떻게 알아?" | `monitor_agent` → `[AGENT_MONITOR]` latency_ms 로그 |
| "서버 재시작하면 진행상황은?" | `_task_store` 인메모리 → 유실(멀티워커는 Redis 필요) |
