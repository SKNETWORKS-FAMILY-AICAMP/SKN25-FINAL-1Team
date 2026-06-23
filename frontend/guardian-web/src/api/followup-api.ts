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
    /** 재예약 슬롯 — 백엔드가 emrid로 계산한 추천 슬롯 + 변경할 schedule_id(세션 상태 무관). */
    rebook_slots?: {
      schedule_id: number;
      estimated_duration_min?: number;
      recommendations?: Record<string, unknown>;
    } | null;
    /** 보호자가 예약 취소를 원함 — 프론트가 확인 후 cancel_schedule_id로 취소. */
    cancel?: boolean;
    cancel_schedule_id?: number | null;
    /** 예약 내역 보기 — 프론트가 예약 목록 카드를 렌더(+ 예약내역 탭 안내). */
    show_schedules?: boolean;
    schedules?: {
      schedule_id: number;
      when?: string | null;
      pet_name?: string | null;
      doctor_name?: string | null;
      hospital_name?: string | null;
      status?: string | null;
    }[];
    /** '문진 작성 후 예약하기' — 프론트가 챗 입력을 문진 모드로 전환. */
    start_triage?: boolean;
    /** 내원 전 준비사항 다시 보기 — 프론트가 준비사항 카드를 다시 렌더. */
    show_prep?: boolean;
    prep_instructions?: string[];
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
