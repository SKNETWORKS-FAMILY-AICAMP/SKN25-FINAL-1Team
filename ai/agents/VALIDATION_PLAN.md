# Validation Agent 설계 문서 

## 개요

MediPaw Validation Agent는 AI가 만든 결과물(문진, 예약, 차트)이 제대로 만들어졌는지 사후에 검증하는 에이전트다. 의료적 판단을 하지 않고, 운영 품질 신호만 감지한다.

- 결과를 `validation_resultDB`에 저장
- 어드민 패널 Validation 탭에서 조회
- 처음엔 수동 실행, 이후 자동화 확장 가능

---

## 1. 진입점 설계

### 함수 시그니처

```python
run_validation(scheduleid: int, db: AsyncSession) → dict
```

기존 코드(`ai/agents/validation.py`)의 `run_validation`은 `payload: dict`를 조립해서 넘겨받는 구조였다.
새로 짜는 버전은 `scheduleid`와 `db`만 받고, 함수 안에서 직접 DB를 조회한다.

### 왜 scheduleid 하나만 받는가

scheduleid 하나면 검증에 필요한 모든 데이터를 체인으로 찾을 수 있다.

```
scheduleid
  → scheduleDB          (emrid, doctorid, confirmed_time, duration_min)
  → guardianDB          (emrid → petid)
  → petDB               (species, gender, birth_date)
  → triage_resultDB     (emrid 기준 조회, chief_complaint, symptom_onset, symptom_keywords)
  → reportDB            (scheduleid 기준 직접 조회, ai_draft_json)
  → chat_historyDB      (emrid 기준 조회, messages, keywords)
```

코드에서 확인된 사항:
- `scheduleDB.emrid` → `guardianDB.emrid`: FK 직접 연결 가능
- `guardianDB.petid` → `petDB.petid`: FK 연결 가능
- `triage_resultDB`는 `emrid` 컬럼만 있고 `scheduleid`는 없음 → emrid 경유 필수
- `reportDB`에는 `scheduleid` 컬럼이 있어 직접 조회 가능
- `chat_historyDB`에는 `emrid` 컬럼이 있음 (nullable)

### 왜 수동 실행으로 시작하는가

`ai/graph.py`의 `post_booking_graph`는 현재 `chart` 노드만 있고 validation 노드는 연결되어 있지 않다.
`schedules.py`에도 validation 실행 코드가 placeholder 상태로만 있다.
수동으로 먼저 만들고 확인 후 연결한다.

---

## 2. 데이터 로딩 분리

```
_load_data(scheduleid, db)
  → schedule, pet, triage, report, chat_history 반환
  → schedule 자체가 없으면 None 반환 → run_validation 즉시 종료
  → triage / report / chat_history가 없으면 None으로 반환 → 해당 체크가 SKIPPED
```

---

## 3. Check 1 — Triage 에이전트 품질 검증

Check 1은 네 파트로 나뉜다. 모두 "triage 에이전트가 제대로 일했냐"를 다른 각도에서 본다.

| 파트 | 질문 | 데이터 출처 |
|---|---|---|
| 1A | 보호자 입력 항목이 빠짐없이 채워졌나 (완전성) | pet, triage |
| 1B | 보호자가 한 말 기반으로 키워드가 제대로 추출됐나 (추출 품질) | chat vs triage |
| 1C | 보호자 말에 응급 표현이 있는데 응급도가 낮게 책정됐나 (외부 시선) | chat 발화 → RED_FLAG_LEXICON vs urgency |
| 1D | triage 에이전트 자신의 red_flags와 응급도 판단이 일치하는가 (내부 일관성) | triage.red_flags vs urgency |

triage 자체가 없으면 1A/1B/1C/1D 모두 **SKIPPED**.

---

### 3A. Triage 완전성 — 보호자 입력 항목이 채워졌나

체크 대상 (자동으로 채워지지 않는 항목만):

