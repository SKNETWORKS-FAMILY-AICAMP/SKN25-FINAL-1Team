# 병원 온보딩 파이프라인 스펙 (문의폼 → 운영팀 발행 → 보호자 페이지)

> 작성: 2026-06-15
> 목적: 병원이 제출한 정보를 **운영팀이 "페이지 등록하기" 한 번으로 자동 발행**하도록,
> "문의 폼에서 받는 항목 = DB 저장 항목 = 보호자 페이지 노출 항목"을 하나의 스키마로 규정한다.
> 관련: [MULTI_HOSPITAL_PLAN.md](MULTI_HOSPITAL_PLAN.md), 보호자 페이지 = guardian-web `hospitals-page.tsx`

---

## 0. 핵심 원칙 — 단일 콘텐츠 스키마

```
[company-web 신청 폼]  ──제출──▶  [clinic_signup_requestDB + 파일스토리지]
                                          │ 운영팀 검토 + 미리보기
                                          ▼
                                  [운영팀 admin: "페이지 등록하기"]
                                          │ 자동 변환(재입력 0)
                                          ▼
                       [hospitalDB + doctorDB + 공개 프로필 + 계정 발급]
                                          │
                                          ▼
                            [보호자 guardian-web 병원 페이지]
```

폼 필드와 보호자 페이지 노출 항목이 **1:1**이므로 운영팀이 글/사진을 다시 칠 필요가 없다.

---

## 1. 콘텐츠 스키마 (필드 규정)

범례 — **필수**: ●(필수) ○(선택) · **공개**: 보호자 페이지 노출 여부 · **검증**: 신원확인용(비공개)

### 1-A. 병원 신원·계정 정보 (비공개, 검증용)

| 필드 | 키 | 타입 | 필수 | 제약 | 비고 |
|---|---|---|---|---|---|
| 병원명 | hospital_name | text | ● | ≤40자 | 공개(페이지 제목) |
| 사업자등록번호 | business_number | text | ● | 형식검증 10자리 | unique |
| 사업자등록증 파일 | business_license_file | file | ● | jpg/png/pdf, ≤10MB | 검증용 비공개 |
| 대표 연락처 | hospital_number | tel | ● | 전화형식 | **공개(연락처)** |
| 주소 | hospital_address | text | ● | — | **공개(오시는 길)** |
| 대표 이메일 | owner_email | email | ● | — | 계정 발급 통보용 |
| 희망 로그인 아이디 | desired_loginid | text | ● | 영숫자 4~20 | 중복확인 |
| 개인정보·이용 동의 | agree | bool | ● | true | — |

### 1-B. 병원 공개 콘텐츠 (보호자 페이지)

| 필드 | 키 | 타입 | 필수 | 제약 | 페이지 매핑 |
|---|---|---|---|---|---|
| 한 줄 소개 | tagline | text | ● | ≤45자 | 제목 아래 teal 문구 |
| 병원 소개 본문 | intro | textarea | ● | 80~600자, 줄바꿈 허용 | 소개 본문 |
| 진료시간 | hours | 구조화(1-D) | ● | — | 진료시간 칸 |
| 병원 특징 | features | tag[] | ○ | 0~6개, 각 ≤12자 | 특징 칩 |
| 배너 사진 | banner_image | file | ○ | jpg/png, ≤5MB, 가로형(16:9 권장, ≥1200px) | 상단 배너 |

### 1-C. 원장 정보 (반복, 1~N명)

원장 1명마다 아래 한 세트. 폼에서 "+ 원장 추가"로 반복.

