# MediPaw 태스크별 코드 로직 플레이북 (TASK_LOGIC.md)

> "이 태스크는 어느 파일에서 어떻게 흐르나"를 한눈에. 발표/질의응답 대비용.
> 표기: `파일:함수` 형태로 클릭 추적 가능. 모든 시간은 KST(UTC+9) 기준 저장/표시.

## 데이터 모델 한 줄 지도

```
User(보호자) ─< Pet ─< Guardian(=문진/emr 1건) ─1:1─ Schedule(예약)
                         │                         └─ Doctor
                         ├─ TriageResult(진단성, 수의사만)
                         ├─ ChatHistory(대화·사진분석)
                         ├─ Report(AI SOAP 초안)  ├─ ValidationResult
                         └─ Followup(경과보고 N건)  └─ Prescription
```
`emrid` = Guardian PK. 거의 모든 흐름이 emrid로 엮인다. 소유권 검증 경로:
`emrid → Guardian.petid → Pet.userid` (`crud/schedule.py:get_emrid_owner_userid`).

---

## 1. 보호자 문진(트리아지)

**트리거**: 보호자앱 챗봇. `POST /chat/sessions` → `POST /chat/sessions/{id}/messages`(SSE)
**파일**: [chat.py](backend/app/api/chat.py), 엔진 [ai/triage/engine.py](ai/triage/engine.py), KB [ai/triage/kb.py](ai/triage/kb.py)

1. 세션 시작 시 펫 소유권 확인 → 초기 메시지/pill 반환.
2. 메시지마다 `send_message`:
   - 비한글 입력 → 한국어 번역해 엔진 처리, **저장은 원문**(`_has_hangul`/`_translate_batch`).
   - 사진 첨부 시 ① CNN(`vision_service.analyze_skin`, 눈 키워드면 `analyze_eye`) ② GPT-vision 관찰(`_describe_chat_photo`, 진단 금지) → `photo_analysis` 저장.
   - `run_triage_turn()` 이 **결정론 walker** 한 턴 진행(자유텍스트→pill 분류만 LLM).
   - 응급도는 **규칙으로 산정**: `score = Σ pill.urgency_score + timing modifier + 종 보정`, 임계 `≥10 RED / ≥7 ORANGE / ≥4 YELLOW / else GREEN`, red_flag pill은 즉시 RED.
3. 완료(`is_complete`)되면 `_complete_and_schedule()`:
   - TriageResult 저장 + Guardian(emrid) 생성 + 카테고리 분류.
   - LangGraph **그래프 A**(`triage_complete_graph`) 백그라운드: `triage_summary(LLM 요약) ∥ schedule(슬롯)` **병렬**.
   - SSE로 `triage_complete` 이벤트 + `schedule_task_id` 전송.

**특이사항 / 방어 포인트**
- **Shadow Triage**: 보호자에겐 `_GUARDIAN_SAFE_FIELDS`(완료여부·응급도num·followup여부·키워드)만. 응급도 라벨·red_flags·추측질환은 **차단**(테스트 [shadow_triage](backend/tests/shadow_triage/test_guardian_safe.py)가 회귀 감시).
- 세션 재개: 나갔다 와도 마지막 pill 복원(`resume_quick_replies`), 문진완료·예약전이면 `resume-schedule`로 슬롯 재계산.

---

## 2. 예약 (가장 자주 질문받는 영역)

**파일**: [schedules.py](backend/app/api/schedules.py) + [crud/schedule.py](backend/app/crud/schedule.py)

| 동작 | 엔드포인트 | 핵심 로직 |
|---|---|---|
| 정기검진 예약 | `POST /schedules/checkup` | `create_checkup_schedule`: 소유권→overlap 사전검사→Guardian+Schedule INSERT→commit |
| 챗봇 예약 확정 | `POST /schedules/confirm` | `confirm_schedule`: overlap→INSERT→commit, **확정 후 그래프 B 백그라운드 실행** |
| 목록 | `GET /schedules` | 탭별 정렬: upcoming=임박순ASC / past·cancelled=최신순DESC / all=미래묶음↑ |
| 빈 슬롯 | `GET /schedules/available` | 운영시간(공휴일>특정일>주간템플릿) → 점심·마감1h전·기존예약 제외 |
| 취소 | `DELETE /schedules/{id}` | **soft cancel**(status=CANCELLED, 행 보존). 완료/과거/이미취소는 거부 |
| 변경 | `PATCH /schedules/{id}` | overlap 재검사(본인 제외) → 시간 갱신 |

**동시예약 방지(3중 방어)** — 면접 단골 질문:
1. 앱 사전검사 `has_time_overlap()` (구간 겹침, 실제 duration 반영 — 30분 격자 무관).
2. DB 제약 `no_overlap_schedule`.
3. race로 1을 통과한 겹침은 `IntegrityError`를 잡아 **500이 아니라 409**로 변환(`crud/schedule.py:167,289,510`).

**응급도 기반 가장 빠른 슬롯**(`find_earliest_slots`): 응급=오늘부터 / 준응급=+1영업일 / 일반=+2영업일부터 스캔. MCP 툴 `find_open_slots`가 이걸 호출.
**주의**: 공휴일은 2026~2027 하드코딩(`crud/schedule.py:_HOLIDAYS`) → **연도 넘어가면 갱신 필요**.

---

