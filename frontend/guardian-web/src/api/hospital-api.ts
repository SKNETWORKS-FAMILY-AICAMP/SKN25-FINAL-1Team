import { apiClient } from "./api-client";
import type { Hospital } from "./hospital-mock";

// 응답 필드명은 백엔드 hospital 스키마와 동일(프론트 Hospital/HospitalDoctor와 1:1).

export interface MyHospital {
  hospitalid: number;
  name: string;
  is_primary: boolean;
  is_active?: boolean; // 폐업 병원이면 false
}

export const getMyHospitals = async (): Promise<MyHospital[]> => {
  const res = await apiClient.get<{ result: MyHospital[] }>("/guardians/me/hospitals");
  return res.data.result ?? [];
};

export const getHospitalDetail = async (hospitalid: number): Promise<Hospital> => {
  const res = await apiClient.get<{ result: Hospital }>(`/hospitals/${hospitalid}`);
  return res.data.result;
};

export interface HospitalSearchItem {
  hospitalid: number;
  name: string;
  address?: string;
}

export const searchHospitals = async (query?: string): Promise<HospitalSearchItem[]> => {
  const res = await apiClient.get<{ result: HospitalSearchItem[] }>("/hospitals", {
    params: { query },
  });
  return res.data.result ?? [];
};

export const addMyHospital = async (hospitalid: number): Promise<void> => {
  await apiClient.post("/guardians/me/hospitals", { hospitalid });
};

export const removeMyHospital = async (hospitalid: number): Promise<void> => {
  await apiClient.delete(`/guardians/me/hospitals/${hospitalid}`);
};

export const setPrimaryHospital = async (hospitalid: number): Promise<void> => {
  await apiClient.put(`/guardians/me/hospitals/${hospitalid}/primary`);
};
