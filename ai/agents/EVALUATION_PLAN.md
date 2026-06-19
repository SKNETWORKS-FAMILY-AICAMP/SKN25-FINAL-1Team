# Agent Evaluation 설계 문서 (v2 통합판)

## 개요
v2 아키텍처(오케스트레이터 + 6개 에이전트 + MCP)에서
생성된 결과물과 대화 과정이 의도대로 동작하는지 검증한다. 의료적 판단이 아닌 운영 품질
신호만 감지한다.

이 평가 시스템은 성격이 다른 두 부분으로 나뉜다. 같은 `evaluation.py` 파일 안에 있지만
트리거·데이터 출처·저장 테이블·출력 모양이 달라 별도 함수/테이블로 분리한다.

**Part A — 케이스 평가** (`run_case_evaluation`)
실제 운영 데이터(scheduleid 하나)를 사후 감사. 케이스마다 실행, `validation_resultDB`에
scheduleid 기준 upsert, 어드민 Validation 탭에서 케이스 리스트로 조회.

**Part B — 에이전트 성능 평가** (`run_*_agent_eval`, `run_full_agent_report`)
라벨링된 테스트셋으로 오케스트레이터/응대AI/문진AI/경과필터AI/MCP가 전반적으로 잘
작동하는지 검증. 배포 전/주기적으로 실행, `agent_eval_resultDB`에 기록,
어드민 "에이전트 성능" 탭에서 카드/대시보드로 조회. MCP 구현 + 테스트 자산 준비 후 가동.

---


## 1. Part A — 진입점 설계

### 함수 시그니처

```python
run_case_evaluation(scheduleid: int, db: AsyncSession) -> dict
```

기존 `run_validation(scheduleid, db)`를 대체한다. 1A~1B, 2A~2D, Chart 1~4단계 로직은
동일하고, 1E(대화 품질)가 추가된 것 외엔 데이터 체인도 그대로 재사용한다.

### 데이터 체인

```
scheduleid
  → scheduleDB          (emrid, doctorid, confirmed_time, duration_min)
  → guardianDB          (emrid → petid)
  → petDB               (species, gender, birth_date)
  → triage_resultDB     (emrid 기준 조회, chief_complaint, symptom_onset, symptom_keywords, red_flags, vtl_basis)
  → reportDB            (scheduleid 기준 직접 조회, ai_draft_json)
  → chat_historyDB      (emrid 기준 조회, messages)
```

1E(대화 품질)도 이 체인에서 이미 로딩된 `triage`, `chat_history`만 쓴다 — 추가 조회 없음.

---

## 2. Check 1 — Triage (1A~1E)

| 라벨 | 질문 |
|---|---|
| 1A 응급도 정합성 | 보호자 발화(RED_FLAG_LEXICON)와 urgency_level_num이 맞나 (외부 시선) |
| 1B 응급도 판단 | triage 자신의 red_flags·vtl_basis와 urgency_level_num이 일관되나 (내부) |
| 1C 컨텍스트 연속성 | 세션 분기 후 이미 답한 항목 재질문 안 했나 |
| 1D 완료 신호 | 오케스트레이터로 보낸 핸드오프 신호가 올바른가 |
| 1E 대화 품질 | 문진 완전성·질문 효율성·응답 일관성·구조화 품질 (LLM, 구 judge.py) |

triage 자체가 없으면 1A~1D는 SKIPPED.

### 1A 응급도 정합성 — 외부 시선

**핵심 질문**: "보호자가 응급을 시사하는 말을 했는데 triage 에이전트가 응급도를 낮게 책정하지 않았나?"

보호자 발화(role=user) 전체를 RED_FLAG_LEXICON과 매칭한다.

**RED_FLAG_LEXICON 카테고리**