| 항목 | 출처 | 없을 수 있는 이유 |
|---|---|---|
| 종 (species) | petDB | 보호자가 등록 안 함 |
| 생년월일 (birth_date) | petDB | 보호자가 등록 안 함 |
| 성별 (gender) | petDB | 보호자가 등록 안 함 |
| 주증상 (chief_complaint) | triage_resultDB | 보호자가 말 안 함 |
| 발현시점 (symptom_onset) | triage_resultDB | 보호자가 말 안 함 |
| 증상 키워드 (symptom_keywords) | triage_resultDB | 추출 실패 가능 |

- `urgency_level_num`은 triage 에이전트가 자동 계산, DB에서 NOT NULL → 체크 대상 아님
- triage가 없으면 → **SKIPPED** (문진 미실행 상태)
- 점수: 6개 중 채워진 개수 × 10/6 → `completeness_score` 저장

```
6/6 → 10.0점 (PASS)
5/6 미만 → WARN
```

### 3B. Triage 유효성 — 문진 에이전트가 제대로 일했나

**핵심 질문**: "보호자가 실제로 한 말을 기반으로 triage 결과가 만들어졌는가?"

완전성은 "채워졌냐"만 본다. 보호자가 말한 적 없는 키워드가 triage 결과에 있거나, 실제 언급한 증상이 누락됐으면 hallucination 또는 추출 실패다.

**방식 — LLM 판단**

키워드 기반 집합 비교를 쓰지 않는다.

- `chat_historyDB.keywords`는 채팅 중 실시간 추출이라 오추출·누락 가능성이 있어 비교 기준으로 불안정
- 보호자 발화 원문(`chat_historyDB.messages`에서 `role: "user"` 텍스트 합산)을 1차 소스로 사용
- 원문과 `triage_resultDB.symptom_keywords`를 LLM에 넘겨 판단 요청
- "밥을 안 먹어요" → "식욕감퇴" 같은 자연어 해석을 LLM이 처리하므로 false positive 없음

**LLM 입력 구조**

```
보호자 발화 원문: "우리 강아지가 어제부터 밥을 잘 안 먹고 많이 처져있어요. 토도 두 번 했어요."
triage 추출 키워드: ["식욕감퇴", "무기력", "구토", "발열"]
```

**LLM에게 묻는 것**

- 보호자 발화 기준으로 triage 키워드가 적절히 반영됐는가?
- 보호자가 언급하지 않은 증상이 추가됐는가? (hallucination)
- 보호자가 언급했는데 triage에서 누락된 증상이 있는가?
- 결론: PASS / WARN + 이유 한 줄

**LLM 출력 예시**

```json
{"result": "WARN", "detail": "발열은 보호자 발화에 언급되지 않았으나 triage에 포함됨 (hallucination 의심)"}
{"result": "PASS", "detail": "보호자 발화의 주요 증상이 triage 키워드에 적절히 반영됨"}
```

**WARN 조건**

LLM이 WARN 반환 → **WARN** + LLM이 준 detail을 checks.triage.checks에 저장

**보호자 발화 텍스트 합산 방법**

`chat_historyDB.messages`에서 `role: "user"`인 항목만 필터링 후 `" ".join(content)` 으로 이어붙인다.

**SKIPPED 조건**

- `chat_historyDB`에 해당 emrid 데이터 없음
- `chat_historyDB.messages`가 비어있음
- `role: "user"` 발화가 하나도 없음 (데이터 없음 ≠ 문제 있음이라 WARN 아님)
- `triage_resultDB.symptom_keywords`가 비어있음

> ⚠️ **주의**: chat_historyDB의 키워드 컬럼명은 `keywords` (symptom_keywords 아님)

---

### 3C. Triage 응급도 정합성 — 응급 표현과 응급도 판단이 일치하는가

**핵심 질문**: "보호자가 응급을 시사하는 말을 했는데 triage 에이전트가 응급도를 낮게 책정하지 않았나?"

1B가 "키워드를 제대로 뽑았냐"를 보는 것과 달리, 1C는 "응급도 판단 자체가 말이 되냐"를 본다.

**감지 방식**

보호자 발화(chat_historyDB.messages에서 role=user) 전체 텍스트를 응급 표현 사전과 매칭한다.

