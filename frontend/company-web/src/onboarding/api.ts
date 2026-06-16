/**
 * 백엔드 연동 (fetch). base=/api → company nginx 가 backend:8000 으로 프록시.
 * 입점 신청(공개) + 운영진 콘솔(admin 토큰).
 */
import type { OperatingHours } from "./types";
import type { ValidationRecord, JudgeRecord } from "../pages/admin/monitoring-mock";

const API = (import.meta.env.VITE_API_BASE_URL as string) || "/api";
const TOKEN_KEY = "medipaw.admin.token";

export const getAdminToken = () => window.localStorage.getItem(TOKEN_KEY);
export const setAdminToken = (t: string) => window.localStorage.setItem(TOKEN_KEY, t);
export const clearAdminToken = () => window.localStorage.removeItem(TOKEN_KEY);
export const isAdminAuthed = () => Boolean(getAdminToken());

function authHeaders(): Record<string, string> {
  const t = getAdminToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function asJson(res: Response) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const error = data as { detail?: string; message?: string };
    throw new Error(error.detail || error.message || `요청 실패 (${res.status})`);
  }
  return data;
}

const CHECK_LABELS = ["데이터 완전성", "문진-차트 일치도", "예약 안전성", "응급신호 정합성"];

function toNumber(value: unknown, fallback = 0): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function normalizeValidationRecord(raw: any): ValidationRecord {
  const checks = Array.isArray(raw?.checks)
    ? raw.checks.map((c: any, i: number) => ({
        item: String(c?.item || CHECK_LABELS[i] || "기타"),
        status: (["PASS", "WARN", "SKIPPED"].includes(c?.status) ? c.status : "SKIPPED") as ValidationRecord["checks"][number]["status"],
        detail: String(c?.detail || ""),
      }))
    : [];
  return {
    emrid: toNumber(raw?.emrid),
    createdAt: String(raw?.createdAt || ""),
    overall: raw?.overall === "ATTENTION" ? "ATTENTION" : "OK",
    checks,
    completeness: toNumber(raw?.completeness),
    summary: String(raw?.summary || ""),
  };
}

function normalizeJudgeRecord(raw: any): JudgeRecord {
  const scores = raw?.scores || {};
  return {
    emrid: toNumber(raw?.emrid),
    createdAt: String(raw?.createdAt || ""),
    verdict: raw?.verdict === "NEEDS_REVIEW" ? "NEEDS_REVIEW" : "HEALTHY",
    scores: {
      completeness: toNumber(scores.completeness),
      question_efficiency: toNumber(scores.question_efficiency),
      response_consistency: toNumber(scores.response_consistency),
      structuring_quality: toNumber(scores.structuring_quality),
    },
    turnCount: toNumber(raw?.turnCount),
    notes: String(raw?.notes || ""),
  };
}

// ── 입점 신청 (공개) ────────────────────────────────────────
export interface DoctorApplicationPayload {
  name: string;
  licenseNumber: string;
  licenseUrl?: string;
  email?: string;
  specialty?: string;
  education?: string;
  bio?: string;
  specialtyAreas: string[];
  photoUrl?: string;
  hours?: OperatingHours;
}

export interface SignupRequestPayload {
  hospitalName: string;
  businessNumber: string;
  businessLicenseUrl?: string;
  hospitalPhone?: string;
  hospitalAddress?: string;
  ownerEmail?: string;
  desiredLoginId: string;
  tagline?: string;
  intro?: string;
  features: string[];
  bannerUrl?: string;
  hours?: OperatingHours;
  doctors: DoctorApplicationPayload[];
}

/** 운영진 목록/상세 응답 (백엔드 SignupRequestOut). */
export interface ApplicationOut extends SignupRequestPayload {
  id: number;
  status: "접수" | "검토중" | "승인발행" | "반려";
  rejectReason?: string | null;
  createdHospitalid?: number | null;
  createdAt?: string | null;
}

/** S3 presigned 업로드 → 읽기 URL 반환. (dev 더미 자격증명이면 실패할 수 있음) */
export async function uploadFile(file: File, prefix: "hospital" | "doctor" | "signup-docs"): Promise<string> {
  const q = new URLSearchParams({ file_name: file.name, content_type: file.type || "application/octet-stream", prefix });
  const data = await asJson(await fetch(`${API}/uploads/presigned-url?${q}`));
  const { presigned_url, cloudfront_url } = data.result;
  try {
    const put = await fetch(presigned_url, { method: "PUT", headers: { "Content-Type": file.type }, body: file });
    if (!put.ok) throw new Error("파일 업로드 실패");
  } catch (err) {
    const localFallback = String(cloudfront_url || "").startsWith("http://localhost/");
    if (!localFallback) throw err;
  }
  return cloudfront_url as string;
}

