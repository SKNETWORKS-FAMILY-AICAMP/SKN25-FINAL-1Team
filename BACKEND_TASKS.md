# 백엔드 작업 핸드오프 — 다중 병원·온보딩·예약·운영진

> 작성: 2026-06-15
> 목적: 프론트(보호자/입점신청/운영진)와 백엔드 온보딩 API의 구현/연동 범위를 팀에 공유한다.
> 현재 company-web/guardian-web은 API 연동이 들어갔고, 백엔드 미가동·데이터 없음 상황에서 일부 mock fallback을 유지한다.
> **필드명은 프론트가 기대하는 그대로** 적었으니 이름 맞춰서 내려주면 매핑 작업 0.
> 관련: [HOSPITAL_ONBOARDING_SPEC.md](HOSPITAL_ONBOARDING_SPEC.md), [MULTI_HOSPITAL_PLAN.md](MULTI_HOSPITAL_PLAN.md)

공통:
- 응답 래퍼는 기존 관례 그대로 `{ "code": 200, "message": "...", "result": ... }`.
- 인증: 보호자=`get_current_user`, 병원=`get_current_hospital`(이미 있음), 운영자=신규 `get_current_admin`.
- 날짜 `YYYY-MM-DD`, 시간 `HH:MM`.

## 0. 현재 구현 상태

2026-06-15 현재 이 문서의 핵심 백엔드 작업은 코드상 대부분 구현 완료.

- 신규 테이블 5개 모델 + guard 마이그레이션 추가 완료.
- 보호자 병원 API, 내 병원 M:N API, 입점 신청 API, 운영진 admin API 추가 완료.
- company-web `/apply`는 S3 presigned URL 업로드 후 `/signup-requests` 저장으로 연결 완료.
- company-web `/admin`은 로그인, 신청 목록/상세, 승인 발행/반려, Validation/Judge 모니터링 API 연결 완료.
- 승인 발행은 `hospitalDB` / `hospital_profileDB` / `doctorDB` / `doctor_profileDB`를 생성.
- 신청 진료시간은 `clinic_signup_requestDB.hours`와 `doctors[].hours`에 원본 보존.
- `vet_scheduleDB` write는 다른 팀원의 스케줄 DB 개편과 충돌하지 않도록 현재 PR에서 막아둠.
- 추후 vet 스케줄 DB가 병원 기본/원장별/특정일 예외 테이블로 쪼개지면 `app/services/schedule_provisioning.py`를 새 구조에 맞게 연결하면 됨.
- `dev.sh`는 새 마이그레이션과 운영자 계정 seed를 실행하도록 보강됨.

팀원이 로컬에서 확인할 때 필요한 실행 작업:

1. S3 버킷 CORS에 `http://localhost:5175` 추가.
2. `./dev.sh` 또는 `./dev.sh fast` 실행으로 마이그레이션 적용.
3. 운영진 로그인: `admin / Admin1234!`.

---

## 1. DB 작업 (마이그레이션, guard 패턴 유지)

### 1-1. 신규 테이블

**`hospital_profileDB`** (병원 공개 콘텐츠, hospitalid 1:1)
| 컬럼 | 타입 | 비고 |
|---|---|---|
| hospitalid | FK PK → hospitalDB | |
| tagline | varchar(60) | 한 줄 소개 |
| intro | text | 소개 본문 |
| banner_image_url | text null | S3 URL |
| features | JSON | string[] (병원 특징 태그) |
| updated_at | timestamptz | |

**`doctor_profileDB`** (원장 공개 콘텐츠, doctorid 1:1)
| 컬럼 | 타입 | 비고 |
|---|---|---|
| doctorid | FK PK → doctorDB | |
| specialty | varchar(40) null | 전문 진료 ("내과 전문 진료") |
| education | varchar(60) null | 학력 |
| bio | text null | 소개글 |
| specialty_areas | JSON | string[] (전문 분야) |
| profile_image_url | text null | S3 URL |
| updated_at | timestamptz | |

