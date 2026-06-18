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
    followup_id?: number;
    /** followup_filter가 만든 자연스러운 응답 — 말풍선으로 노출. */
    reply?: string;
    /** 실제로 경과로 저장됐는지(잡담/병원질문 등은 false). */
    saved?: boolean;
    /** 경과와 무관한 입력 — 저장 안 됨. */
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
