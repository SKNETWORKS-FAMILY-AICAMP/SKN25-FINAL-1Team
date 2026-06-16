import axios, { type AxiosError } from "axios";
import { API_BASE_URL, apiClient } from "./client";

export interface OperatingHours {
  start_time: string;
  end_time: string;
  lunch_start: string;
  lunch_end: string;
}

export interface DaySchedule {
  day_of_week: number; // 0=월 ... 6=일
  is_open: boolean;
  start_time: string | null;
  end_time: string | null;
  lunch_start: string | null;
  lunch_end: string | null;
}

export interface AddClosedDateResponse {
  success: boolean;
  has_existing_reservations: boolean;
  reservation_count: number;
}

type SettingsApiErrorResponse = {
  message?: string;
  detail?: string;
  error?: string;
};

export function getSettingsApiErrorMessage(err: unknown, fallbackMessage: string) {
  if (!axios.isAxiosError(err)) {
    return err instanceof Error ? err.message : fallbackMessage;
  }

  const axiosError = err as AxiosError<SettingsApiErrorResponse>;

  if (!axiosError.response) {
    return `백엔드 서버에 연결할 수 없습니다. ${API_BASE_URL} 서버가 실행 중인지 확인해주세요.`;
  }

  return (
    axiosError.response.data?.message ??
    axiosError.response.data?.detail ??
    axiosError.response.data?.error ??
    fallbackMessage
  );
}

export async function fetchOperatingHours(accessToken: string): Promise<OperatingHours> {
  const { data } = await apiClient.get<OperatingHours>(
    "/doctor/settings/operating-hours",
    { headers: { Authorization: `Bearer ${accessToken}` } }
  );
  return data;
}

export async function updateOperatingHours(
  accessToken: string,
  hours: OperatingHours
): Promise<OperatingHours> {
  const { data } = await apiClient.put<OperatingHours>(
    "/doctor/settings/operating-hours",
    hours,
    { headers: { Authorization: `Bearer ${accessToken}` } }
  );
  return data;
}

export async function fetchWeeklySchedule(accessToken: string): Promise<DaySchedule[]> {
  const { data } = await apiClient.get<{ schedule: DaySchedule[] }>(
    "/doctor/settings/weekly-schedule",
    { headers: { Authorization: `Bearer ${accessToken}` } }
  );
  return data.schedule;
}

export async function updateWeeklySchedule(
  accessToken: string,
  schedule: DaySchedule[]
): Promise<DaySchedule[]> {
  const { data } = await apiClient.put<{ schedule: DaySchedule[] }>(
    "/doctor/settings/weekly-schedule",
    { schedule },
    { headers: { Authorization: `Bearer ${accessToken}` } }
  );
  return data.schedule;
}

export async function fetchVetWeeklySchedule(
  accessToken: string,
  doctorid: number
): Promise<DaySchedule[]> {
  const { data } = await apiClient.get<{ schedule: DaySchedule[] }>(
    `/doctor/settings/weekly-schedule?doctorid=${doctorid}`,
    { headers: { Authorization: `Bearer ${accessToken}` } }
  );
  return data.schedule;
}

export async function updateVetWeeklySchedule(
  accessToken: string,
  doctorid: number,
  schedule: DaySchedule[]
): Promise<DaySchedule[]> {
  const { data } = await apiClient.put<{ schedule: DaySchedule[] }>(
    `/doctor/settings/weekly-schedule?doctorid=${doctorid}`,
    { schedule },
    { headers: { Authorization: `Bearer ${accessToken}` } }
  );
  return data.schedule;
}

export async function fetchClosedDates(accessToken: string): Promise<string[]> {
  const { data } = await apiClient.get<{ dates: string[] }>(
    "/doctor/settings/closed-dates",
    { headers: { Authorization: `Bearer ${accessToken}` } }
  );
  return data.dates;
}

export async function addClosedDate(
  accessToken: string,
  date: string
): Promise<AddClosedDateResponse> {
  const { data } = await apiClient.post<AddClosedDateResponse>(
    "/doctor/settings/closed-dates",
    { date },
    { headers: { Authorization: `Bearer ${accessToken}` } }
  );
  return data;
}

export async function removeClosedDate(
  accessToken: string,
  date: string
): Promise<void> {
  await apiClient.delete(`/doctor/settings/closed-dates/${date}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}