**`clinic_signup_requestDB`** (입점 신청 원본 + 검토 상태)
| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | PK | |
| hospital_name / business_number / hospital_phone / hospital_address / owner_email / desired_loginid | varchar | 신원·계정 |
| business_license_url | text | S3 (사업자등록증) |
| tagline / intro | text | 공개 콘텐츠 |
| features | JSON | string[] |
| banner_image_url | text null | S3 |
| hours | JSON | OperatingHours (아래 4-D 구조) |
| doctors | JSON | DoctorApplication[] (이름·면허번호·면허증url·이메일·specialty·education·bio·specialty_areas·photo_url) |
| status | varchar | `접수` / `검토중` / `승인발행` / `반려` |
| reject_reason | text null | |
| created_hospitalid | FK null | 발행 시 생성된 병원 |
| created_at / reviewed_at | timestamptz | |

**`admin_userDB`** (운영자) — `adminid, loginid(unique), password(bcrypt), name, created_at`. 초기 1계정이면 충분.

**`guardian_hospitalDB`** (보호자 M:N 병원) — `id, userid FK, hospitalid FK, is_primary bool, created_at`. unique(userid, hospitalid).

### 1-2. 기존 테이블 활용
- `hospitalDB` (name/address/number/business_number/creds): 그대로. 공개 콘텐츠는 위 profile 테이블로 분리.
- `doctorDB` (hospitalid FK, name, license, email): 그대로. 공개 콘텐츠는 doctor_profileDB.
- `vet_scheduleDB`: 현재 예약 슬롯 source of truth. 단, 입점 발행에서 이 테이블에 쓰는 부분은 스케줄 DB 개편과 충돌 방지를 위해 주석 처리. 보호자 병원조회는 기존처럼 여기서 읽어 표시 문자열을 만들되, 스케줄 미등록 병원은 `hours=null` fallback.

---

## 2. S3 (이미 `app/utils/s3.py` 있음 — presigned 패턴 그대로)
- prefix 추가: `hospital`(배너), `doctor`(원장 사진), `signup-docs`(사업자등록증·면허증, 비공개).
- 업로드 엔드포인트: `GET /uploads/presigned-url?file_name=...&content_type=...&prefix=hospital|doctor|signup-docs` → `{ presigned_url, cloudfront_url }`.
- 프론트가 직접 PUT 후 `cloudfront_url`을 신청 JSON에 담아 제출.
- S3 CORS에는 최소 `http://localhost:5173`, `http://localhost:5174`, `http://localhost:5175` 허용 필요.

---

## 3. API — 보호자(guardian)

### 3-A. 내 병원 목록 (M:N)
`GET /guardians/me/hospitals`  (auth: user)
```json
{ "code": 200, "result": [
  { "hospitalid": 1, "name": "메디포 동물병원", "is_primary": true }
] }
```
`POST /guardians/me/hospitals` body `{ "hospitalid": 1 }` → 등록
`DELETE /guardians/me/hospitals/{hospitalid}` → 해제
`PUT /guardians/me/hospitals/{hospitalid}/primary` → 기본 병원 지정

### 3-B. 병원 상세 (보호자 병원탭 — mock Hospital 형태 그대로)
`GET /hospitals/{hospitalid}`  (auth: user)
```json
{ "code": 200, "result": {
  "hospitalid": 1,
  "name": "메디포 동물병원",
  "tagline": "반려동물과 보호자가 안심할 수 있는 진료 환경",
  "intro": "메디포 동물병원은 ...",
  "address": "서울특별시 강남구 테헤란로 123, 2층",
  "phone": "02-1234-5678",
  "hours": "평일 09:00 ~ 20:00\n토요일 09:00 ~ 18:00\n일요일·공휴일 휴진",
  "bannerImage": "https://cdn.../hospital/...png",
  "features": ["정확한 진단", "맞춤 진료"],
  "doctors": [
    {
      "doctorid": 11,
      "name": "김민지 원장",
      "specialty": "내과 전문 진료",
      "education": "서울대학교 수의과대학 졸업",
      "bio": "10년 이상의 임상 경험 ...",
      "specialtyAreas": ["내과 진료", "노령동물 건강관리"],
      "profileImage": "https://cdn.../doctor/...png"
    }
  ]
} }
```
> `hours`는 `vet_scheduleDB`에서 만든 표시 문자열(여러 줄). `bannerImage`/`profileImage`/`specialtyAreas` 카멜케이스 그대로(프론트 hospital-mock과 동일). 값 없으면 `null`/`[]` — 프론트가 폴백 처리함.
> 병원 검색이 필요하면 `GET /hospitals?query=` 추가(같은 카드 형태 배열).

