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
    /** 보호자가 예약 변경/재예약(더 빠른 시간)을 원함 — 프론트가 슬롯 선택을 다시 띄운다. */
    rebook?: boolean;
    /** 재예약 대상 emrid(이전 문진 기반 슬롯 추천에 사용). */
    emrid?: number;
    /** 후속 행동 pill(예: '더 빠른 시간 찾기'). */
    quick_replies?: string[];
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
