import { apiClient } from "./client";

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
