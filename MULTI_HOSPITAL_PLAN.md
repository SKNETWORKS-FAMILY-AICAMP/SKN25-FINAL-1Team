# MediPaw 다중 병원 · 다중 원장 + 운영자 백오피스 전체 계획

> 작성: 2026-06-14
> 목적: "1인 동물병원" 가정으로 만든 시스템을 **다중 병원 · 다중 원장**으로 확장하고,
> 신규 병원 온보딩(신원 검증 후 계정 자동 발급)과 운영자 백오피스(승인 + validation + judge)를 추가한다.

---

## 0. 확정된 방향 (요약)

- **병원(Hospital)을 1급 엔티티로 독립.** 지금은 병원 정보가 원장(`doctorDB`) 레코드에 박혀 있음 → 분리.
- **원장 N : 1 병원** (한 병원에 여러 원장, 대표원장 + 일반수의사).
- **보호자 M : N 병원** (보호자가 여러 병원 등록 후 전환).
- **원장은 소속 병원 환자 전체 열람** 가능 (담당 원장 표기는 유지).
- **보호자 화면에 "원장 소개 탭"** 추가 → 병원 안에서 원장 골라 예약.
- **신규 병원 = 문의 폼 + 서류 업로드(사업자등록증·수의사 면허증) → 운영자 백오피스에서 신원 확인 → "승인" 클릭 시 병원 + 원장 계정 자동 생성** (임시 비번, 첫 로그인 시 변경 강제).
- **운영자 백오피스 한 곳에** = ① 병원 가입 승인/자동생성 ② Validation 모니터링·벤치마크 ③ Judge 모니터링·벤치마크.

---

## 1. 데이터 모델

### 1-1. 신규 / 변경 테이블

#### `hospitalDB` (재정의 — 진짜 병원 엔티티)
현재: `doctorid`/`scheduleid` 역방향 FK (방향이 거꾸로, 사실상 미사용) → **전면 교체**

| 컬럼 | 타입 | 비고 |
|---|---|---|
| hospitalid | PK | |
| hospital_name | str | |
| address | str | |
| phone | str | |
| **business_number** | str, unique | **원장에서 이동** (병원당 1개) |
| intro | text | 병원 소개 (보호자 화면 노출) |
| logo_image | str | 병원 로고/대표 이미지 URL |
| status | str | `active` / `suspended` |
| created_at / updated_at | datetime | |

#### `doctorDB` (변경)
| 변경 | 내용 |
|---|---|
| **추가** `hospitalid` | FK → hospitalDB (N:1) |
| **추가** `role` | `owner`(대표원장) / `member`(일반수의사) |
| **추가** `specialty` | 진료분야 (예: 내과/외과/피부) — 소개 탭 노출 |
| **추가** `bio` (text) | 한줄~상세 소개 — 소개 탭 노출 |
| **추가** `profile_image` | 원장 사진 — 소개 탭 노출 |
| **추가** `career` (text/JSON) | 경력·학력 — 소개 탭 노출 |
| **추가** `is_active` | 퇴사/비활성 처리 |
| **이동** `business_number` | → hospitalDB (제거). ⚠️ 현재 doctor에 unique라 같은 병원 2번째 원장 계정 생성이 막힘 — **반드시 이동** |
| 기존 `hospital_name/address/number` | 마이그레이션 후 hospital에서 파생 (당분간 유지 가능) |

#### `guardian_hospitalDB` (신규 — 보호자 M:N 병원)
| 컬럼 | 비고 |
|---|---|
| id PK | |
| userid | FK → userDB (보호자) |
| hospitalid | FK → hospitalDB |
| is_primary | bool — 기본 선택 병원 |
| created_at | |
| (uq: userid+hospitalid) | 중복 등록 방지 |

> 보호자는 여러 병원 등록, 앱에서 "현재 병원" 전환. 예약·EMR·기록은 현재 선택된 병원 기준.

#### `clinic_signup_requestDB` (신규 — 가입 문의/승인 워크플로우)
| 컬럼 | 비고 |
|---|---|
| id PK | |
| hospital_name | |
| address / phone | |
| business_number | |
| business_license_image | **사업자등록증 이미지** URL |
| owner_name / owner_email / owner_license_no | 대표원장 |
| owner_license_image | **대표원장 면허증 이미지** URL |
| owner_desired_loginid | 희망 아이디 |
| additional_doctors | JSON 배열: `[{name, email, license_no, license_image, desired_loginid}]` |
| hospital_intro | 병원 소개 |
| status | `접수` / `검토중` / `승인` / `반려` |
| reject_reason | 반려 사유 |
| created_hospitalid | 승인 시 생성된 병원 FK (역추적) |
| created_at / reviewed_at | |

