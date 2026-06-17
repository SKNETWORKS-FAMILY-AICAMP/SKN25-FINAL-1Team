import { API_BASE_URL, apiClient } from "./client";

export interface HospitalProfile {
  hospitalid: number;
  name: string;
  address: string;
  phone: string;
  tagline: string | null;
  intro: string | null;
  bannerImage: string | null;
  bannerImagePosition: string | null;
  features: string[];
  doctors: DoctorProfile[];
}

export interface DoctorProfile {
  doctorid: number;
  name: string;
  licenseNumber: string | null;
  specialty: string | null;
  education: string | null;
  bio: string | null;
  specialtyAreas: string[];
  profileImage: string | null;
  profileImagePosition: string | null;
}

export interface HospitalProfileUpdate {
  name?: string;
  address?: string;
  phone?: string;
  tagline?: string;
  intro?: string;
  bannerImage?: string;
  bannerImagePosition?: string;
  features?: string[];
}

export interface DoctorProfileUpdate {
  name?: string;
  licenseNumber?: string;
  specialty?: string;
  education?: string;
  bio?: string;
  specialtyAreas?: string[];
  profileImage?: string;
  profileImagePosition?: string;
}

export async function fetchHospitalProfile(accessToken: string): Promise<HospitalProfile> {
  const { data } = await apiClient.get<{ result: HospitalProfile }>(
    "/doctor/hospital/profile",
    { headers: { Authorization: `Bearer ${accessToken}` } }
  );
  return data.result;
}

export async function updateHospitalProfile(
  accessToken: string,
  update: HospitalProfileUpdate
): Promise<void> {
  await apiClient.put(
    "/doctor/hospital/profile",
    update,
    { headers: { Authorization: `Bearer ${accessToken}` } }
  );
}

export async function deleteDoctor(accessToken: string, did: number): Promise<void> {
  await apiClient.delete(
    `/doctor/hospital/doctors/${did}`,
    { headers: { Authorization: `Bearer ${accessToken}` } }
  );
}

export async function createDoctor(accessToken: string, name: string): Promise<DoctorProfile> {
  const { data } = await apiClient.post<{ result: DoctorProfile }>(
    "/doctor/hospital/doctors",
    { name },
    { headers: { Authorization: `Bearer ${accessToken}` } }
  );
  return data.result;
}

export async function fetchDoctors(accessToken: string): Promise<DoctorProfile[]> {
  const { data } = await apiClient.get<{ result: DoctorProfile[] }>(
    "/doctor/hospital/doctors",
    { headers: { Authorization: `Bearer ${accessToken}` } }
  );
  return data.result;
}

export async function updateDoctorProfile(
  accessToken: string,
  did: number,
  update: DoctorProfileUpdate
): Promise<void> {
  await apiClient.put(
    `/doctor/hospital/doctors/${did}/profile`,
    update,
    { headers: { Authorization: `Bearer ${accessToken}` } }
  );
}

export async function uploadHospitalFile(
  accessToken: string,
  file: File,
  prefix: "hospital" | "doctor"
): Promise<string> {
  const q = new URLSearchParams({
    file_name: file.name,
    content_type: file.type || "application/octet-stream",
    prefix,
  });
  const { data } = await apiClient.get<{ result: { presigned_url: string; cloudfront_url: string } }>(
    `/doctor/hospital/uploads/presigned-url?${q}`,
    { headers: { Authorization: `Bearer ${accessToken}` } }
  );
  const { presigned_url, cloudfront_url } = data.result;

  const put = await fetch(presigned_url, {
    method: "PUT",
    headers: { "Content-Type": file.type },
    body: file,
  });
  if (!put.ok) {
    const isLocalFallback = String(cloudfront_url).startsWith(`${API_BASE_URL}/`);
    if (!isLocalFallback) throw new Error("파일 업로드에 실패했습니다.");
  }
  return cloudfront_url;
}
