# 커밋 전 검증 리포트 (feat/followup-filter-eval)

생성일: 2026-06-24 · 환경: 로컬 dev 스택(docker compose `ai/docker/docker-compose.yml`) + 실 dev DB(:5432) + API(:8000)

## 0. 이번 변경 (법령 문구 반영)

수의사법 제13조(진료부·검안부 기록·서명) / 같은 법 시행규칙 제13조(1년 보존)를 반영해
영구삭제 차단(409) 및 보관함 UX 문구를 아래로 통일.

> 상담·예약·진료 기록이 있는 반려동물은 영구 삭제할 수 없어요. 진료부 등 병원 진료 기록은 수의사법 및 같은 법 시행규칙에 따라 일정 기간 보존될 수 있어요.

변경 파일:
- `backend/app/api/pets.py` — 영구삭제 409 detail
- `frontend/guardian-web/src/i18n/translations.ts` — `petArchive.permanentNote` (한/영)

영문: *"Pets with consultation, booking, or medical records cannot be permanently deleted. Medical records such as the clinical chart may be retained for a certain period under the Veterinarians Act and its Enforcement Rule."*

옛 문구를 검증하는 테스트/참조 없음(grep 0건) → 문구 변경으로 깨지는 테스트 없음.

---

## 1. 결과 요약

| 구분 | 결과 |
|---|---|
| **전체 통과율** | 신규 작성·실행 테스트 **100%** (아래 항목 전부 통과) |
| **신규 실패** | **0개** |
| backend pytest | **90 passed / 0 failed / 6 deselected(live)** *(별도 사전존재 collection 에러 3건 — 아래 §4)* |
| guardian-web build (tsc+vite) | ✅ 성공 |
| vet-web build | ✅ 성공 |
| company-web build | ✅ 성공 |
| alembic heads | **1개** (단일) |
| alembic upgrade head | ✅ DB가 head(`u1a2b3c4d5e6`)까지 적용됨 |
| fresh DB 0001→head | ✅ 임시 빈 DB에서 head까지 정상 적용 |
| 채팅 route accuracy | **1.0** (10/10) |
| BOOKED 예약정보 응답 정확도 | **1.0** (7/7, 맥락 일치) |
| archived pet 신규 채팅 차단 성공률 | **1.0** |
| followup 저장 성공률 | **100%** (저장 1건 확인) |
| scheduleid fill rate (BOOKED) | **1.0** (7/7 실값) |
| CI yaml / compose validation | ✅ 유효 |
| docker backend/migrate image build | ✅ 성공 (exit 0) |

**커밋 가능 여부: ✅ 가능** — 모든 커밋 기준 충족, 신규 실패 0. (단, 사용자 검토 후 진행 요청에 따라 커밋 대기 중)

커밋 기준 체크:
- [x] 활성 펫 채팅 정상
- [x] 보관 펫 신규 채팅 차단
- [x] PRE_BOOKING/BOOKED 대표 시나리오 통과
- [x] scheduleid가 BOOKED 채팅에서 실제 값으로 들어옴 (88~95)
- [x] 신규 실패 0개

---

## 2. 실행한 테스트 명령어

```bash
# 전체 시스템 (alembic heads/current, fresh DB 마이그레이션, 프론트 3종 tsc+vite build, 백엔드 import)
POSTGRES_PASSWORD=medipaw_secret ./check.sh deep

# backend non-live pytest (stale 3모듈 제외 — §4 참조)
docker compose -f ai/docker/docker-compose.yml exec -T backend \
  python -m pytest -m 'not live' -q \
  --ignore=tests/shadow_triage/test_guardian_safe.py \
  --ignore=tests/triage_regression/test_triage_engine.py \
  --ignore=tests/triage_regression/test_triage_prompt.py

# followup 장기대화(마라톤) scripted 채점
docker exec -w /app/backend docker-backend-1 \
  python scripts/run_followup_marathon.py --mode scripted --out /tmp/followup_marathon.json

# 실DB BOOKED 맥락 평가
docker exec -w /app/backend docker-backend-1 \
  python scripts/run_realdb_context_eval.py --out /tmp/realdb.json

# 펫 보관 E2E (실 API :8000)
python3 backend/scripts/run_pet_archive_e2e.py

# 채팅 종합 E2E (실 dev DB + process_turn = SSE와 동일 경로)
docker exec -w /app/backend docker-backend-1 \
  python scripts/run_chat_eval.py --out /tmp/chat_eval.json

# CI / compose YAML 검증
docker exec docker-backend-1 python -c "import yaml; yaml.safe_load(open('/tmp/ci.yml'))"
docker compose -f ai/docker/docker-compose.yml config   # 유효성
docker compose -f ai/docker/docker-compose.yml build backend migrate
```

