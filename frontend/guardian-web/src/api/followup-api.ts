import { apiClient } from "./api-client";

export interface CreateFollowupPayload {
  emrid: number;
  images: string[];
  message?: string;
}

export interface FollowupResponse {
  code: number;
  message: string;
  result: {
    followup_id: number;
    /** 경과와 무관한 입력 — 이때만 안내 응답을 띄운다. */
    offtopic?: boolean;
    followup_recommended?: boolean;
    guardian_message?: string;
    recommended_actions?: string[];
  };
}

export const createFollowup = async (
  payload: CreateFollowupPayload,
): Promise<FollowupResponse> => {
  const response = await apiClient.post<FollowupResponse>("/followup", payload);
  return response.data;
};
