import { apiClient } from "./client";

export interface OperatingHours {
  start_time: string;
  end_time: string;
  lunch_start: string;
  lunch_end: string;
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