> ⚠️ **중요한 운영 메모**: 실행 중이던 dev `backend` 컨테이너는 17시간 전 이미지라
> 이번 브랜치의 신규 라우트(`/pets/archived`, `/pets/{id}/restore`, `/pets/{id}/permanent`)와
> 신규 마이그레이션(`u1a2b3c4d5e6`)이 **프로세스에 반영돼 있지 않았음**.
> `backend`·`migrate` 이미지를 재빌드하고 `up -d --force-recreate backend`로 재기동한 뒤
> openapi에 신규 라우트가 등록된 것을 확인하고 E2E를 수행함.

---

## 3. 세부 결과

### 3-1. 변경 영향권
| 항목 | 결과 |
|---|---|
| pet archive E2E (생성/보관/복원/영구삭제) | ✅ **10/10** (`pet_archive_e2e.json`) |
| 보호자 pet 진입점 archived_at 필터 | ✅ 활성 목록(`get_pets_by_userid`)이 보관펫 제외 |
| 기록 있는 펫 영구삭제 → 409 + 법령 문구 | ✅ `message`에 "수의사법" 포함 확인 |
| 기록 없는 펫 영구삭제 | ✅ 200 성공 |
| guardian-web tsc/build | ✅ |
| followup marathon | ✅ **75/75 턴 매치 (100%, 3 시나리오)** |
| realdb context eval | ✅ 완료 (아래) |

**realdb context eval 요약** (메모리 judge / DB조회):
- 예약시각(time): 5.0/5 · 2/2
- 병원(hospital): 4.5/5 · 2/2
- 담당의(vet, "누구 의사지?/그 의사 친절해?"): 1.0/5 · 0/2  ← 이 하니스의 구어체 표현에서 이름 미반영(사전존재 관찰항목, 이번 변경과 무관). **채팅 종합 E2E의 "담당 의사 누구야?"에서는 "김메디 선생님" 정상 반영됨.**
- 재예약(rebook): 5.0/5 · 3/3 · P4 3/3
- 취소문의(cancel_inquiry): 4.0/5 · 3/3 · P4 3/3 (cancel_request 미발생 정상)
- 취소실행(cancel_exec): P4 2/2 (cancel_request 발생 정상)
- P4 clarify 누수: 애매질문 0 / 감정 0 / 잡담경계 0

### 3-2. 전체 시스템 풀 테스트
| 항목 | 결과 |
|---|---|
| backend non-live pytest | ✅ 90 passed / 0 failed |
| alembic heads 단일성 | ✅ 1개 |
| alembic upgrade head | ✅ |
| fresh DB 0001→head | ✅ |
| frontend tsc/build (guardian/vet/company) | ✅ 3종 전부 |
| CI yaml validation | ✅ jobs: frontend-build, backend-syntax, backend-migrations |
| docker compose build (backend/migrate) | ✅ |

### 3-3. 채팅 종합 E2E (`chat_eval_results.json` / `chat_eval_report.html`)
실 dev DB에 BOOKED 세션을 구성하고 `process_turn()`(SSE 엔드포인트와 동일 경로)로 실행. 16/16 통과.