**사전 방식: 하드코딩 (의도적 선택)**

- 재현성과 감사 가능성이 중요한 의료 맥락에서는 결과가 항상 동일하게 나오는 게 우선
- LLM 대비 false positive 제어가 쉬움
- 표현이 추가될 경우 코드 수정 필요 — 추후 `red_flag_lexicon` DB 테이블로 분리 가능하나 현재는 하드코딩으로 시작

응급 표현 사전 (RED_FLAG_LEXICON, 하드코딩):

| 카테고리 | 표현 예시 |
|---|---|
| 호흡 곤란 신호 | 숨을 못, 헐떡, 청색, 혀가 파 |
| 의식 저하 신호 | 의식이 없, 쓰러, 기절, 축 늘어 |
| 경련 지속 신호 | 경련, 발작, 경기, 몸을 떨 |
| 다량 출혈 신호 | 피를 많이, 토혈, 혈변, 코피가 멈 |
| 중독/이물 신호 | 삼켰, 중독, 초콜릿, 양파, 쥐약 |
| 쇼크 의심 신호 | 잇몸이 하얗, 몸이 차갑, 축 처져 |

**WARN 조건**

응급 표현이 감지됐는데 `triage_resultDB.urgency_level_num ≥ 4` (낮음으로 책정)이면 → **WARN**

응급 표현이 감지됐고 응급도도 높게 책정됐으면 → PASS (두 신호가 일치)
응급 표현이 감지 안 됐으면 → PASS

**SKIPPED 조건**

- chat_historyDB에 해당 emrid 데이터 없음
- `role: "user"` 발화가 하나도 없음 (감지 대상 텍스트 없어서 판단 불가)

---

### 3D. Triage 응급도 판단 품질 — 에이전트 자신의 판단이 일관되는가

**핵심 질문**: "triage 에이전트가 스스로 감지한 위험 신호와 자신이 내린 응급도가 일치하는가?"

1C는 보호자 발화(외부)를 기준으로 보는 것이고, 1D는 triage 에이전트 자기 자신의 출력물 안에서 모순을 찾는다.

triage 에이전트는 두 가지를 동시에 출력한다:
- `red_flags`: 에이전트가 스스로 감지한 위험 신호 목록
- `urgency_level_num`: 에이전트가 스스로 내린 응급도

이 둘이 서로 모순되면 에이전트 내부 추론이 일관되지 않은 것이다.

**WARN 조건**

- `red_flags`가 비어있지 않은데 `urgency_level_num ≥ 4` (낮음으로 책정) → **WARN**
  - 에이전트가 위험 신호를 감지해놓고 응급도를 낮게 냄 (자기 모순)
- `vtl_basis`가 null 또는 빈 값 → **WARN**
  - 응급도 판단 근거가 기록되지 않음 (추론 과정 누락)

**PASS 조건**

- `red_flags`가 있고 urgency도 높게 책정됨 (일치)
- `red_flags`가 비어있고 urgency도 낮음 (일치)
- `vtl_basis`가 있음

**SKIPPED 조건**

- triage 자체가 없음

---

## 4. Check 2 — 스케줄 에이전트 품질 검증

**핵심 질문**: "스케줄 에이전트가 빈 슬롯을 제대로 탐색해서 예약을 잘 잡았는가?"

confirmed_time 유무에 따라 SKIPPED 범위가 다르다:

- **2A**: confirmed_time과 무관하게 항상 실행 (duration_min만 보면 됨)
- **2B, 2C, 2D**: `confirmed_time`이 없으면 **SKIPPED** (예약 미확정 상태에서 시간 기반 판단 불가)

| 파트 | 질문 |
|---|---|
| 2A | 진료 시간(duration_min)이 합리적으로 산출됐나 |
| 2B | 응급도에 맞는 시간대에 예약이 잡혔나 (핵심) |
| 2C | 의사 근무시간 안에 예약이 잡혔나 |
| 2D | 선택한 슬롯이 실제로 비어있었나 (사후 감사) |

### 4A. 진료 시간 합리성

