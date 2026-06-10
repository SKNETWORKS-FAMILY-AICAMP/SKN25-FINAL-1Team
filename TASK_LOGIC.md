# MediPaw 태스크별 코드 로직 플레이북 (TASK_LOGIC.md)

> "이 태스크는 어느 파일에서 어떻게 흐르나"를 끝까지 따라갈 수 있게 정리한 문서.
> 발표·질의응답에서 개발 로직 질문에 막히지 않는 게 목표.
> 표기: `파일:함수`(클릭 추적). 모든 시각은 **KST(UTC+9)** 로 저장/표시.

---

## 0. 시스템 개요

3개 프론트(보호자앱 5173 · 수의사 대시보드 5174 · 회사소개 5175) + FastAPI 백엔드(8000) + PostgreSQL(pgvector). AI는 백엔드 안에서 **LangGraph 멀티에이전트**로 동작.

**한 줄 철학**: AI는 *구조화·신호표시·초안*까지만, **의료 판단은 수의사**(Human-in-the-Loop). 보호자에겐 진단성 정보를 안 보냄(**Shadow Triage**).

### 0-1. 데이터 모델 지도 (ID 관계가 핵심)

```
User(보호자) ─< Pet ─< Guardian(=문진 1건, PK=emrid) ─1:1─ Schedule(예약)
                          │                              └─ Doctor
                          ├─ TriageResult   (응급도·증상 등 진단성, 수의사만 열람)
                          ├─ ChatHistory    (대화·사진분석 결과)
                          ├─ Report         (AI SOAP 차트 초안)
                          ├─ ValidationResult (규칙검증 결과)
                          ├─ Followup        (경과보고 N건)
                          └─ EMR ─< Prescription >─ Drug   (진료완료 후 기록)
```