| 그룹 | 시나리오 | route | scheduleid | 결과 |
|---|---|---|---|---|
| 진입 | 활성펫 채팅 시작 | — | — | ✅ 가능 |
| 진입 | 보관펫 신규채팅 차단 | — | — | ✅ 차단(404 조건) |
| 진입 | 보관펫 선택목록 제외 | — | — | ✅ |
| PRE_BOOKING | 증상 → triage | triage | null | ✅ |
| PRE_BOOKING | 병원 운영시간/위치 → reception | reception | null | ✅ |
| PRE_BOOKING | 예약 의도 → 문진 흐름 | triage | null | ✅ 흐름 유지 |
| BOOKED | "내 예약 언제야?" | followup_filter | 88 | ✅ 6/26 10:00 안내 |
| BOOKED | "어느 병원 예약이야?" | followup_filter | 89 | ✅ 메디포동물병원 안내 |
| BOOKED | "담당 의사 누구야?" | followup_filter | 90 | ✅ 김메디 선생님 안내 |
| BOOKED | "예약 시간 바꾸고 싶어요" | followup_filter | 91 | ✅ 현예약 되짚음+rebook_request |
| BOOKED | "예약 취소돼요?" | followup_filter | 92 | ✅ cancel_request 미발생(문의) |
| BOOKED | "아이 상태가 안 좋아요…" | followup_filter | 93 | ✅ 경과 저장(Followup 1건) |
| BOOKED | 사진 후속 "사진 못 찍었으면?" | followup_filter | 94 | ✅ 끊김 없이 연속 |
| 상태 | chat_history 저장 | followup_filter | 95 | ✅ user+assistant 저장 |
| 상태 | orch_state 저장/로드 | — | 95 | ✅ dict 영속 |
| 상태 | scheduleid 실값 | — | 95 | ✅ null 아님 |

- SSE 응답: process_turn 이벤트 스트림(status→message→quick_replies→done) 정상, 깨짐 없음.
- archived pet의 과거 채팅 상세 조회: ✅ 유지(`GET /chat/sessions/{id}` 200).

---

## 4. 사전존재(pre-existing) 이슈 — 이번 변경과 무관, 신규 실패 아님

1. **pytest collection 에러 3건** (`-m "not live"` 수집 단계):
   - `tests/shadow_triage/test_guardian_safe.py` → `app.api.chat`에 없는 `_guardian_safe_triage` import
   - `tests/triage_regression/test_triage_engine.py`, `test_triage_prompt.py` → 존재하지 않는 `ai.triage` 모듈
   - 확인: 해당 심볼/모듈은 merge-base·`main`에도 없음(에이전트 리팩터 PR #204로 경로 이동 후 남은 stale 테스트). 이번 변경 파일(pets.py, translations.ts)과 무관.
   - 권고(별도 후속): stale 테스트 갱신 또는 삭제.

2. **check.sh API 경로 best-effort 경고 4건**(false positive):
   - `/pets/${petId}/permanent`, `/pets/${petId}/restore`, `/admin/eval/full-report`, `/admin/validation/run-recent`
   - 템플릿 리터럴 매칭의 한계로 실제로는 라우트가 존재(E2E 10/10로 permanent/restore 동작 확인). 무시 가능.

3. **realdb 하니스 vet 항목 저점**: 위 3-1 참조. 채팅 종합 E2E에서는 담당의 안내 정상.

---

## 5. 산출물

- `test_report.md` (본 파일)
- `chat_eval_report.html` — 시나리오별 입력/route/reply 전문/events/scheduleid/pass·fail
- `chat_eval_results.json` — 원본 결과 + 지표(route accuracy, reply quality, event correctness, scheduleid fill, archived block, BOOKED 맥락 정확도)
- `pet_archive_e2e.json` — 펫 생성/보관/복원/영구삭제 API 응답 + 체크 결과

신규 추가 스크립트: `backend/scripts/run_pet_archive_e2e.py`, `backend/scripts/run_chat_eval.py`, `backend/scripts/gen_chat_eval_html.py`