| 카테고리 | 표현 예시 |
|---|---|
| 호흡 곤란 신호 | 숨을 못, 헐떡, 청색, 혀가 파, 잇몸이 파 |
| 의식 저하 신호 | 의식이 없, 쓰러, 기절, 축 늘어 |
| 경련 지속 신호 | 경련, 발작, 경기, 몸을 떨 |
| 다량 출혈 신호 | 피를 많이, 토혈, 혈변, 코피가 멈 |
| 중독/이물 신호 | 삼켰, 중독, 초콜릿, 양파, 쥐약 |
| 쇼크 의심 신호 | 잇몸이 하얗, 몸이 차갑, 축 처져 |

**WARN 조건**: 응급 표현 감지 + urgency_level_num ≥ 4

**SKIPPED 조건**: chat_history 없음 / role=user 발화 없음

---

### 1B 응급도 판단 — 내부 일관성

**핵심 질문**: "triage 에이전트가 스스로 감지한 위험 신호와 자신이 내린 응급도가 일치하는가?"

**WARN 조건**
- `red_flags` 있는데 urgency_level_num ≥ 4 (자기 모순)
- `vtl_basis`가 null 또는 빈 값 (판단 근거 누락)

**SKIPPED 조건**: triage 없음

---

### 1C 컨텍스트 연속성 (MCP 후)

> ⚠️ messages에 `agent_type` 태그가 있어야 세션 분기 감지 가능.

세션 분기 후 보호자가 이미 답한 슬롯을 재질문했으면 WARN.
user가 실제로 답한 항목만 기준 — 에이전트가 물었지만 보호자가 답하지 않은 항목 재질문은 PASS.

---

### 1D 완료 신호 (MCP 후)

> ⚠️ 핸드오프 신호 로그가 있어야 검증 가능.

신호에 `status=complete`, `next=schedule`, 유효한 `emrid`, `urgency_level_num` 포함 여부 +
신호 수신 후 Schedule 에이전트 실제 실행 여부 확인.

---

### 1E 대화 품질 (구 judge.py 통합)

- **포지셔닝**: 환자 안전 판정 아님. overall(ATTENTION/OK) 집계에서 **제외**하고
  `conversation_status` 필드로 별도 노출.
- **데이터**: chat_history에서 `agent_type == "triage"` 구간만 LLM에 전달.
  MCP 전엔 전체 대화를 문진 대화로 간주(v1 동작과 동일).
- **객관 지표**: turn_count는 코드로 직접 계산(구 `_count_turns` 재사용), LLM 비의존.
- **self-enhancement 편향 회피**: triage 에이전트를 생성한 모델과 **다른** 모델/provider 사용
  (Zheng et al. 2023, MT-Bench 근거). 구 judge.py의 `agent="judge"` 라우팅 방식 재사용.
- **판정**: 4개 지표 모두 7.0 이상 → HEALTHY(PASS), 하나라도 미만 → NEEDS_REVIEW(WARN).
  단, overall에는 반영하지 않는다.

**4개 지표**

| 지표 | 의미 |
|---|---|
| completeness | 문진에서 필요한 정보가 다 수집됐나 |
| question_efficiency | 불필요한 재질문 없이 효율적으로 진행됐나 |
| response_consistency | 같은 주제에 모순된 응답이 없었나 |
| structuring_quality | 대화가 논리적 순서로 구조화됐나 |

---

## 3. Check 2 — Schedule (2A~2E)

| 라벨 | 질문 |
|---|---|
| 2A 예약 타이밍 | 응급도 대비 confirmed_time까지 걸린 일수가 기준 이내인가 (당일 슬롯 가용성 고려) |
| 2B 근무시간 | 의사/병원 근무표 안에 예약됐나 |
| 2C 빈 슬롯 | has_time_overlap 재사용해 실제 충돌 여부 사후 감사 |
| 2D 핸드오프 수신 | 문진 완료 신호를 받아 정상 실행됐나 |

confirmed_time이 없으면 2A/2B/2C는 일괄 SKIPPED. 


### 2A 예약 타이밍

| urgency_level_num | 기준 |
|---|---|
| 1~2 | 당일 (created_at 기준) |
| 3 | 2일 이내 |
| 4~5 | 3일 이내 |