export async function submitSignupRequest(payload: SignupRequestPayload): Promise<{ id: number; status: string }> {
  const data = await asJson(
    await fetch(`${API}/signup-requests`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
  return data.result;
}

// ── 운영진 ─────────────────────────────────────────────────
export async function adminLogin(loginid: string, password: string): Promise<void> {
  const data = await asJson(
    await fetch(`${API}/admin/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ loginid, password }),
    }),
  );
  setAdminToken(data.result.access_token);
}

export async function listApplications(status?: string): Promise<ApplicationOut[]> {
  const q = status && status !== "전체" ? `?status=${encodeURIComponent(status)}` : "";
  const data = await asJson(await fetch(`${API}/admin/signup-requests${q}`, { headers: authHeaders() }));
  return data.result ?? [];
}

export async function getApplication(id: number): Promise<ApplicationOut> {
  const data = await asJson(await fetch(`${API}/admin/signup-requests/${id}`, { headers: authHeaders() }));
  return data.result;
}

export async function approveApplication(id: number): Promise<{ hospitalid: number; loginid: string; temp_password: string }> {
  const data = await asJson(
    await fetch(`${API}/admin/signup-requests/${id}/approve`, { method: "POST", headers: authHeaders() }),
  );
  return data.result;
}

export async function rejectApplication(id: number, reason: string): Promise<void> {
  await asJson(
    await fetch(`${API}/admin/signup-requests/${id}/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ reason }),
    }),
  );
}

export async function getValidationResults(attentionOnly: boolean): Promise<ValidationRecord[]> {
  const data = await asJson(
    await fetch(`${API}/admin/validation/results?attention_only=${attentionOnly}`, { headers: authHeaders() }),
  );
  return Array.isArray(data.result) ? data.result.map(normalizeValidationRecord) : [];
}

export async function getJudgeResults(needsReviewOnly: boolean): Promise<JudgeRecord[]> {
  const data = await asJson(
    await fetch(`${API}/admin/judge/results?needs_review_only=${needsReviewOnly}`, { headers: authHeaders() }),
  );
  return Array.isArray(data.result) ? data.result.map(normalizeJudgeRecord) : [];
}

// ── 운영진: 병원/원장 프로필 관리 ───────────────────────────
export interface AdminHospitalListItem {
  hospitalid: number;
  name: string;
  address?: string | null;
  phone?: string | null;
  doctorCount: number;
}

export interface AdminDoctor {
  doctorid: number;
  name: string;
  licenseNumber?: string | null;
  email?: string | null;
  is_active: boolean;
  specialty?: string | null;
  education?: string | null;
  bio?: string | null;
  specialtyAreas: string[];
  profileImage?: string | null;
  profileImagePosition?: string | null;
}

export interface AdminHospitalDetail {
  hospitalid: number;
  name: string;
  address?: string | null;
  phone?: string | null;
  businessNumber?: string | null;
  tagline?: string | null;
  intro?: string | null;
  bannerImage?: string | null;
  bannerImagePosition?: string | null;
  features: string[];
  doctors: AdminDoctor[];
}

export interface DaySchedule {
  day_of_week: number;
  is_open: boolean;
  start_time?: string | null;
  end_time?: string | null;
  lunch_start?: string | null;
  lunch_end?: string | null;
}

function jsonHeaders(): Record<string, string> {
  return { "Content-Type": "application/json", ...authHeaders() };
}

export async function listHospitals(): Promise<AdminHospitalListItem[]> {
  const data = await asJson(await fetch(`${API}/admin/hospitals`, { headers: authHeaders() }));
  return data.result ?? [];
}

export async function getHospital(hid: number): Promise<AdminHospitalDetail> {
  const data = await asJson(await fetch(`${API}/admin/hospitals/${hid}`, { headers: authHeaders() }));
  return data.result;
}

export async function updateHospitalProfile(
  hid: number,
  body: Partial<Pick<AdminHospitalDetail, "name" | "address" | "phone" | "tagline" | "intro" | "bannerImage" | "bannerImagePosition" | "features">>,
): Promise<void> {
  await asJson(
    await fetch(`${API}/admin/hospitals/${hid}/profile`, { method: "PUT", headers: jsonHeaders(), body: JSON.stringify(body) }),
  );
}

export async function getHospitalHours(hid: number): Promise<DaySchedule[]> {
  const data = await asJson(await fetch(`${API}/admin/hospitals/${hid}/hours`, { headers: authHeaders() }));
  return data.schedule ?? [];
}

export async function updateHospitalHours(hid: number, schedule: DaySchedule[]): Promise<void> {
  await asJson(
    await fetch(`${API}/admin/hospitals/${hid}/hours`, { method: "PUT", headers: jsonHeaders(), body: JSON.stringify({ schedule }) }),
  );
}

export interface AdminDoctorInput {
  name: string;
  licenseNumber?: string;
  email?: string;
  specialty?: string;
  education?: string;
  bio?: string;
  specialtyAreas: string[];
  profileImage?: string;
  profileImagePosition?: string;
}

export async function addDoctor(hid: number, body: AdminDoctorInput): Promise<number> {
  const data = await asJson(
    await fetch(`${API}/admin/hospitals/${hid}/doctors`, { method: "POST", headers: jsonHeaders(), body: JSON.stringify(body) }),
  );
  return data.result?.doctorid;
}

export async function updateDoctorProfile(did: number, body: Partial<AdminDoctorInput>): Promise<void> {
  await asJson(
    await fetch(`${API}/admin/doctors/${did}/profile`, { method: "PUT", headers: jsonHeaders(), body: JSON.stringify(body) }),
  );
}

export async function setDoctorActive(did: number, is_active: boolean): Promise<void> {
  await asJson(
    await fetch(`${API}/admin/doctors/${did}/active`, { method: "PUT", headers: jsonHeaders(), body: JSON.stringify({ is_active }) }),
  );
}
