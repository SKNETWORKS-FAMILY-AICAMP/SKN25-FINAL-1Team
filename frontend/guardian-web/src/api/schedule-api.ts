import { apiClient } from "./api-client";
import type {
  AvailableScheduleSlotsResponse,
  CancelScheduleResponse,
  CheckupReservationPayload,
  CheckupReservationResponse,
  ScheduleFilter,
  ScheduleListResponse,
  UpdateSchedulePayload,
  UpdateScheduleResponse,
  ConfirmSchedulePayload,
  ConfirmScheduleResponse,
} from "../types/schedule";

export interface GetSchedulesParams {
  filter: ScheduleFilter;
  page: number;
  size: number;
}

export interface GetAvailableScheduleSlotsParams {
  date: string;
  doctorid?: number;
  hospitalid?: number;
  duration_min: number;
}

export const getSchedules = async ({
  filter,
  page,
  size,
}: GetSchedulesParams): Promise<ScheduleListResponse> => {
  const response = await apiClient.get<ScheduleListResponse>("/schedules", {
    params: {
      filter,
      page,
      size,
    },
  });

  return response.data;
};

export const getAvailableScheduleSlots = async ({
  date,
  doctorid,
  hospitalid,
  duration_min,
}: GetAvailableScheduleSlotsParams): Promise<AvailableScheduleSlotsResponse> => {
  const response = await apiClient.get<AvailableScheduleSlotsResponse>(
    "/schedules/available",
    {
      params: {
        date,
        doctorid,
        hospitalid,
        duration_min,
      },
    },
  );

  return response.data;
};

// 백엔드 recommend_slots 슬롯(원시형)
export interface RecommendSlotRaw {
  date: string;
  start_time: string;
  end_time?: string;
  doctorid?: number;
  doctor_name?: string;
}

export interface ScheduleRecommendationResponse {
  code: number;
  message: string;
  result: {
    estimated_duration_min: number;
    is_initial_visit: boolean;
    reasoning?: string;
    pre_visit_instructions?: string[];
    recommendations: {
      bucket: string;
      recommended: RecommendSlotRaw[];
      earliest: RecommendSlotRaw[];
      by_doctor: Record<string, { doctor_name?: string; slots: RecommendSlotRaw[] }>;
    };
  };
}

// 문진 완료 후 예약 추천 (duration LLM + 3모드 슬롯)
export const getScheduleRecommendation = async (body: {
  pet: unknown;
  triage: unknown;
  hospitalid?: number;
  doctorid?: number;
}): Promise<ScheduleRecommendationResponse> => {
  const response = await apiClient.post<ScheduleRecommendationResponse>(
    "/schedules/recommend",
    body,
  );

  return response.data;
};

export const reserveCheckupSchedule = async (
  payload: CheckupReservationPayload,
): Promise<CheckupReservationResponse> => {
  const response = await apiClient.post<CheckupReservationResponse>(
    "/schedules/checkup",
    payload,
  );

  return response.data;
};

export const updateSchedule = async (
  scheduleId: number,
  payload: UpdateSchedulePayload,
): Promise<UpdateScheduleResponse> => {
  const response = await apiClient.patch<UpdateScheduleResponse>(
    `/schedules/${scheduleId}`,
    payload,
  );

  return response.data;
};

export const cancelSchedule = async (
  scheduleId: number,
): Promise<CancelScheduleResponse> => {
  const response = await apiClient.delete<CancelScheduleResponse>(
    `/schedules/${scheduleId}`,
  );

  return response.data;
};

export const confirmSchedule = async (
  payload: ConfirmSchedulePayload,
): Promise<ConfirmScheduleResponse> => {
  const response = await apiClient.post<ConfirmScheduleResponse>(
    "/schedules/confirm",
    payload,
  );

  return response.data;
};