기준 초과 시 `_has_same_day_slots` 확인:
- 당일 슬롯 없었음(`False`) → PASS "당일 슬롯 없어 최선 배정"
- 당일 슬롯 있었음(`True`) → WARN "기준 초과 (사용자 선택)"
- 판단 불가(`None`) → WARN (보수적 플래그)

`_has_same_day_slots` 로직: `VetWeeklySchedule → HospitalWeeklySchedule` fallback →
총 근무 분 계산 → 당일 확정 예약 합산(현 schedule 제외) → 여유 분 ≥ duration_min이면 True.

### 2B 근무시간

`VetWeeklySchedule → HospitalWeeklySchedule` fallback. 근무표 없음 → SKIPPED.
휴무일 / 근무 시작 전 / 종료 후 넘어감 / 점심 겹침 → WARN.

### 2C 빈 슬롯

`has_time_overlap(db, doctorid, confirmed_time, end, exclude_schedule_id=scheduleid)` 재사용.
겹치면 WARN.

### 2D 핸드오프 수신 (MCP 후)

신호 수신 기록 / emrid 일치 / 에이전트 실행 기록 확인. MCP 미구현이면 SKIPPED.

---

## 4. Check 3 — Chart (1~5단계)

차트 AI가 `reportDB.ai_draft_json`에 저장하는 실제 구조:

```json
{
  "thinking": "...",
  "intake_summary": {
    "guardian_report": "보호자 호소 요약",
    "key_symptoms": ["가려움", "피부 이상"],
    "suspected_diseases": ["알레르기성 피부염", "외부기생충 감염"]
  },
  "soap": {
    "S": "보호자 호소 정리",
    "O": "내원 시 확인할 객관적 소견",
    "A": "감별진단 및 임상 판단",
    "P": "진료 계획"
  },
  "differential_diagnosis": [
    {
      "disease": "알레르기성 피부염",
      "probability": "높음",
      "reasoning": "근거",
      "against": "반증"
    }
  ],
  "recommended_tests": [...],
  "red_flags_confirmed": [],
  "missing_info": [...],
  "vet_questions": [...],
  "cautions": [...]
}
```

**1~4단계: Rule-based 구조 체크 (앞 단계 실패 시 즉시 반환)**

```
1단계: report 자체가 없는가?                       → SKIPPED (차트 미생성)
2단계: ai_draft_json이 dict가 아닌가?              → WARN (차트 형식 오류)
3단계: intake_summary가 없거나 dict가 아닌가?       → WARN (차트 구조 이상)
4단계: intake_summary.key_symptoms가 비어있는가?   → WARN (증상 미기록)
```

**3단계: LLM — 임상 품질 평가 (추후)**

triage 결과 기준으로 AI 차트가 임상적으로 일관되는지 Sonnet으로 평가.
tool_use로 JSON 강제, 결과는 `{"result": "PASS"|"WARN", "detail": "..."}`.

LLM에 전달하는 필드 (필요한 것만):
- `intake_summary` (guardian_report, key_symptoms, suspected_diseases)
- `soap.S`, `soap.A`
- `differential_diagnosis` (disease, reasoning, against)

제외 필드 (평가 불필요): `thinking`, `soap.O`, `soap.P`, `recommended_tests`, `missing_info`, `vet_questions`, `cautions`

---

## 5. 에러 격리

Check 1 / 2 / 3 / 1E 각각 독립 try/except. 하나가 실패해도 나머지 계속 실행.
실패한 모듈은 `status: "ERROR"`로 저장.

---

## 6. 종합 판단

| 상태 | 의미 | overall 영향 |
|---|---|---|
| PASS | 정상 | 없음 |
| WARN | 수의사 확인 권고 | ATTENTION |
| SKIPPED | 조건 미충족 (정상) | 없음 |
| ERROR | 시스템 오류 | 없음 |

- **overall(ATTENTION/OK)**: triage(1A~1D)·schedule(2A~2E)·chart 모듈만 집계
- **1E(대화 품질)**: overall 집계 제외 — 별도 `conversation_status` 필드로만 노출