#### `admin_userDB` (신규 — 운영자 계정)
| 컬럼 | 비고 |
|---|---|
| adminid PK | |
| loginid / password | |
| name | |
| role | 초기엔 단일 `superadmin`이면 충분 |
| created_at | |

### 1-2. 기존 테이블 영향 (열람 범위 변경)

- **EMR / 환자 조회**(`doctorEMRDB`, 환자 목록): 현재 `doctorid` 기준 → **`hospitalid` 기준**으로 변경.
  같은 병원 원장이면 누가 진료했든 병원 환자 전체 열람. 기록에 "담당 원장" 표기 유지.
- **예약**(`scheduleDB`): `doctorid` FK 유지(예약은 원장 단위). 충돌 제약 `uq_schedule_doctor_time`은 **이미 원장 단위라 다중 원장 동시예약 그대로 동작 — 변경 불필요** ✅. 단, 예약 생성 시 "병원 → 원장" 선택 흐름 추가.
- **원장 진료시간**(`vet_scheduleDB`): 이미 `doctorid` 단위 — 변경 불필요.
- `validation_resultDB`, `agent_pipeline_resultDB`: 모델 변경 없음. 백오피스 조회용으로 재활용.

---

## 2. 권한 / 역할 모델

| 역할 | 권한 |
|---|---|
| **보호자(user)** | 병원 검색·등록·전환, 원장 소개 열람, 예약, 본인 펫 기록 |
| **대표원장(doctor.owner)** | 병원 정보 수정, 소속 원장 초대/비활성, 병원 전체 예약·환자 뷰, 본인 진료 |
| **일반수의사(doctor.member)** | 본인 스케줄, **병원 전체 환자 열람**, 본인 프로필 관리 |
| **운영자(admin)** | 가입 신청 검토/승인/반려, 계정 자동 생성, validation·judge 모니터링·벤치마크 |

---

## 3. 보호자 화면 (guardian-web)

### 3-1. 병원 찾기 / 등록 (신규)
- **진입**: 최초 로그인 시 온보딩 강제(기존 보호자는 등록 병원 0개 → 유도). 이후 설정에서 추가.
- **받는 정보 / 동작**: 병원명·지역 검색 → 결과 카드(병원명·주소·대표원장·로고) → "내 병원으로 등록".
- **표시**: 등록한 병원 리스트, 기본 병원(is_primary) 설정, 현재 병원 전환 토글.

### 3-2. 원장(수의사) 소개 탭 (신규 — 핵심)
- **진입**: 선택한 병원 상세 안의 탭.
- **표시**: 소속 원장 카드 리스트 — **사진 / 이름 / 진료분야(specialty) / 경력(career) / 한줄소개(bio)**.
- **동작**: 카드에서 바로 "이 원장에게 예약" 연결.
- **데이터 출처**: §4-2 수의사 본인 프로필 관리 화면.

### 3-3. 예약 플로우 (변경)
- 기존: (단일 원장) 시간만 선택.
- 변경: **① 병원 선택(등록된 것 중) → ② 원장 선택 → ③ 진료시간 슬롯 선택 → ④ 예약 확정.**
- 원장별 진료시간(`vet_scheduleDB`) + 충돌제약 그대로 활용.

### 3-4. 진료기록 / 내 펫 (변경)
- 기록에 **병원명 + 담당 원장** 표기 추가.
- 병원 전환 시 해당 병원 기록만 필터(또는 전체 + 병원 뱃지).

### 3-5. 설정 (변경)
- 등록 병원 관리(추가/삭제/기본 설정).

---

## 4. 수의사 화면 (vet-web)

### 4-1. 첫 로그인 (기존 + 강화)
- `is_initial_password=True`면 비밀번호 변경 강제(이미 존재).

### 4-2. 내 프로필 관리 (신규)
- **받는 정보**: 사진(profile_image), 진료분야(specialty), 경력·학력(career), 소개(bio).
- → 보호자 소개 탭(§3-2)으로 그대로 노출. (양쪽이 한 쌍)

### 4-3. 병원 정보 관리 (신규, 대표원장 전용)
- **받는 정보**: 병원 소개(intro), 주소·전화, 로고(logo_image), 진료시간.

### 4-4. 소속 원장 관리 (신규, 대표원장 전용)
- 소속 원장 목록, **원장 추가 신청/초대**(또는 운영자에게 추가 요청), 비활성(is_active=false), 역할 표시.
- (단순화) 초기엔 "추가 원장은 운영자에게 요청" → 백오피스에서 계정 생성하는 방식도 가능.