---

## 4. API — 예약 (다중 원장)

### 4-A. 슬롯 조회 — **`doctor_name` 채워주기** (이미 있는 엔드포인트 보강)
`GET /schedules/available?date=YYYY-MM-DD&duration_min=30&hospitalid=1&doctorid=11`
(`hospitalid`·`doctorid` 모두 선택 필터 — 둘 다 프론트가 보냄. hospitalid 주면 그 병원 슬롯만, doctorid 주면 그 원장만)
```json
{ "code": 200, "result": [
  { "start_time": "15:00", "end_time": "15:55", "doctorid": 11, "doctor_name": "김민지 원장" },
  { "start_time": "15:30", "end_time": "16:25", "doctorid": 12, "doctor_name": "박서준 원장" }
] }
```
> ⚠️ **`doctor_name`을 꼭 채워야** 챗봇/모달의 원장별 추천·그룹핑 UI가 켜진다. 지금 `doctorid`만 오고 `doctor_name`이 비면 프론트는 평평한 목록으로 폴백(안 깨짐). `doctorid` 주면 해당 원장 슬롯만 필터.

### 4-B. 예약 생성 (payload에 hospitalid/doctorid 추가됨)
`POST /schedules/checkup`  (auth: user)
```json
{ "pet_id": 1, "date": "2026-06-16", "time": "15:00", "memo": "",
  "category_code": 1, "hospitalid": 1, "doctorid": 11 }
```
→ 기존 응답 형태 유지. `doctorid`로 해당 원장에 예약(충돌 제약 `uq_schedule_doctor_time` 그대로 동작).

### 4-C. 챗봇 예약 확정 (이미 있는 엔드포인트 — payload에 hospitalid 추가됨)
`POST /schedules/confirm` body `{ emrid, doctorid, confirmed_time, duration_min, hospitalid? }`
→ 기존 응답 유지(`result.hospital_name`/`doctor_name` 포함). `hospitalid`는 선택(스코핑·검증용).

### 4-D. 예약 목록 — 이미 `hospital_name`/`doctor_name` 내려주는 형태 유지(추가 작업 없음).

---

## 5. API — 입점 신청 (company-web /apply)

`POST /signup-requests`  (인증 불필요, 공개 폼)
요청 body (파일은 미리 S3 업로드 후 URL):
```json
{
  "hospitalName": "메디포 동물병원",
  "businessNumber": "1234567890",
  "businessLicenseUrl": "https://cdn.../signup-docs/...pdf",
  "hospitalPhone": "02-1234-5678",
  "hospitalAddress": "서울 강남구 ...",
  "ownerEmail": "hospital@email.com",
  "desiredLoginId": "medipaw_gangnam",
  "tagline": "...", "intro": "...",
  "features": ["정확한 진단"],
  "bannerUrl": "https://cdn.../hospital/...png",
  "hours": { "weekday": {"open":"09:00","close":"20:00"},
             "saturday": {"open":"09:00","close":"18:00"},
             "sunday": null, "holiday": null,
             "lunch": {"start":"12:30","end":"13:30"} },
  "doctors": [
    { "name":"김민지 원장", "licenseNumber":"제12345호",
      "licenseUrl":"https://cdn.../signup-docs/...pdf", "email":"",
      "specialty":"내과 전문 진료", "education":"서울대 수의대 졸업",
      "bio":"...", "specialtyAreas":["내과 진료"],
      "photoUrl":"https://cdn.../doctor/...png" }
  ]
}
```
응답: `{ "code": 200, "result": { "id": "...", "status": "접수" } }`
> 프론트 현재는 파일을 dataURL로 들고 있음 — 실연동 시 S3 업로드 → URL로 바꿔 보냄(프론트 작업). 백엔드는 위 JSON만 받으면 됨.

