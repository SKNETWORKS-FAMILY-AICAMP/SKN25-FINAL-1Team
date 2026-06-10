import { apiClient } from "./client";
import type { EmrResult, QueuePatient } from "../types/emr";

// ──────────────────────────────────────────────
// Response types
// ──────────────────────────────────────────────

export interface EmrQueueResponse {
  code: number;
  result: {
    waiting: QueuePatient[];
    completed: QueuePatient[];
  };
}

export interface DoctorInfo {
  doctorid: number;
  doctor_name: string;
  loginid: string;
}

export interface EmrDetailResponse {
  code: number;
  result: EmrResult;
}

export interface TriageResultResponse {
  code: number;
  result: {
    id: number;
    emrid: number;
    urgency_level: string;
    urgency_level_num: number;
    vtl_basis: string | null;
    red_flags: string[] | null;
    chief_complaint: string | null;
    symptom_onset: string | null;
    symptom_keywords: string[] | null;
    suspected_diseases: string[] | null;
    symptom_summary: string | null;
    recommended_action: string | null;
    need_photo: boolean | null;
    created_at: string | null;
  } | null;
}

export interface ReportResultResponse {
  code: number;
  result: {
    reportid: number;
    emrid: number;
    scheduleid: number | null;
    medical_analysis: string | null;
    ai_draft_json: Record<string, unknown> | null;
    status: string;
  } | null;
}

export interface ValidationResultResponse {
  code: number;
  result: {
    id: number;
    emrid: number;
    scheduleid: number | null;
    overall: string;
    checks: Record<string, unknown> | null;
    completeness_score: number | null;
    accuracy_score: number | null;
    consistency_score: number | null;
    summary: string | null;
    created_at: string | null;
  } | null;
}

export interface FollowupItem {
  followup_id: number;
  emrid: number;
  images: string[];
  message: string | null;
  ai_summary?: string | null;
  emergency_alert?: boolean | null;
  created_at: string | null;
}

// ──────────────────────────────────────────────
// 1순위: EMR Queue
// ──────────────────────────────────────────────

export async function fetchEmrQueue(params: {
  accessToken: string;
  date?: string;
  doctorId?: number;
}): Promise<{ waiting: QueuePatient[]; completed: QueuePatient[] }> {
  const { data } = await apiClient.get<EmrQueueResponse>("/doctor/emr/queue", {
    headers: { Authorization: `Bearer ${params.accessToken}` },
    params: {
      ...(params.date ? { date: params.date } : {}),
      ...(params.doctorId !== undefined ? { doctor_id: params.doctorId } : {}),
    },
  });
  return data.result;
}

export async function fetchHospitalDoctors(accessToken: string): Promise<DoctorInfo[]> {
  const { data } = await apiClient.get<{ code: number; result: DoctorInfo[] }>(
    "/doctor/auth/hospital/doctors",
    { headers: { Authorization: `Bearer ${accessToken}` } }
  );
  return data.result;
}

export async function fetchEmrDetail(params: {
  accessToken: string;
  scheduleId: number;
}): Promise<EmrResult> {
  const { data } = await apiClient.get<EmrDetailResponse>(
    `/doctor/emr/queue/${params.scheduleId}`,
    { headers: { Authorization: `Bearer ${params.accessToken}` } }
  );
  return data.result;
}

// ──────────────────────────────────────────────
// 3순위: AI SOAP 초안
// ──────────────────────────────────────────────

export async function fetchEmrReport(params: {
  accessToken: string;
  scheduleId: number;
}): Promise<ReportResultResponse["result"]> {
  const { data } = await apiClient.get<ReportResultResponse>(
    `/doctor/emr/${params.scheduleId}/report`,
    { headers: { Authorization: `Bearer ${params.accessToken}` } }
  );
  return data.result;
}

// ──────────────────────────────────────────────
// 4순위: 트리아지 결과
// ──────────────────────────────────────────────

export async function fetchEmrTriage(params: {
  accessToken: string;
  scheduleId: number;
}): Promise<TriageResultResponse["result"]> {
  const { data } = await apiClient.get<TriageResultResponse>(
    `/doctor/emr/${params.scheduleId}/triage`,
    { headers: { Authorization: `Bearer ${params.accessToken}` } }
  );
  return data.result;
}

// ──────────────────────────────────────────────
// 5순위: 검증 결과
// ──────────────────────────────────────────────

export async function fetchEmrValidation(params: {
  accessToken: string;
  scheduleId: number;
}): Promise<ValidationResultResponse["result"]> {
  const { data } = await apiClient.get<ValidationResultResponse>(
    `/doctor/emr/${params.scheduleId}/validation`,
    { headers: { Authorization: `Bearer ${params.accessToken}` } }
  );
  return data.result;
}

// ──────────────────────────────────────────────
// 6순위: 경과 모니터링 (수의사 뷰)
// ──────────────────────────────────────────────

export interface AutoPrescriptionItem {
  drug_name: string;
  form: string;
  dosage: string;
  frequency: string;
  duration_days: number;
}

export async function generateAutoPrescription(params: {
  accessToken: string;
  scheduleId: number;
  doctorNotes?: string;
}): Promise<AutoPrescriptionItem[]> {
  const { data } = await apiClient.post<{ code: number; result: AutoPrescriptionItem[] }>(
    `/doctor/emr/${params.scheduleId}/auto-prescription`,
    { doctor_notes: params.doctorNotes ?? "" },
    { headers: { Authorization: `Bearer ${params.accessToken}` } }
  );
  return data.result;
}

// ──────────────────────────────────────────────
// 진료 사진 업로드 (x-ray 등) → S3 업로드 후 읽기용 CloudFront URL 반환
// ──────────────────────────────────────────────

export async function uploadEmrFile(params: {
  accessToken: string;
  file: File;
}): Promise<{ cloudfront_url: string }> {
  const formData = new FormData();
  formData.append("file", params.file);
  const { data } = await apiClient.post<{ code: number; result: { cloudfront_url: string } }>(
    "/doctor/emr/upload/file",
    formData,
    {
      headers: {
        Authorization: `Bearer ${params.accessToken}`,
        "Content-Type": "multipart/form-data",
      },
    }
  );
  return data.result;
}

export async function fetchDoctorFollowup(params: {
  accessToken: string;
  emrid: number;
}): Promise<FollowupItem[]> {
  const { data } = await apiClient.get<{ code: number; result: FollowupItem[] }>(
    `/doctor/emr/followup/${params.emrid}`,
    { headers: { Authorization: `Bearer ${params.accessToken}` } }
  );
  return data.result;
}