| 필드 | 키 | 타입 | 필수 | 제약 | 공개 | 페이지 매핑 |
|---|---|---|---|---|---|---|
| 이름 | name | text | ● | ≤20자 | 공개 | 원장 이름 |
| 수의사 면허번호 | license_number | text | ● | — | 검증 | — |
| 면허증 파일 | license_file | file | ● | jpg/png/pdf, ≤10MB | 검증 | — |
| 이메일 | email | email | ○ | — | 검증 | 연락용(개별 로그인 없음) |
| 전문 진료 | specialty | text | ○ | ≤20자 | 공개 | 이름 아래 teal |
| 학력 | education | text | ○ | ≤40자 | 공개 | 학력 줄 |
| 소개글 | bio | textarea | ○ | ≤300자 | 공개 | 원장 소개 |
| 전문 분야 | specialty_areas | tag[] | ○ | 0~8개, 각 ≤12자 | 공개 | 전문분야 칩 |
| 사진 | profile_image | file | ○ | jpg/png, ≤5MB, 세로 인물 권장(3:4, ≥600px) | 공개 | 원장 사진 |

> 누락 시 보호자 페이지는 폴백 처리(이미 구현): 사진 없음 → 이니셜, 소개 없음 → "소개글 미등록", 정보 없음 → "정보 없음".

### 1-D. 진료시간 구조 (규칙적으로 받기)

자유 텍스트 대신 **요일 버킷 + 시간**으로 받아 일관되게 렌더.

```jsonc
hours: {
  weekday:  { open: "09:00", close: "20:00" },     // 평일
  saturday: { open: "09:00", close: "18:00" },     // 토
  sunday:   null,                                   // 일 (null = 휴진)
  holiday:  null,                                   // 공휴일
  lunch:    { start: "12:30", end: "13:30" } | null // 점심(선택)
}
```
→ 보호자 페이지에서 "평일 09:00~20:00 / 토 09:00~18:00 / 일·공휴일 휴진" 형태로 자동 조립.

---

## 2. company-web 신청 폼 (규칙)

- **분기**: 기존 일반 문의 폼은 유지하고, "동물병원 입점 신청"은 **별도 전용 폼**(`/apply` 또는 섹션)으로 분리. 위 1-A~1-C 전체를 받음.
- **UX 규칙**:
  - 파일 업로드(드래그앤드롭) + 즉시 썸네일 미리보기 + 용량/형식/비율 검증.
  - 원장 섹션은 "+ 원장 추가 / 삭제"로 1~N 반복.
  - 글자수 카운터(tagline/intro/bio), 태그 입력(features/specialty_areas).
  - 필수 누락·형식 오류 인라인 표시, 통과 전 제출 비활성.
  - 제출 직전 **"보호자에게 이렇게 보여요" 미리보기** 토글(선택이지만 권장).
- **제출 처리**: `POST /signup-requests` (multipart) → `clinic_signup_requestDB` + 파일 스토리지 저장 → 접수번호 발급/안내.

---

## 3. 운영팀 admin 사이트

> 위치: company-web 내 보호된 `/admin` (운영자 로그인). 자세한 권한은 MULTI_HOSPITAL_PLAN §6.

- **신청 목록**: 상태(접수/검토중/승인발행/반려) 필터, 신청일 정렬.
- **신청 상세**:
  - 입력 콘텐츠 전체 + **첨부 서류 뷰어**(사업자등록증·면허증).
  - **보호자 페이지 실시간 미리보기**(guardian-web과 동일 렌더 컴포넌트 재사용).
- **"페이지 등록하기"(발행) 버튼 → 자동 처리** (운영자 재입력 0):
  1. `hospitalDB` 생성 + 공개 콘텐츠(tagline/intro/hours/features/banner) 저장
  2. 원장들 `doctorDB` + 공개 프로필(specialty/education/bio/areas/photo) 생성
  3. 업로드 사진을 정식 스토리지로 연결(임시 → 정식 경로)
  4. 로그인 아이디 + **임시 비밀번호 발급**(`is_initial_password=True`), 대표/원장 이메일 통보
  5. 신청 상태 = `승인발행`, 생성된 hospitalid 역참조
- **반려**: 사유 입력 → 상태 `반려` + 회신.
- **재발행/수정**: 병원이 추후 콘텐츠 수정 요청 시 같은 흐름으로 갱신.

---

## 4. 백엔드 추가 필요 (현재 스키마 갭)