- `duration_min ≤ 0` → **WARN** (LLM 산출 실패)
- `duration_min > 240` → **WARN** (4시간 초과, 비정상)
- 그 외 → PASS

### 4B. 응급도 vs 예약 시간 적절성 (핵심 체크)

스케줄 에이전트는 urgency_level_num을 보고 "이 환자를 얼마나 빨리 봐야 하냐"를 판단해서 슬롯을 추천한다. 그 판단이 맞는지 검증한다.

필요한 데이터:
- `triage_resultDB.urgency_level_num`
- `scheduleDB.confirmed_time` (예약된 시간)
- `scheduleDB.created_at` (예약이 만들어진 시간)

기준:

| urgency_level_num | 응급도 | confirmed_time 기준 |
|---|---|---|
| 1 ~ 2 | 즉시 / 당일 | 당일 (created_at 기준 당일) |
| 3 | 48시간 이내 | created_at + 2일 이내 |
| 4 ~ 5 | 일반 | created_at + 3일 이내 |

기준 초과 시 — 당일 슬롯 가용 여부 확인 후 판단:

| 당일 슬롯 상황 | 판단 |
|---|---|
| 슬롯 없음 (근무 없음 또는 모두 예약됨) | **PASS** "당일 슬롯 없어 N일 후 최선 배정" |
| 슬롯 있었음 | **WARN** "응급도 권고 초과 — 사용자 선택" |
| 판단 불가 (근무표 정보 부족) | **WARN** (보수적으로 플래그) |

- 기준 이내면 → **PASS**

**당일 슬롯 계산 방법** (`_has_same_day_slots`):

```
1. created_at 요일 기준 근무표 조회 (VetWeeklySchedule → HospitalWeeklySchedule fallback)
2. is_open=False 또는 근무표 없음 → False (슬롯 없음)
3. 총 근무 시간(분) = end_time - start_time - 점심 시간
4. 당일 이미 확정된 예약 duration_min 합산 (현재 schedule 제외)
5. (총 근무 시간 - 예약 합산) >= duration_min 이면 True (슬롯 있음)
   → 단순 합산 방식. 단편화(예: 15분짜리 빈틈만 남은 경우)는 미고려
```

**SKIPPED 조건**

- triage가 없어서 urgency_level_num을 알 수 없음

### 4C. 근무시간 준수

조회 순서: `VetWeeklySchedule(doctorid, day_of_week)` → 없으면 `HospitalWeeklySchedule(hospitalid, day_of_week)`

- `VetWeeklySchedule` 없고 `doctor.hospitalid`가 null → HospitalWeeklySchedule fallback 불가 → **SKIPPED**
- 두 테이블 모두 해당 요일 근무표 없음 → **SKIPPED**
- `is_open = False` (휴무일) → **WARN**
- `confirmed_time.time() < start_time` → **WARN** (근무 시작 전)
- `(confirmed_time + duration_min).time() > end_time` → **WARN** (근무 종료 후 넘어감)
- 점심 시간(lunch_start ~ lunch_end)과 겹침 → **WARN**

### 4D. 빈 슬롯 실제 검증 (사후 감사)

`backend/app/crud/schedule.py`의 `has_time_overlap` 함수를 재사용한다.

```python
has_time_overlap(db, doctorid, confirmed_time, confirmed_end_time or confirmed_time+duration_min, exclude_schedule_id=scheduleid)
```

- 겹치는 예약 있음 → **WARN** (에이전트가 충돌 슬롯 선택)
- 겹치는 예약 없음 → PASS

> DB EXCLUSION constraint가 예방하고 있어 실제 WARN 발생 확률은 낮지만, 에이전트 판단의 사후 감사 목적으로 유지

---

## 5. Check 3 — Chart 정합성

Rule-based → LLM 2단계 방식. 구조 오류는 rule이 빠르게 잡고, 내용 품질은 LLM이 평가한다.

**1~4단계: Rule-based 구조 체크 (앞 단계 실패 시 즉시 반환, LLM 호출 안 함)**