### 4-5. 예약 / 스케줄 (변경)
- **개인 뷰**: 본인 예약/진료시간.
- **병원 전체 뷰**(대표원장): 병원 내 전 원장 예약 캘린더.

### 4-6. 환자 / EMR (변경)
- 조회 범위 `doctorid` → **`hospitalid`**. 병원 환자 전체 열람, "담당 원장" 표기.
- EMR 작성 시 작성 원장(doctorid) 기록 유지.

---

## 5. 문의 사이트 (company-web)

### 5-1. 병원 가입 신청 폼 (신규)
**받아야 할 정보 (= `clinic_signup_requestDB` 입력):**
- 병원: 병원명 / 주소 / 대표 전화 / **사업자등록번호 + 사업자등록증 이미지 업로드**
- 병원 소개(intro)
- 대표원장: 이름 / 이메일 / **수의사 면허번호 + 면허증 이미지 업로드** / 희망 로그인 아이디
- 추가 원장(반복 입력 N명): 이름 / 이메일 / 면허번호 / **면허증 이미지** / 희망 아이디
- 개인정보·이용 동의 체크
- (제출 후) 접수 확인 화면 + 안내("운영자 신원 확인 후 계정 발급 연락").

### 5-2. 신청 상태 안내 (선택)
- 신청 번호로 상태 조회(접수/검토중/승인/반려) — 초기엔 생략 가능.

---

## 6. 운영자 백오피스 (신규) — company-web `/admin` 보호 경로

> 별도 앱 신설보다 company-web 안의 인증된 `/admin` 경로로 붙이는 게 가장 빠름.
> 운영자 로그인(`admin_userDB`)으로 보호.

### 6-A. 병원 가입 승인 / 자동 생성
- **신청 목록**: status별 필터(접수/검토중/승인/반려), 신청일 정렬.
- **신청 상세**: 병원 정보 + **첨부 서류(사업자등록증·면허증) 뷰어** + 원장 목록.
- **"승인" 버튼 → 자동 처리**:
  1. `hospitalDB` 생성 (병원 정보·business_number·intro·logo)
  2. 소속 원장 계정 일괄 생성 (대표원장 owner + 추가 원장 member),
     각자 **희망 아이디 + 임시 비밀번호** 발급, `is_initial_password=True`
  3. 신청 status=`승인`, `created_hospitalid` 기록
  4. 임시 비번 전달: **초기엔 화면에 표시 → 운영자 수동 전달**, (추후) 원장 이메일 자동 발송
- **"반려" 버튼**: 반려 사유 입력 → status=`반려` (회신은 초기 수동).

### 6-B. Validation 모니터링 + 벤치마크
> Validation = 결정론적 4종 점검(LLM 미사용). 결과는 `validation_resultDB`에 저장됨.

**(1) 운영 모니터링 (실데이터)**
- 최근 validation 결과 목록: emrid·일시·`overall`(OK/ATTENTION)·요약.
- 필터: ATTENTION만 보기, 항목별(완전성/문진-차트/예약안전/응급정합성) WARN 필터.
- 상세: 4종 체크 status + detail(계산 근거 노출: "일치율 X% < 50%" 등), 누락 필드.
- 추세: 기간별 ATTENTION 비율, 항목별 WARN 추이(Langfuse 점수 연동 가능).

**(2) 벤치마크 / 회귀 비교 (eval dataset)**
- 데이터셋: `backend/data/validation/vet_eval_dataset(.sample).json` (clean/flawed × 종 × 질환군).
- "벤치마크 실행" → `backend/scripts/verify_validation_judge.py` 류 로직 호출.
- **결과 표시**:
  - clean: validation=OK / judge=HEALTHY 정답 일치율(정확도).
  - flawed: 주입 결함(redflag_mismatch / missing_field / chart_drift / rx_safety)을 `expected_verdict`대로 잡아낸 **recall/precision**.
  - 축별 스코어: redflag_recall / urgency_accuracy / schedule_floor / completeness / chart_consistency / diagnosis_recall / **rx_safety**(현재 미구현 → 리펙토링 타깃, before/after 차이 부각).
  - 종별 갭(dog/cat/rabbit/exotic) — 토끼·이그조틱 과소트리아지 측정.
- **리펙토링 전/후 비교 뷰**: 동일 데이터셋 두 실행 결과를 나란히(축별 ▲▼).

### 6-C. Judge 모니터링 + 벤치마크
> Judge = LLM 운영품질 모니터링(환자 안전 아님). audit log 위주 + Langfuse 점수.