- **`emrid` = Guardian PK** = 모든 흐름의 중심 키. "문진 1건"의 식별자.
- **소유권 검증 경로**: `emrid → Guardian.petid → Pet.userid` ([crud/schedule.py:get_emrid_owner_userid](backend/app/crud/schedule.py#L186)). 보호자 API는 거의 다 이걸로 "내 것인지" 확인.
- **응급도 표시 단일 기준**: `urgency_level_num`(1~5) → 화면 버킷(응급/준응급/일반)은 [engine.py:urgency_num_to_visit_type](ai/triage/engine.py#L36) 하나로만 매핑(대시보드·EMR큐·예약 모두 공유 → 드리프트 방지).

---

## 1. 인증 / 세션 (JWT)

**파일**: [api/auth.py](backend/app/api/auth.py)(보호자) · [api/doctor_auth.py](backend/app/api/doctor_auth.py)(수의사) · [core/security.py](backend/app/core/security.py) · [core/dependencies.py](backend/app/core/dependencies.py)

| 동작 | 엔드포인트 | 로직 |
|---|---|---|
| 회원가입 | `POST /auth/signup` | loginid 중복확인(409) → bcrypt 해시 저장 |
| 로그인 | `POST /auth/login` | `verify_password` → access(120분)+refresh(14일) 발급 |
| 토큰 갱신 | `POST /auth/refresh` | refresh 디코드→type/유저 확인→새 access |
| 로그아웃 | `POST /auth/logout` | **no-op**(서버 무효화 없음, 클라가 토큰 폐기) |
| 아이디 찾기 | `POST /auth/find-id` | 이름+전화 일치 시 loginid 반환 |
| 비번 찾기 | `POST /auth/find-password` | 이름+전화+id 일치 시 **임시비번 생성→해시저장→응답에 평문 반환** |

**JWT 구조**: HS256, claim `sub`(userid/doctorid) + `type`("user"|"doctor"). 토큰 검증은 의존성 주입으로:
- [dependencies.py:get_current_user](backend/app/core/dependencies.py#L44): 디코드 → `type=="user"` 확인 → DB에서 User 존재확인 → 객체 주입.
- `get_current_doctor`: 동일하나 `type=="doctor"`. **보호자/수의사 토큰 교차사용 차단**.

**보안 주의(개선 후보)**: ① refresh 회전·블랙리스트 없음(로그아웃해도 서버는 무효화 못 함) ② find-password가 임시비번을 **API 응답 본문으로 노출**(이메일 발송 아님) ③ dev `SECRET_KEY` 기본값이 compose에 박힘(운영은 env로 덮음).

---

## 2. 보호자 문진 (라이브 트리아지) — 가장 복잡한 흐름

**파일**: 엔드포인트 [api/chat.py:send_message](backend/app/api/chat.py#L297) → 엔진 [ai/triage/session.py:run_triage_turn](ai/triage/session.py) → 결정론 [ai/triage/engine.py](ai/triage/engine.py) + KB [ai/triage/kb.py](ai/triage/kb.py)

### 2-1. 한 턴(메시지)의 처리 순서
1. **검증**: content/image 둘 다 없으면 400. 세션·펫 소유권 확인.
2. **언어 처리**: 입력에 한글이 없으면(`_has_hangul`) 한국어로 번역해 엔진에 투입. **저장·표시는 보호자 원문 유지** ([chat.py:321](backend/app/api/chat.py#L321)).
3. **사진 분석**(첨부 시): ① CNN `vision_service.analyze_skin`(눈 키워드면 `analyze_eye` 추가) ② GPT-vision `_describe_chat_photo`로 "보이는 변화만 관찰"(진단 금지) → `photo_analysis` 저장.
4. **엔진 한 턴** `run_triage_turn`(아래 2-2) → SSE로 답변을 10자씩 스트리밍. UI 언어≠ko면 답변·pill을 미리 번역해 스트리밍.
5. **완료 시** `is_complete` → `_complete_and_schedule`(2-3).

### 2-2. 트리아지 엔진 = 결정론 walker + LLM 보조 ([session.py](ai/triage/session.py))
- **뼈대는 결정론**: `vet_triage.json` 의사결정트리를 노드(질문)→pill(선택지)→`next`로 walk. 응급도는 규칙으로 산정(`Σ urgency_score + timing modifier + 종 보정`, 임계 `≥10 RED/≥7 ORANGE/≥4 YELLOW/else GREEN`). red_flag pill은 **즉시 RED**.
- **LLM은 분류에만**: 자유 텍스트 → 어느 pill인지 매핑(`_llm_classify_pills`), 실패하면 휴리스틱(`_heuristic_classify_pills`)으로 폴백 → **LLM이 죽어도 문진은 굴러감**.
- **FREEFORM 모드**: 트리에 없는 기타 증상(예: 피부)은 슬롯 기반 추가질문으로 3~5턴 수집(`_FREEFORM_*`, `_planned_freeform_followup`). 같은 질문 반복 방지(`_avoid_repeated_freeform_question`).
- **Red Flag**: pill 외에 문맥 기반(`_contextual_red_flag`) + KB 키워드(`kb.detect_red_flag`, 초콜릿·쥐약 등)도 스캔.
- **RAG 주입**: 라이브 중에도 유사 상담사례를 검색해 프롬프트에 참고로 넣음(`_search_triage_rag_context`).
- **이미지 인지**: `photo_triage_text`로 사진 분석을 문진 맥락에 반영.
- 산출 `collected_info`: 응급도/주증상/발현시점/키워드/추측질환/red_flags/**need_followup** 등.

### 2-3. 문진 완료 처리 ([chat.py:_complete_and_schedule](backend/app/api/chat.py#L213))
1. `update_session_complete`(키워드 저장) + 사진예측 병합.
2. **Guardian 생성**(emrid 발급) + 세션에 emrid 연결.
3. **TriageResult 저장**(`build_triage_result`) + 카테고리 분류. *(실패 시 rollback, 문진 흐름은 유지)*
4. **LangGraph A 백그라운드 실행**(2-4).
5. 보호자에겐 `_guardian_safe_triage`로 **안전 필드만** SSE 전송 + `schedule_task_id`.

### 2-4. LangGraph A — `triage_complete_graph` ([graph.py:192](ai/graph.py#L192))
```
START ─┬─ triage_summary  (LLM이 SOAP의 S 한 줄 요약 → TriageResult.symptom_summary 갱신)
       └─ schedule/booking (슬롯 계산)        ┴─ END   ← 둘이 독립이라 병렬 → 슬롯 표시 지연 0
```
`booking`(MCP) vs `schedule`(기존)은 `settings.USE_MCP_BOOKING` 플래그로 분기.

### 2-5. 세션 재개 / 상담기록
- 상세 `GET /chat/sessions/{id}` ([chat.py:605](backend/app/api/chat.py#L605))가 재개 신호 계산: `resumable_triage`(문진 미완료) / `resumable_schedule`(완료·예약전) / `can_followup`(경과보고 가능) / `booking_complete` / `followup_closed`. 마지막 pill도 복원해서 내려줌.
- 슬롯 단계 재개: `POST /chat/sessions/{id}/resume-schedule` → 저장된 TriageResult로 schedule 에이전트 재실행, task_id만 반환(진단정보 미전송).

---

## 3. 예약 (보호자) — 동시성 3중 방어가 핵심

**파일**: [api/schedules.py](backend/app/api/schedules.py) + [crud/schedule.py](backend/app/crud/schedule.py)

| 동작 | 엔드포인트 | 함수 | 핵심 |
|---|---|---|---|
| 정기검진 예약 | `POST /schedules/checkup` | `create_checkup_schedule` | 소유권→overlap→Guardian+Schedule INSERT→commit |
| 챗봇 예약 확정 | `POST /schedules/confirm` | `confirm_schedule` | overlap→INSERT→commit + **그래프 B 실행** |
| 목록 | `GET /schedules` | `get_schedules_by_userid` | 탭별 정렬(아래) |
| 빈 슬롯 | `GET /schedules/available` | `get_available_slots` | 운영시간 기반 동적 계산 |
| 취소 | `DELETE /schedules/{id}` | `cancel_schedule` | **soft cancel**(status=CANCELLED) |
| 변경 | `PATCH /schedules/{id}` | `update_schedule_time` | overlap 재검사(본인 제외) |

**동시예약 방지 3중 방어** (단골 질문):
1. 앱 사전검사 `has_time_overlap()`([crud/schedule.py:90](backend/app/crud/schedule.py#L90)) — 30분 격자가 아니라 **실제 duration 구간 겹침**으로 판정.
2. DB 제약 `no_overlap_schedule`.
3. race로 1을 통과한 충돌은 `IntegrityError`를 잡아 **500이 아니라 409**로 변환([167](backend/app/crud/schedule.py#L167)·[289](backend/app/crud/schedule.py#L289)·[510](backend/app/crud/schedule.py#L510)).

**목록 탭 정렬**([get_schedules_by_userid](backend/app/crud/schedule.py#L196)): upcoming=임박순ASC / past·cancelled=최신순DESC / all=미래묶음(임박순)↑ + 과거묶음(최신순)↓. N+1 방지로 Schedule+Pet+Doctor+Category 한 쿼리 조인.

**빈 슬롯 계산**([get_available_slots](backend/app/crud/schedule.py#L339)): 운영시간 우선순위(특정일 오버라이드 > 주간 템플릿 > 기본 평일 09-18) → 점심·마감1시간전·기존예약 제외 → `duration_min` 기반 **연속 슬롯** 계산. 공휴일은 2026~2027 하드코딩(`_HOLIDAYS`, **연도 넘어가면 갱신 필요**).

**응급도 기반 가장 빠른 슬롯**([find_earliest_slots](backend/app/crud/schedule.py#L444)): 응급(num1)=오늘부터 / 준응급(2~3)=+1영업일 / 일반(4~5)=+2영업일부터 스캔 → MCP 툴 `find_open_slots`가 호출.

---

## 4. 예약 확정 후 AI 파이프라인 (멀티에이전트 본체)

**트리거**: `/schedules/confirm` 성공 → `_run_post_booking_agents` 백그라운드 태스크 → **LangGraph B**.

### 4-1. `post_booking_graph` ([graph.py:109](ai/graph.py#L109))
```
chart(SOAP 초안) → validation(규칙검증) ─(emrid % 5 == 0)→ judge → END
                                        └─(아니면)──────────────→ END
```
- **컨텍스트 수집** [_fetch_booking_context](backend/app/api/schedules.py#L291): triage + pet + 과거 EMR + 사진예측 + **RAG 검색**(유사사례 top3, 유사도≥0.60만 주입).
- **payload 조립** [_build_payloads](backend/app/api/schedules.py#L372): chart/validation/judge 각자 입력 dict 구성(순수함수).
- 각 노드 **예외 격리** — 한 단계 실패가 다음을 안 막음. 진행상황은 task_id 3개로 SSE 폴링.

### 4-2. 에이전트별 상세

**① triage 요약** [agents/triage.py:run_triage](ai/agents/triage.py#L76) — 문진 대화를 **SOAP의 S(주관적) 한 줄 평서형**으로 LLM 요약 → `symptom_summary` DB 갱신. 응급도 등은 엔진 결과 유지.

**② schedule** [agents/schedule.py](ai/agents/schedule.py) — 체중·증상복잡도·재진여부로 진료시간 산정. VTL Level이 `slot_window` 하한선(하향 금지). 종별 강제 상향(고양이 요도폐색→당일, 개 GDV→즉시). **LLM 실패 시 응급도 기반 fallback**.

**③ booking (MCP)** [agents/booking.py](ai/agents/booking.py) — *이 프로젝트의 MCP 핵심 결과물*. LLM tool-use 루프로 MCP 툴 `find_open_slots`/`search_triage_cases`를 **MCP 프로토콜로** 호출. 슬롯은 LLM이 지어내지 않고 DB 결과만(`_SLOT_COUNT=3` 코드 강제). 제안만, 확정은 사람이.

**④ chart** [agents/chart.py](ai/agents/chart.py) — **gpt-4o**(추론부담 큼). 6단계 추론(엔티티→타임라인→감별진단→근거→누락→SOAP)으로 SOAP 초안 + 감별진단 + 권장검사 + **수의사 확인질문** + 처방초안 생성 → reportDB 저장. 확정 진단 금지.

**⑤ validation** [agents/validation.py](ai/agents/validation.py) — **LLM 0%, 전부 규칙**. A완전성(필수5필드)/B문진-차트일치율(<50% WARN, 문자열매칭)/C예약안전/D응급신호정합성(응급표현↔응급도 불일치 시만 WARN). 같은 입력=같은 결과. → validation_resultDB 저장.

**⑥ judge** [agents/judge.py](ai/agents/judge.py) — 운영품질 LLM 평가(완전성·효율·일관성·구조화) + **턴수는 코드 계산**. **1/5 샘플링, DB 저장 X, audit log만**. 환자안전 아닌 시스템 품질 모니터링(콜센터 QA).

---

## 5. 경과보고 (Followup)

**파일**: [api/followup.py](backend/app/api/followup.py) + [agents/followup.py](ai/agents/followup.py)
- **게이트**: triage `need_followup=True` + 예약 시작 전 + 미완료일 때만 활성([chat.py:can_followup](backend/app/api/chat.py#L615)).
- 보호자가 경과(텍스트+사진) 제출 → `run_followup_sync`가 **같은 emrid의 누적 보고 전체**를 시간순으로 모아 에이전트에 전달 → 누적 요약 1줄 생성(수의사용). 원본은 건별 저장, 요약은 누적 갱신.

---

## 6. 수의사측 — EMR / 처방 / 대시보드 / 스케줄

### 6-1. EMR 큐·조회 ([api/emr.py](backend/app/api/emr.py), 인증 `get_current_doctor`)
- `GET /doctor/emr/queue` — 오늘 진료 대기/완료 큐.
- `GET /doctor/emr/queue/{id}` — 환자정보+문진요약+과거기록.
- `GET /doctor/emr/{id}/report` — AI SOAP 초안(reportDB).
- `GET /doctor/emr/{id}/triage` — 트리아지 전체(**여기서만** 진단정보 노출).
- `GET /doctor/emr/{id}/validation` — 검증/judge 결과(WARN 예외만 화면 표시).

### 6-2. AI 자동 처방 ([emr.py:generate_auto_prescription](backend/app/api/emr.py#L187))
`POST /doctor/emr/{id}/auto-prescription`:
1. triage+pet+guardian 조회 → 나이 계산.
2. 증상/의심질환 키워드로 **drugsDB 후보 약품 검색**(성분 ilike), 부족하면 일반약으로 채워 40개.
3. LLM(gpt-4o)에 후보목록 제시 → **허용값(form/dosage/frequency/duration)만 골라** JSON 처방 생성. **수의사 메모를 최우선 참고**.
4. 결과는 초안 — 수의사가 확인·수정 후 저장.

### 6-3. 수의사 예약 관리 ([api/doctor_reservation.py](backend/app/api/doctor_reservation.py))
CRUD + `TimeSlotConflict` 예외→409. 응급도 표시는 `urgency_num_to_visit_type` 공유. 챗봇 문진 결과가 있으면 그 응급도 우선.

### 6-4. 오늘 대시보드 ([api/dashboard.py](backend/app/api/dashboard.py))
`GET /dashboard/today` — 당일 예약 목록 + 요약(전체/대기/응급/완료 카운트). 진료사유는 guardian 메모 > 주증상 > 요약 > 키워드 순.

### 6-5. 스케줄 세팅 ([api/settings.py](backend/app/api/settings.py))
운영시간/주간 템플릿(요일별 is_open·영업·점심)/특정일 휴무. 휴무일 추가 시 **기존 예약 충돌 검사**(`has_existing_reservations`). 기본 주간(`_DEFAULT_WEEK`): 평일 09-18, 주말 휴무.

---

## 7. 환자 컨텍스트 빌더 (재진 판단의 근거)

[crud/patient.py:build_patient_context](backend/app/crud/patient.py#L137) — chart/schedule 에이전트와 챗봇이 공유하는 "이 환자 한눈에" dict:
- 프로필 + **EMR 이력**(수의사 메모) + **처방 이력**(N+1 방지 일괄조회) + **만성질환 감지**(메모 키워드: 피부염/외이염/당뇨/신부전) + **재방문 패턴**(평균 간격·정기/비정기) + 과거 triage + followup 이력 + **visit_type**(initial/returning).
- `emr_history`가 있으면 재진, 없으면 초진으로 간주(chart/schedule 분기).

---

## 8. 횡단 관심사

**파일 업로드** ([chat.py:427~](backend/app/api/chat.py#L427)): presigned PUT(S3 직업로드) / 직접 업로드 2경로. MIME 화이트리스트(jpeg/png/mp4) + **5MB**. 한계: 매직넘버 미검증, presigned size를 클라 쿼리로 받아 위조 가능.

**다국어/번역** ([chat.py:_translate_batch](backend/app/api/chat.py#L492)): ko/en/ja/zh. 입력경로(비한글→ko 번역 후 엔진) + 표시경로(ko→UI언어). 실패 시 원문 폴백(화면 안 비게). DB엔 항상 한국어 원문 저장(수의사 차트·재번역 원본).

**DB 트랜잭션**: async SQLAlchemy. 요청세션과 백그라운드세션 분리(`AsyncSessionLocal`). 예약충돌은 사전검사+DB제약+IntegrityError→409 일관. 목록은 조인으로 N+1 회피.

**관측성**: Langfuse 콜백([observability.py](ai/observability.py)) — 에이전트별 trace(`run_name`), validation은 규칙결과를 점수로 push, judge/RAG 품질도 trace.

**MCP** ([ai/mcp_client.py](ai/mcp_client.py) ↔ [backend/scripts/mcp_rag_server.py](backend/scripts/mcp_rag_server.py)): stdio 전송, 호출마다 서브프로세스 spawn(콜드스타트). read-only 툴 `find_open_slots`/`search_triage_cases`. 데모/저빈도엔 충분, 고빈도는 영속세션/HTTP로 전환 고려.

**알람** ([api/alarm.py](backend/app/api/alarm.py), [crud/alarm.py](backend/app/crud/alarm.py)): 예약 확정 시 수의사에게 알람 생성(실패해도 예약은 성공 — try/except 격리).

---

## 9. 자주 받는 질문 → 어디를 보면 되나

| 질문 | 답 위치 |
|---|---|
| 응급도 어떻게 정해? | `engine.py` scoring(규칙) · `PRESENTATION_DEFENSE.md` Q2 |
| AI가 AI 평가하는 거 아냐? | `validation.py`(규칙 100%) · `JUDGE_POLICY.md` |
| 이중예약 어떻게 막아? | `crud/schedule.py:has_time_overlap` + DB 제약 + 409 변환 |
| 보호자한테 진단정보 새? | `chat.py:_GUARDIAN_SAFE_FIELDS` + shadow_triage 테스트 |
| MCP 실제로 써? | `mcp_rag_server.py` + `booking.py` tool-use 루프 |
| 문진 LLM 죽으면? | `session.py` 휴리스틱 폴백 + `schedule.py` fallback |
| 사진 분석은? | CNN `vision_model.py` + GPT-vision `chat.py:_describe_chat_photo` |
| 재진/초진 구분은? | `patient.py:build_patient_context` 의 emr_history 유무 |
| 다국어 입력 처리? | `chat.py:_has_hangul` + `_translate_batch` |
| 차트는 어떤 모델? | chart=gpt-4o, 나머지=`settings.OPENAI_MODEL` |

---

## 10. 알려진 한계 / 개선 후보 (질문 대비 솔직 정리)

- 인증: refresh 회전·블랙리스트 없음, find-password 임시비번 응답노출.
- 업로드: 매직넘버 미검증, presigned size 위조 가능.
- 공휴일 2026~2027 하드코딩(연도 갱신 필요).
- `_task_store` 인메모리 dict → 재시작/멀티워커 시 진행상황 유실(Redis 후보).
- MCP 매 호출 서브프로세스 spawn(콜드스타트) → 영속세션/HTTP 후보.
- 수의사 자동배정이 "첫 번째 수의사" 고정([schedules.py:50](backend/app/api/schedules.py#L50)) — 다(多)수의사 확장 시 로직 필요.