```
1단계: report 자체가 없는가?          → SKIPPED (차트 미생성)
2단계: ai_draft_json이 dict가 아닌가? → WARN (차트 형식 오류)
3단계: intake_summary가 없는가?       → WARN (차트 구조 이상)
4단계: key_symptoms가 비어있는가?      → WARN (증상 미기록)
```

**5단계: LLM — 내용 품질 평가 (1~4단계 모두 통과한 경우에만 실행)**

LLM 입력:
- triage: `chief_complaint`, `urgency_level`, `symptom_keywords`
- ai_draft_json 핵심 필드만 추출:
  - `intake_summary` (guardian_report, key_symptoms, suspected_diseases)
  - `soap.S` (보호자 호소 정리)
  - `soap.A` (감별진단)
  - `differential_diagnosis` (질환별 근거/반증)
- 제외 필드: `thinking` (내부 추론, 길고 판단에 불필요), `soap.O` (검사 전 빈 항목), `soap.P`, `recommended_tests`, `missing_info`, `vet_questions`, `cautions`

LLM에게 묻는 것:
- triage 결과 기준으로 AI 차트 draft가 임상적으로 말이 되는가?
- triage에 있는 증상이 차트에서 누락됐거나 모순되는 내용이 있는가?
- 결론: PASS / WARN + 이유 한 줄

LLM 출력 예시:
```json
{"result": "WARN", "detail": "triage에서 경련 의심 기록됐으나 차트 draft에 언급 없음 — 누락 의심"}
{"result": "PASS", "detail": "triage 증상과 차트 내용이 임상적으로 일관됨"}
```

- `consistency_score`: PASS → 10.0 / WARN → 5.0 (정성 평가라 단계적 점수 사용)

---

## 6. 에러 격리

세 체크 각각을 독립 try/except로 감싼다. 하나가 실패해도 나머지는 계속 실행된다.
실패한 체크는 `status: "ERROR"`, `detail: 에러 메시지`로 저장.

---

## 7. 중복 실행 처리 (upsert)

`validation_resultDB`에서 `scheduleid` 기준으로 조회해서 있으면 UPDATE, 없으면 INSERT.

---

## 8. 종합 판단

| 상태 | 의미 | overall 영향 |
|---|---|---|
| PASS | 정상 | 없음 |
| WARN | 수의사 확인 권고 | ATTENTION |
| SKIPPED | 조건 미충족 (정상) | 없음 |
| ERROR | 시스템 오류 | 없음 |

- Check 1A, 1B, 1C, 1D, 2A, 2B, 2C, 2D, 3 중 하나라도 WARN → `overall = "ATTENTION"`
- 아니면 → `overall = "OK"`

summary 예시:
```
"트리아지 완전성, 스케줄 근무시간 이탈 — 수의사 검토 권고"
"특이 검증 이슈 없음"
```

---

## 9. 코드 검토 확인 사항

| 항목 | 내용 |
|---|---|
| chat_historyDB 키워드 컬럼 | `keywords` (symptom_keywords 아님) |
| triage 조회 경로 | `scheduleid → emrid → triage_resultDB` (petid 경유 아님) |
| `has_time_overlap` 재사용 | Check 2D에서 기존 함수 그대로 사용 가능 |
| report 조회 | `scheduleid` 컬럼 있어서 직접 조회 가능 |
| graph.py | validation 노드 미연결 상태 → 수동 실행이 현실적 |

---

## 10. 구현 순서

### 0단계 — 상수 선언
```
RED_FLAG_LEXICON       보호자 일상어 기반 응급 표현 사전
CHART_OVERLAP_THRESHOLD = 0.5
LOW_URGENCY_THRESHOLD   = 4
URGENCY_MAX_DAYS        = {1: 0, 2: 0, 3: 2, 4: 3, 5: 3}
```

### 1단계 — 데이터 로딩
```
_load_data(scheduleid, db)
  → schedule, guardian, pet, triage, report, chat_history, doctor 반환
  → schedule 없으면 None 반환 → run_validation 즉시 종료
```