**(1) 운영 모니터링**
- 최근 judge 결과: emrid·`monitoring_verdict`(HEALTHY/NEEDS_REVIEW)·`quality_scores`(완전성/질문효율/일관성/구조화) + `turn_count`.
- 필터: NEEDS_REVIEW만, 약점 축(weak_axis)별.
- 상세: 4개 품질점수(0~10) + notes + improvement_points + 대화 턴수.
- 추세: 기간별 평균 품질점수, NEEDS_REVIEW 비율.

**(2) 벤치마크**
- flawed 케이스에서 judge가 `monitoring_verdict=NEEDS_REVIEW` 잡는지(데이터셋 expected_verdict.judge 기준).
- 전/후 비교 동일.

> ※ Judge는 DB 저장이 아니라 audit log 설계라, 모니터링 화면을 만들려면
> judge 결과를 **조회 가능한 곳(audit log 조회 API 또는 경량 저장)**으로 노출하는 작업이 선행됨. (구현 시 결정)

---

## 7. 백엔드 API (신규/변경 요약)

**병원/원장**
- `GET /hospitals?query=` 병원 검색
- `GET /hospitals/{id}` 병원 상세
- `GET /hospitals/{id}/doctors` 원장 소개 리스트
- `GET/PUT /doctors/me/profile` 원장 본인 프로필
- `GET/PUT /hospitals/{id}` (대표원장) 병원 정보
- `GET/POST /hospitals/{id}/doctors` (대표원장) 소속 원장 관리

**보호자-병원**
- `GET/POST/DELETE /guardians/me/hospitals` 등록 병원 관리
- `PUT /guardians/me/hospitals/{id}/primary` 기본 병원

**예약 (변경)**
- 예약 생성에 `hospitalid` + `doctorid` 포함.

**가입 신청**
- `POST /signup-requests` (서류 업로드 multipart)
- `GET /signup-requests/{id}/status`

**운영자(admin)**
- `POST /admin/login`
- `GET /admin/signup-requests` / `GET /admin/signup-requests/{id}`
- `POST /admin/signup-requests/{id}/approve` → 병원+원장 자동 생성
- `POST /admin/signup-requests/{id}/reject`
- `GET /admin/validation/results` (필터) / `GET /admin/validation/results/{emrid}`
- `POST /admin/validation/benchmark/run` / `GET /admin/validation/benchmark/{runid}`
- `GET /admin/judge/results` / `POST /admin/judge/benchmark/run`

---

## 8. 마이그레이션 순서 (데이터 보존)

1. `hospitalDB` 신규 스키마 생성(역방향 FK 제거).
2. 기존 각 `doctor`의 `hospital_name/address/number/business_number` → `hospitalDB` 레코드로 추출.
   동일 사업자번호는 1개 병원으로 합침.
3. `doctor.hospitalid` 연결, 가장 먼저 만든 원장 = `owner`(또는 수동 지정).
4. `business_number` unique 제약을 doctor→hospital로 이동.
5. `guardian_hospitalDB` 생성. 기존 보호자는 등록 병원 0 → 온보딩으로 유도.
6. EMR/환자 조회 쿼리 `doctorid`→`hospitalid` 전환.
7. `clinic_signup_requestDB`, `admin_userDB` 생성.

---

## 9. 구현 우선순위

**MVP (먼저)**
1. 데이터 모델 + 마이그레이션 (1~8단계 핵심).
2. 운영자 백오피스 6-A (가입 승인 + 자동 생성) — 신규 병원 온보딩이 없으면 다중화 의미 없음.
3. company-web 가입 신청 폼(서류 업로드).
4. 보호자 병원 등록·전환(3-1) + 원장 소개 탭(3-2) + 예약 플로우(3-3).
5. 수의사 프로필 관리(4-2) + 환자 열람 범위 hospitalid 전환(4-6).

**2차 (확장)**
6. 대표원장 병원/원장 관리(4-3, 4-4), 병원 전체 예약 뷰(4-5).
7. 운영자 6-B Validation 모니터링·벤치마크.
8. 운영자 6-C Judge 모니터링·벤치마크 (audit log 조회 노출 선행).
9. 임시 비번 이메일 자동 발송, 신청 상태 조회.

---

## 10. 구현 전 확정 필요 항목

1. **임시 비밀번호 전달**: 초기 화면표시→수동 vs 이메일 자동발송(언제부터).
2. **추가 원장 생성 경로**: 가입 시 일괄 vs 대표원장이 운영 중 추가요청 vs 대표원장 직접 생성.
3. **Judge 결과 저장**: audit log만 vs 모니터링용 경량 테이블 추가(화면 조회 위해 필요).
4. **보호자 기록 필터**: 병원 전환 시 해당 병원만 vs 전체+뱃지.
5. **운영자 백오피스 인증 수준**: 단일 계정 vs 다중 운영자/권한.
</content>
</invoke>