---

## 6. API — 운영진(admin)

### 6-A. 로그인
`POST /admin/login` body `{ "loginid", "password" }` → `{ code, result: { access_token } }` (type="admin").

### 6-B. 신청 목록 / 상세
`GET /admin/signup-requests?status=접수`  (auth: admin) → 신청 배열(위 신청 JSON + status/createdAt).
`GET /admin/signup-requests/{id}` → 단건(서류 URL 포함).

### 6-C. 발행 (★ 자동 처리 핵심)
`POST /admin/signup-requests/{id}/approve`  (auth: admin) → 서버가 **한 번에**:
1. `hospitalDB` 생성 (name/address/number/business_number) + `loginid`=desiredLoginId, `password`=임시비번 해시, `is_initial_password=true`
2. `hospital_profileDB` 생성 (tagline/intro/banner/features)
3. 각 원장 → `doctorDB`(hospitalid 연결) + `doctor_profileDB`(specialty/education/bio/areas/photo)
4. `hours`는 신청 원본에 보존. `vet_scheduleDB` 반영은 스케줄 DB 개편 이후 연결
5. 신청 `status="승인발행"`, `created_hospitalid` 기록
6. 대표 이메일로 `loginid`+임시비번 발송 (기존 `app/core/email.py` 재사용)

응답:
```json
{ "code": 200, "result": { "hospitalid": 1, "loginid": "medipaw_gangnam", "temp_password": "..." } }
```
> 임시비번 생성·이메일은 기존 `doctor_auth.py`의 `secrets`+`send_account_credentials` 로직 재사용.

### 6-D. 반려
`POST /admin/signup-requests/{id}/reject` body `{ "reason": "..." }` → `status="반려"`.

---

## 7. API — Validation / Judge 모니터링 (운영진 패널)

### 7-A. Validation
`GET /admin/validation/results?attention_only=false`  (auth: admin)
`validation_resultDB` + validation.py 출력 기준:
```json
{ "code": 200, "result": [
  { "emrid": 1042, "createdAt": "2026-06-15T09:12:00", "overall": "OK",
    "completeness": 10,
    "checks": [
      { "item":"데이터 완전성", "status":"PASS", "detail":"필수 문진 정보 모두 수집됨" },
      { "item":"문진-차트 일치도", "status":"PASS", "detail":"일치율 100%" },
      { "item":"예약 안전성", "status":"PASS", "detail":"예약 메타데이터 정상" },
      { "item":"응급신호 정합성", "status":"PASS", "detail":"응급 신호 미감지" }
    ],
    "summary":"특이 검증 이슈 없음" }
] }
```
(status: `PASS`|`WARN`|`SKIPPED`, overall: `OK`|`ATTENTION`)

### 7-B. Judge
`GET /admin/judge/results?needs_review_only=false`  (auth: admin)
`agent_pipeline_resultDB.judge_result` JSON 기준:
```json
{ "code": 200, "result": [
  { "emrid": 1043, "createdAt": "2026-06-15T08:40:00",
    "verdict": "NEEDS_REVIEW",
    "scores": { "completeness":8.0, "question_efficiency":8.5,
                "response_consistency":6.4, "structuring_quality":7.2 },
    "turnCount": 6, "notes": "대화-구조화 일관성 낮음" }
] }
```
(verdict: `HEALTHY`|`NEEDS_REVIEW`)
> 새 테이블 없음. 현재 admin 라우트는 `agent_pipeline_resultDB.judge_result`를 읽어 내려준다.

---

## 9. 건드릴 파일 맵 (백엔드)

> 마이그레이션은 기존 f1/g2/h1처럼 **수동 작성 + guard 패턴**(`inspector.get_columns`). autogenerate 아님.
> 파일 업로드는 `app/api/chat.py`의 `/upload/presigned-url`(→ `app/utils/s3.py create_presigned_put`) 패턴 재사용.