summary 예시:
```
"수의사 검토 권고: 응급도 판단, 근무시간"
"특이 검증 이슈 없음"
```

---

## 7. checks JSON 구조

`validation_resultDB.checks` 컬럼에 저장되는 JSON. 모듈별 중첩 구조.

```json
{
  "triage": {
    "status": "WARN",
    "checks": [
      {"item": "응급도 정합성",  "status": "PASS",    "detail": "응급 표현 미감지"},
      {"item": "응급도 판단",    "status": "WARN",    "detail": "vtl_basis 누락"},
      {"item": "컨텍스트 연속성","status": "SKIPPED", "detail": "agent_type 태그 없음 (MCP 미구현)"},
      {"item": "완료 신호",      "status": "SKIPPED", "detail": "핸드오프 신호 로그 없음 (MCP 미구현)"}
    ]
  },
  "schedule": {
    "status": "PASS",
    "checks": [
      {"item": "진료 시간",    "status": "PASS",    "detail": "30분 산출"},
      {"item": "예약 타이밍",  "status": "PASS",    "detail": "응급도 4 기준 1일 후 예약"},
      {"item": "근무시간",     "status": "PASS",    "detail": "근무시간 내 예약"},
      {"item": "빈 슬롯",     "status": "PASS",    "detail": "충돌 없음"},
      {"item": "핸드오프 수신","status": "SKIPPED", "detail": "MCP 미구현"}
    ]
  },
  "chart": {
    "status": "SKIPPED",
    "checks": [{"item": "정합성", "status": "SKIPPED", "detail": "차트 미생성"}]
  },
  "conversation": {
    "status": "WARN",
    "checks": [
      {
        "item": "대화 품질",
        "status": "WARN",
        "detail": "질문 효율성 낮음 — 재질문 의심",
        "scores": {
          "completeness": 8.5,
          "question_efficiency": 6.0,
          "response_consistency": 8.8,
          "structuring_quality": 8.0
        },
        "turn_count": 7
      }
    ]
  }
}
```

`overall` 계산 시 `conversation` 모듈은 제외. 모듈 레벨 status 규칙: WARN 있으면 WARN,
전부 SKIPPED면 SKIPPED, 그 외 PASS.

---

## 8. Part B — 에이전트 성능 평가

> Part A와 완전히 다른 트리거/데이터/저장 체계. scheduleid에 묶이지 않는다.

| 함수 | 평가 내용 | 합격 기준 |
|---|---|---|
| `run_orchestrator_eval` | 라우팅 정확도 / 문진 중 유출 / sticky 규칙 | 정확도 90%+, 유출 0건, sticky 100% |
| `run_reception_eval` | MCP 도구선택 / 가드레일 3요소 / 무관발화 차단 | 각 100% |
| `run_triage_agent_eval` | 슬롯추출 F1 / hallucination / 점수표 정확도 / RED flag | F1 90%+, halluc 0건, 점수표 95%+, RED flag 100% |
| `run_followup_filter_eval` | 분류 recall/precision / 누적갱신 / 악화신호 내원권유 | recall 90%+, precision 80%+ |
| `run_mcp_health_check` | 연결+list_tools+call_tool / 도구별 성공률 / 응답시간 | 100% / 99%+ / p95 2000ms 이내 |
| `run_e2e_scenarios` | S1(정상흐름) / S2(끼어들기복귀) / S6(경과vs잡담) | 단계별 결과물 생성 확인 |

테스트 자산: `tests/router_eval.jsonl`, 슬롯 추출/경과 분류 테스트셋, MCP fixture, 시나리오 스크립트
— 전부 MCP 구현과 함께 준비.

### 8.1 통합 리포트

```python
run_full_agent_report(db) -> dict
```