### 2단계 — Triage 검증 모듈
```
validate_triage(pet, triage, chat_history)
  내부: 1A 완전성 (rule-based)
        1B 유효성 (LLM — 보호자 발화 원문 vs triage.symptom_keywords)
        1C 응급도 정합성 외부 (rule-based — RED_FLAG_LEXICON vs urgency)
        1D 응급도 판단 내부 (rule-based — triage.red_flags vs urgency)
  → triage_verdict
```

### 3단계 — Schedule 검증 모듈
```
validate_schedule(schedule, triage, doctor, db)
  내부: 2A duration 합리성 / 2B 응급도 vs 예약 타이밍 / 2C 근무시간 / 2D 빈 슬롯 감사
  → schedule_verdict
```

### 4단계 — Chart 검증 모듈
```
validate_chart(triage, report)
  내부: 1~4단계 rule-based 구조 확인 (WARN/SKIPPED 시 즉시 반환, LLM 미호출)
        5단계 LLM 내용 품질 평가 (triage + ai_draft_json → PASS/WARN + 이유)
  → chart_verdict
```

### 5단계 — 결과 조립
```
_build_result(triage_verdict, schedule_verdict, chart_verdict)
  → overall ("ATTENTION" or "OK")
  → checks  (validation_resultDB.checks JSON 컬럼)
  → completeness_score (1A 점수)
  → consistency_score  (3번 일치율 × 10)
  → summary (수의사용 한 줄 요약)
```

### 6단계 — DB 저장
```
_save_result(scheduleid, emrid, result, db)
  → scheduleid 기준 SELECT
  → 있으면 UPDATE / 없으면 INSERT
  → await db.commit()
```

### 7단계 — 오케스트레이터
```
async def run_validation(scheduleid, db)
  → _load_data 호출
  → validate_triage / validate_schedule / validate_chart 각각 try/except 격리
  → _build_result → _save_result
  → 결과 반환
```

### 8단계 — API 엔드포인트
```
POST /admin/validation/run?schedule_id=xxx
  → admin.py에 추가
  → run_validation(schedule_id, db) 호출
```

---

## 11. checks JSON 구조

`validation_resultDB.checks` 컬럼에 저장되는 JSON 형태. 모듈별 중첩 구조를 사용한다.

```json
{
  "triage": {
    "status": "WARN",
    "checks": [
      {"item": "완전성",        "status": "WARN", "detail": "성별 누락"},
      {"item": "유효성",        "status": "WARN", "detail": "발열은 보호자 발화에 언급되지 않았으나 triage에 포함됨 (hallucination 의심)"},
      {"item": "응급도 정합성", "status": "PASS", "detail": "응급 표현 미감지"},
      {"item": "응급도 판단",   "status": "PASS", "detail": "red_flags와 응급도 일치"}
    ]
  },
  "schedule": {
    "status": "PASS",
    "checks": [
      {"item": "진료 시간",   "status": "PASS",    "detail": "30분 산출"},
      {"item": "예약 타이밍", "status": "PASS",    "detail": "응급도 대비 당일 예약"},
      {"item": "근무시간",    "status": "SKIPPED", "detail": "근무표 미등록"},
      {"item": "빈 슬롯",    "status": "PASS",    "detail": "충돌 없음"}
    ]
  },
  "chart": {
    "status": "WARN",
    "checks": [
      {"item": "정합성", "status": "WARN", "detail": "일치율 30% < 50%"}
    ]
  }
}
```

**규칙**

- 모듈 레벨 `status`: 내부 checks 중 WARN이 하나라도 있으면 WARN, 전부 SKIPPED면 SKIPPED, 나머지 PASS
- ERROR가 발생한 모듈: `status: "ERROR"`, checks 내부에 `{"item": "모듈 오류", "status": "ERROR", "detail": 에러 메시지}`
- 1B (유효성) check의 detail: LLM이 반환한 이유 텍스트를 그대로 저장

---

## 12. LLM 연동 명세

### 모델 선택

| 체크 | 모델 | 이유 |
|---|---|---|
| 1B (triage 유효성) | `claude-haiku-4-5-20251001` | "키워드가 발화에 근거했나" 단순 판단 → Haiku 충분 |
| Check 3 5단계 (chart 품질) | `claude-sonnet-4-6` | 임상 일관성 평가는 복잡 → Sonnet |