### 신규 파일
| 파일 | 내용 |
|---|---|
| `app/models/hospital_profile.py` | `hospital_profileDB` (§1-1) |
| `app/models/doctor_profile.py` | `doctor_profileDB` |
| `app/models/clinic_signup_request.py` | `clinic_signup_requestDB` |
| `app/models/admin_user.py` | `admin_userDB` |
| `app/models/guardian_hospital.py` | `guardian_hospitalDB` |
| `backend/migrations/versions/<id>_add_onboarding_tables.py` | 위 5개 테이블 생성 (guard 패턴) |
| `app/schemas/hospital.py` | 병원 상세/내병원 응답 (§3) |
| `app/schemas/onboarding.py` | 입점 신청 요청/응답 + OperatingHours + DoctorApplication (§5) |
| `app/schemas/admin.py` | admin 로그인/신청 목록 (§6) |
| `app/crud/signup_request.py` | 신청 생성·목록·상세·**발행**·반려 (§5·6) |
| `app/crud/admin.py` | admin 인증 |
| `app/crud/guardian_hospital.py` | 내 병원 list/add/remove/primary (§3-A) |
| `app/services/schedule_provisioning.py` | 스케줄 DB 개편 이후 입점 신청 진료시간을 실제 스케줄 저장소에 반영할 호환 계층 |
| `app/api/hospitals.py` | `GET /hospitals`, `/hospitals/{id}`, `/guardians/me/hospitals` (§3) |
| `app/api/signup_requests.py` | `POST /signup-requests` (§5) |
| `app/api/admin.py` | `/admin/login`, `/admin/signup-requests…`, `/admin/validation|judge` (§6·7) |
| `app/api/uploads.py` *(선택)* | 별도 파일은 만들지 않음. 현재는 `app/api/signup_requests.py`에 `/uploads/presigned-url` 포함 |

### 수정 파일
| 파일 | 수정 |
|---|---|
| `app/crud/schedule.py` | `get_available_slots(... hospitalid=None)` 파라미터 추가 + 필터 |
| `app/api/schedules.py` | `/available`에 `hospitalid` 쿼리 전달, `/confirm`에 `hospitalid` 수용 |
| `app/crud/hospital.py` *(이미 있음)* | 병원 상세(프로필+원장 조인), 병원 검색 |
| `app/crud/doctor.py` *(이미 있음)* | 병원별 원장 + doctor_profile 조인 |
| `app/core/dependencies.py` | `get_current_admin` 추가 (get_current_hospital 복사, type=="admin") |
| `app/main.py` | `hospitals_router` / `signup_requests_router` / `admin_router` (+uploads) 등록 |
| `dev.sh` | 로컬 실행 시 마이그레이션 + admin seed 실행 |
| `ai/docker/nginx-company.conf` | company 정적 서버에서 `/api/` → backend 프록시 |

### 재사용 (수정 거의 없음)
- 임시비번·이메일: `app/core/email.py send_account_credentials` + `app/api/doctor_auth.py`의 `secrets` 로직 (발행 시 호출).
- 토큰: `app/core/security.py create_access_token({"type":"admin"})` 그대로.
- 진료시간 저장: 신청 원본 JSON에는 저장 완료. 실제 스케줄 저장소 반영은 스케줄 DB 개편 이후 `app/services/schedule_provisioning.py`에서 연결.
- **Judge/Validation 모니터링(§7)**: 새 테이블 불필요 —
  Validation은 `validation_resultDB`, Judge는 `agent_pipeline_resultDB.judge_result`를 읽어 내려줌.

---

## 8. 우선순위 (붙이는 순서 기준)
1. **3-B 병원 상세** + **4-A 슬롯 doctor_name** → 보호자 병원탭·예약이 실데이터로 바로 켜짐 (효과 가장 큼)
2. **5 입점 신청** + **6 운영진 발행** → 온보딩 파이프라인 실동작
3. **3-A 보호자 M:N 병원** + **4-B 예약 hospitalid/doctorid**
4. **7 Validation/Judge 조회** (Judge는 적재 선행)

프론트는 위 API 기준으로 연결되어 있고, 데이터 없음/백엔드 미가동 상황에서만 mock fallback을 사용한다.
</content>