## 3. 예약확정 후 AI 파이프라인 (멀티에이전트 핵심)

**트리거**: `/schedules/confirm` 성공 직후 `_run_post_booking_agents` 백그라운드.
**그래프 B** ([ai/graph.py:109](ai/graph.py#L109) `post_booking_graph`):
```
chart(SOAP 초안) → validation(규칙검증) ─(emrid%5==0)→ judge → END
                                        └─(아니면)──────────→ END
```
- `_fetch_booking_context`: triage+pet+과거EMR+사진예측+**RAG 검색**(유사 상담사례 top3, 유사도≥0.60만) 수집.
- `chart`([ai/agents/chart.py](ai/agents/chart.py)): LLM이 SOAP 초안 생성 → reportDB 저장.
- `validation`([ai/agents/validation.py](ai/agents/validation.py)): **LLM 0%, 전부 규칙** — A완전성/B문진-차트일치율(<50%)/C예약안전/D응급신호정합성. validation_resultDB 저장.
- `judge`([ai/agents/judge.py](ai/agents/judge.py)): 운영품질 LLM 평가 + 턴수 코드계산. **1/5 샘플링, DB 저장 안 함, audit log만**.
- 각 노드 예외격리(한 단계 실패가 다음을 안 막음). 진행상황은 task_id 3개로 SSE 폴링.

---

## 4. 수의사 EMR / 처방전

**파일**: [emr.py](backend/app/api/emr.py) (인증: `get_current_doctor`)
- `GET /doctor/emr/queue` — 오늘 대기/완료 큐
- `GET /doctor/emr/queue/{id}` — 환자정보+문진요약+과거기록
- `GET /doctor/emr/{id}/report` — AI SOAP 초안(reportDB)
- `GET /doctor/emr/{id}/triage` — 트리아지 전체(여기서만 진단정보 노출)
- `GET /doctor/emr/{id}/validation` — 검증 결과(WARN 예외만 화면 표시)
- `POST /doctor/emr/{id}/auto-prescription` — 약 DB 기반 AI 처방전 초안

**수의사측 예약 관리**: [doctor_reservation.py](backend/app/api/doctor_reservation.py) — CRUD + `TimeSlotConflict` 예외 → 409. 응급도 표시버킷은 `urgency_num_to_visit_type` 단일 기준 공유(드리프트 방지).

---

## 5. 경과보고(Followup)

**파일**: [followup.py](backend/app/api/followup.py), 에이전트 [ai/agents/followup.py](ai/agents/followup.py)
- 게이트: triage가 `need_followup=True`로 판정 + 예약 시작 전 + 미완료일 때만 활성(`chat.py`의 `can_followup`).
- 보호자가 경과(텍스트+사진) 제출 → `run_followup_sync`가 **같은 emrid의 누적 보고 전체**를 시간순으로 모아 에이전트에 전달 → 누적 요약 1줄 생성(수의사용).
- 원본은 건별 저장, 요약은 누적 갱신.

---

## 6. 횡단 관심사 (Cross-cutting)

**인증/JWT** ([core/security.py](backend/app/core/security.py), [core/dependencies.py](backend/app/core/dependencies.py))
- access(120분)/refresh(14일), HS256, claim `sub`+`type`("user"|"doctor").
- `get_current_user`/`get_current_doctor`가 디코드→type확인→DB존재확인. **보호자/수의사 토큰 교차사용 차단**.
- 한계: refresh 회전·블랙리스트 없음(로그아웃 서버무효화 불가).

**파일 업로드** ([chat.py:427](backend/app/api/chat.py#L427))
- presigned PUT(S3 직업로드) / 직접 업로드 2경로. 검증: MIME 화이트리스트(jpeg/png/mp4) + **5MB**.
- 한계: 매직넘버 미검증, presigned는 size를 클라이언트 쿼리로 받아 위조 가능.

**DB 트랜잭션**: async SQLAlchemy. 요청세션과 백그라운드세션 분리. 예약충돌은 사전검사+DB제약+IntegrityError→409 일관. 목록은 조인으로 N+1 회피.

**MCP** ([ai/mcp_client.py](ai/mcp_client.py) ↔ [backend/scripts/mcp_rag_server.py](backend/scripts/mcp_rag_server.py))
- stdio 전송, 호출마다 서브프로세스 spawn(콜드스타트). 툴: `find_open_slots`, `search_triage_cases`.
- booking 에이전트가 LLM tool-use로 MCP 호출 → 슬롯은 DB 결과만(LLM이 지어내지 않음).

---

## 7. 자주 받는 질문 → 어디를 보면 되나

| 질문 | 답 위치 |
|---|---|
| "응급도 어떻게 정해?" | `engine.py` scoring(규칙). `PRESENTATION_DEFENSE.md` Q2 |
| "AI가 AI 평가?" | `validation.py`(규칙 100%) / `JUDGE_POLICY.md` |
| "이중예약 막아?" | `crud/schedule.py:has_time_overlap` + DB 제약 + 409 변환 |
| "보호자한테 진단정보 새?" | `chat.py:_GUARDIAN_SAFE_FIELDS` + shadow_triage 테스트 |
| "MCP 진짜 써?" | `mcp_rag_server.py` + `booking.py` tool-use 루프 |
| "중간발표보다 뭐가 나아졌어?" | `tests/eval/` + `EVAL_REPORT.md` (재현성 0% vs LLM) |