---

### 프롬프트 설계 원칙

"잘 됐냐"만 물어보지 않는다. 판단 기준을 명시적으로 나열해야 재현성이 생긴다.

**1B 시스템 프롬프트 구조**
```
당신은 수의 트리아지 품질 검사기입니다.
보호자 채팅 발화와 AI 트리아지가 추출한 증상 키워드를 비교해 품질을 평가합니다.

판단 기준:
- 자연어 해석은 정상입니다. ("밥을 안 먹어요" → "식욕감퇴" 는 PASS)
- 보호자가 언급하지 않은 증상이 키워드에 추가됐으면 → WARN (hallucination 의심)
- 보호자가 명확히 언급한 증상이 키워드에서 누락됐으면 → WARN (추출 실패)
- 모호하거나 판단하기 어려운 경우 → PASS (보수적으로 판단)
```

**Check 3 시스템 프롬프트 구조**
```
당신은 수의 차트 품질 검사기입니다.
AI 트리아지 결과와 AI가 작성한 차트 초안의 임상적 일관성을 평가합니다.

판단 기준:
- 트리아지의 주증상이 차트에서 다뤄지지 않으면 → WARN (누락)
- 트리아지 결과와 차트 내용이 모순되면 → WARN (불일치)
- 트리아지에서 중요한 증상이 차트에서 빠져있으면 → WARN
- 전반적으로 일관성이 있으면 → PASS
```

---

### JSON 출력 강제: tool_use

`json.loads()` 파싱 실패 케이스를 원천 차단하기 위해 Anthropic SDK tool_use로 스키마를 강제한다.

```python
VALIDATION_TOOL = [{
    "name": "validation_result",
    "description": "검증 결과를 반환합니다",
    "input_schema": {
        "type": "object",
        "properties": {
            "result": {"type": "string", "enum": ["PASS", "WARN"]},
            "detail": {"type": "string", "description": "판단 이유 한 줄 (한국어)"}
        },
        "required": ["result", "detail"]
    }
}]
```

응답에서 `tool_use` 블록의 `input`을 그대로 사용한다. 추가 의존성 없이 Anthropic SDK 기본 기능으로 동작한다.

---

### LLM 오류 처리

```
1회 재시도 → 성공하면 정상 처리
           → 그래도 실패하면 status: "ERROR", detail: 오류 메시지
```

- 재시도 대상: 네트워크 타임아웃, 5xx 오류
- 재시도 제외: 4xx (잘못된 요청 → 즉시 ERROR)
- ERROR는 overall(ATTENTION/OK)에 영향 없음

---

## 13. 전체 흐름

```
어드민 패널 → "검증 실행" 버튼 클릭
  ↓
POST /admin/validation/run?schedule_id=123
  ↓
_load_data(scheduleid, db)
  schedule → emrid → pet, triage, chat_history
  scheduleid → report
  ↓
Check 1A: Triage 완전성 (6개 항목, rule-based)
Check 1B: Triage 유효성 (LLM — 보호자 발화 원문 vs triage.symptom_keywords)
Check 1C: Triage 응급도 정합성 — 외부 (보호자 발화 RED_FLAG vs urgency, rule-based)
Check 1D: Triage 응급도 판단 품질 — 내부 (triage.red_flags vs urgency + vtl_basis)
Check 2A: duration_min 합리성
Check 2B: 응급도 vs 예약 시간 적절성 (urgency_level_num vs confirmed_time - created_at)
Check 2C: 근무시간 준수
Check 2D: 빈 슬롯 실제 검증 (has_time_overlap 재사용, 사후 감사)
Check 3:  Chart 정합성
          1~4단계: rule-based 구조 체크 (형식/구조 오류 시 LLM 미호출)
          5단계:   LLM — triage 기준 차트 내용 임상 품질 평가
  ↓
종합 판단 (ATTENTION / OK)
  ↓
validation_resultDB upsert (scheduleid 기준)
  ↓
어드민 패널 Validation 탭에서 결과 확인
```