```json
{
  "overall_verdict": "PARTIAL_FAIL",
  "agents": {
    "orchestrator":  {"routing_accuracy": "94%", "triage_leak": 0,    "pass": true},
    "reception_ai":  {"tool_accuracy": "100%",   "guardrail": "100%", "pass": true},
    "triage_ai_v2":  {"slot_f1": "88%", "red_flag_recall": "100%",   "pass": false},
    "filter_ai":     {"recall": "92%",  "precision": "85%",           "pass": true},
    "mcp":           {"availability": "99.9%", "p95_ms": 1200,        "pass": true}
  },
  "blockers": ["triage_ai_v2.slot_f1: 88% < 90% 기준"],
  "verdict_reason": "문진 AI 슬롯 추출 F1 기준치 미달 → 배포 보류"
}
```

| overall_verdict | 조건 |
|---|---|
| PASS | 모든 에이전트 pass + blockers 없음 |
| PARTIAL_FAIL | blocker 있음 (배포 보류) |
| CRITICAL_FAIL | RED flag recall < 100% 또는 triage_leak > 0 |

저장: `agent_eval_resultDB`(run_id, run_at, results_json, overall_verdict, blockers) —
`validation_resultDB`와 다른 테이블. 한 row = "한 번 실행한 전체 테스트셋 결과".

---

## 9. 어드민 화면

| 탭 | 내용 | 데이터 소스 |
|---|---|---|
| Validation | scheduleid별 PASS/WARN/SKIPPED 리스트, 클릭 시 checks 펼치기 | `validation_resultDB` |
| 에이전트 성능 | 에이전트별 카드 + overall_verdict + blockers, "평가 실행" 버튼 | `agent_eval_resultDB` |

Part B 탭은 MCP·테스트 자산 준비 전엔 빈 상태로 둬도 된다.

---

## 10. 구현 순서

**완료 (Part A)**
```
1A 응급도 정합성, 1B 응급도 판단
2A 예약타이밍, 2B 근무시간, 2C 빈슬롯
Chart 1~4단계
POST /admin/validation/run 엔드포인트
```

**다음 (MCP 전)**
```
1E 대화 품질 — LLM 어댑터 연결 (triage와 다른 모델 사용)
Chart 5단계 — 임상 품질 LLM (Sonnet)
```

**MCP 구현 후**
```
1C 컨텍스트연속성, 1D 완료신호, 2E 핸드오프수신 (agent_type 태깅 전제)
Part B 전체:
  테스트 자산 준비 (router_eval.jsonl, 슬롯/경과 분류 테스트셋, MCP fixture, 시나리오)
  → run_orchestrator_eval ~ run_e2e_scenarios 구현
  → run_full_agent_report 조립
  → 어드민 "에이전트 성능" 탭 연결
```

---

## 11. LLM 연동 명세

| 체크 | 모델 | 비고 |
|---|---|---|
| Chart 5단계 | claude-sonnet-4-6 | 임상 일관성 평가 |
| 1E 대화 품질 | triage 에이전트와 **다른** 모델/provider | self-enhancement 편향 회피 (Zheng et al. 2023) |

JSON 출력 강제(tool_use), 1회 재시도 정책(4xx 제외, 5xx/타임아웃만 재시도).

---

## 12. 코드 검토 확인 사항

| 항목 | 내용 |
|---|---|
| chat_historyDB 키워드 컬럼 | `keywords` (symptom_keywords 아님) |
| triage 조회 경로 | `scheduleid → emrid → triage_resultDB` (petid 경유 아님) |
| `has_time_overlap` 재사용 | Check 2D에서 기존 함수 그대로 사용 |
| report 조회 | `scheduleid` 컬럼 있어서 직접 조회 가능 |
| 차트 에이전트 실행 조건 | 예약 확정 후 post_booking_graph에서만 실행 → chart 없으면 Check 3 전체 SKIPPED |
| messages agent_type 태그 | 1C, 1D, 2E, 1E(구간 필터링) 전제 조건 — MCP 구현 시 추가 |
| ValidationResult 모델 | `conversation_status` 컬럼 추가 마이그레이션 필요 |
| router_eval.jsonl | `tests/` 디렉토리, 에이전트 유형별 발화 20~30개씩 (Part B 전제) |
| RED flag 테스트 | 목록 전부 통과 필수 (샘플링 아님, Part B `run_triage_agent_eval` 소속) |