현재 `hospitalDB`(name/address/number/business_number/계정)·`doctorDB`(hospitalid/name/license/email)에는
**공개 콘텐츠 필드가 없음.** 아래 추가 필요:

- **병원 공개 프로필**: `hospitalDB`에 컬럼 추가 또는 별도 `hospital_profileDB`
  (tagline, intro, hours(JSON), features(JSON), banner_image_url).
- **원장 공개 프로필**: `doctorDB`에 컬럼 추가 또는 별도 `doctor_profileDB`
  (specialty, education, bio, specialty_areas(JSON), profile_image_url).
- **신청 원본 보관**: `clinic_signup_requestDB`(1-A~1-C 전체 + 파일 경로 + status + reject_reason).
- **파일 스토리지**: 업로드 이미지·서류 저장소(S3 또는 정적 디렉터리) + 서빙 URL.
  보호자 페이지의 현재 `/assets/...` 목업 경로를 실제 업로드 URL로 교체.
- **API**: `POST /signup-requests`, `GET/POST /admin/signup-requests/{id}/(approve|reject)`,
  발행 시 위 자동 처리 로직.

---

## 5. 구현 순서 (제안)

1. **콘텐츠 스키마 확정**(이 문서 §1) — 폼·DB·페이지가 공유할 타입 정의.
2. 백엔드: `clinic_signup_requestDB` + 공개 프로필 컬럼/테이블 + 파일 스토리지 + 신청 API.
3. company-web: 동물병원 입점 신청 전용 폼(§2).
4. 운영팀 admin: 신청 목록·상세·미리보기 + "페이지 등록하기" 발행(§3).
5. guardian-web: 목업 → 실제 API로 교체(이미 구조 동일).

---

## 6. 결정 사항 (확정)

1. **공개 프로필 저장** → **별도 1:1 테이블 `hospital_profileDB` / `doctor_profileDB` 신설.**
   인증/신원 테이블(`hospitalDB`)과 분리, 콘텐츠 필드는 전부 nullable.
   - `hospital_profileDB`(hospitalid FK): tagline, intro(text), banner_image_url, features(JSON)
   - `doctor_profileDB`(doctorid FK): specialty, education, bio(text), specialty_areas(JSON), profile_image_url
   - 진료시간은 여기 두지 않고 **기존 `vet_scheduleDB` 재사용**(3번).
2. **파일 스토리지** → **기존 S3 그대로 사용.** 시스템에 이미 boto3 + `app/utils/s3.py`
   (presigned PUT → 프론트 직접 업로드 → CloudFront 읽기 URL을 DB 저장) 구축됨.
   prefix만 추가: `hospital`(배너), `doctor`(사진), `signup-docs`(사업자등록증·면허증, 비공개).
3. **진료시간** → **요일 버킷, 기존 `vet_scheduleDB` 재사용.** vet-web `OperatingHoursContext`가
   이미 `vet_scheduleDB`(day_of_week/start_time/end_time/lunch/is_open) + 휴진일을 읽어 표시.
   온보딩도 같은 테이블에 저장 → 수의사 웹과 자동 일치. (§1-D의 별도 JSON 구조는 불필요)
4. **admin 사이트** → **company-web `/admin` 통합.** 운영진 웹에 띄울 것:
   ① 신청 프로필 받아 "페이지 등록하기" 자동 발행 ② Validation 모니터링 ③ Judge 모니터링.
5. ~~원장 계정: 개별 로그인 vs 병원 단위~~ → **확정: 병원 단위 단일 로그인 + UI에서 원장 선택.**
   원장은 **로그인 없는 프로필**(예약/EMR/소개에서 선택만). 원장 `email`은 연락용 선택값(계정 발급 X).
   근거: 백엔드 `get_current_hospital`(병원 단위) + vet-web도 이미 병원 로그인(`HospitalUser`,
   role `HOSPITAL_ADMIN`/`VETERINARIAN`) 후 `doctors` 목록에서 원장 선택하는 구조로 구현됨.
