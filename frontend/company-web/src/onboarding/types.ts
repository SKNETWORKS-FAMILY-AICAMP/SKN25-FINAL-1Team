/**
 * 병원 입점 온보딩 공유 타입.
 *
 * 신청 폼(/apply) → 스토어 → 운영진 웹(/admin) 발행 → 보호자 페이지가 공유하는 스키마.
 * 필드 규정은 HOSPITAL_ONBOARDING_SPEC.md §1 기준.
 *
 * ⚠️ 백엔드 API 확정 전까지 localStorage mock 으로 동작한다. 실제 연동 시:
 *   - 파일은 S3 presigned 업로드 → URL 저장 (지금은 미리보기용 dataURL)
 *   - status/발행은 admin API 로 교체
 */

export type ApplicationStatus = "접수" | "검토중" | "승인발행" | "반려";

/** 업로드 파일 (mock: 이름 + 이미지 미리보기 dataURL). 실제론 S3 URL 로 교체. */
export interface UploadedFile {
  name: string;
  /** 이미지일 때만 미리보기용 dataURL (서류 PDF 등은 비움) */
  dataUrl?: string;
}

/** 진료시간 — 요일 버킷 (HOSPITAL_ONBOARDING_SPEC §1-D, vet_scheduleDB 와 동형). */
export interface DayHours {
  open: string; // "09:00"
  close: string; // "20:00"
}
export interface OperatingHours {
  weekday: DayHours | null; // 평일 (null = 휴진)
  saturday: DayHours | null; // 토
  sunday: DayHours | null; // 일
  holiday: DayHours | null; // 공휴일
  lunch: { start: string; end: string } | null; // 점심시간 (선택)
}

/** 원장 (로그인 없는 프로필 — 병원 단위 로그인 + UI 선택 모델). */
export interface DoctorApplication {
  /** 폼 내부 식별용(서버 id 아님) */
  key: string;
  // 신원(검증·비공개)
  name: string;
  licenseNumber: string;
  licenseFile?: UploadedFile;
  email?: string;
  // 공개 콘텐츠
  specialty?: string;
  education?: string;
  bio?: string;
  specialtyAreas: string[];
  photo?: UploadedFile;
}

export interface HospitalApplication {
  id: string;
  // ── 신원·계정 (비공개/검증) ──────────────────────────────
  hospitalName: string;
  businessNumber: string;
  businessLicenseFile?: UploadedFile;
  hospitalPhone: string;
  hospitalAddress: string;
  ownerEmail: string;
  desiredLoginId: string;
  // ── 병원 공개 콘텐츠 ─────────────────────────────────────
  tagline: string;
  intro: string;
  features: string[];
  banner?: UploadedFile;
  hours: OperatingHours;
  // ── 원장 (1~N) ─────────────────────────────────────────
  doctors: DoctorApplication[];
  // ── 메타 ───────────────────────────────────────────────
  status: ApplicationStatus;
  createdAt: string;
  reviewedAt?: string;
  rejectReason?: string;
  /** 발행 시 부여한 임시 비밀번호(데모용 표시) */
  issuedTempPassword?: string;
}

export const EMPTY_HOURS: OperatingHours = {
  weekday: { open: "09:00", close: "20:00" },
  saturday: { open: "09:00", close: "18:00" },
  sunday: null,
  holiday: null,
  lunch: { start: "12:30", end: "13:30" },
};

/** 필드 제약(스펙 §1) — 폼·검증 공용 상수. */
export const LIMITS = {
  tagline: 45,
  intro: 600,
  introMin: 10,
  bio: 300,
  feature: 12,
  features: 6,
  area: 12,
  areas: 8,
} as const;
