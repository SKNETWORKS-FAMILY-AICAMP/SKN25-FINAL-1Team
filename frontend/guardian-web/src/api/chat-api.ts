import { apiClient } from "./api-client";

export interface CreateChatSessionPayload {
  pet_id: number;
}

export interface ChatSessionResult {
  session_id: number;
  pet_name: string;
  profile_image?: string;
  initial_message?: string;
  initial_pills?: string[];
  initial_multi?: boolean;
}

export interface CreateChatSessionResponse {
  code: number;
  message?: string;
  result: ChatSessionResult;
}

export interface ChatSessionHistory {
  session_id: number;
  keywords: string[];
  created_at: string;
  status: string;
}

export interface ChatSessionsResponse {
  code: number;
  message?: string;
  result: ChatSessionHistory[];
}

export interface ChatSessionMessage {
  role: "user" | "assistant";
  content: string;
  image_url?: string | null;
}

export interface ChatSessionDetailResult {
  session_id: number;
  pet_id: number;
  emrid?: number | null;
  messages: ChatSessionMessage[];
  keywords: string[];
  is_complete: boolean;
  can_followup: boolean;
  booking_complete?: boolean;
  /** 문진 미완료 — 라이브 문진으로 이어서 진행 가능. */
  resumable_triage?: boolean;
  /** 문진 완료·예약 미확정 — 슬롯 선택 단계 재개 가능. */
  resumable_schedule?: boolean;
  /** 라이브 문진 재개 시 현재 노드의 추천(pill). */
  resume_quick_replies?: string[];
  created_at: string;
}

export interface ResumeScheduleResponse {
  code: number;
  message?: string;
  result?: {
    schedule_task_id: string;
    emrid: number;
    triage_info: Record<string, unknown>;
  };
}

export interface ChatSessionDetailResponse {
  code: number;
  message?: string;
  result?: ChatSessionDetailResult;
}

export interface DeleteChatSessionResponse {
  code: number;
  message?: string;
}

export interface SendChatMessagePayload {
  content: string;
  image_url?: string;
  lang?: string;
}

export interface ChatUploadPresignedUrlResponse {
  code: number;
  message?: string;
  result?: {
    presigned_url: string;
    cloudfront_url: string;
  };
}

export interface ChatUploadFileResponse {
  code: number;
  message?: string;
  result?: {
    cloudfront_url: string;
  };
}

export type ChatStreamEvent =
  | {
      type: "message";
      content: string;
    }
  | {
      type: "quick_replies";
      options: string[];
      options_display?: string[];
      multi?: boolean;
    }
  | {
      type: "message_meta";
      source: string;
      lang: string;
    }
  | {
      type: "triage_complete";
      emrid?: number;
      schedule_task_id?: string;
      data: {
        is_triage_complete: boolean;
        symptom_keywords: string[];
        urgency_level_num?: number;
        need_followup?: boolean;
        [key: string]: unknown;
      };
    }
  | {
      type: "calendar";
      [key: string]: unknown;
    }
  | {
      type: "time_slots";
      [key: string]: unknown;
    }
  | {
      type: "booking_complete";
      [key: string]: unknown;
    }
  | {
      type: "done";
    }
  | {
      type: "error";
      message?: string;
    };

interface ApiErrorResponse {
  code: number;
  message?: string;
}

export const createChatSession = async (
  payload: CreateChatSessionPayload,
): Promise<CreateChatSessionResponse> => {
  const response = await apiClient.post<CreateChatSessionResponse>(
    "/chat/sessions",
    payload,
  );
  return response.data;
};

export const getChatSessions = async (
  petId: number,
): Promise<ChatSessionsResponse> => {
  const response = await apiClient.get<ChatSessionsResponse>("/chat/sessions", {
    params: {
      pet_id: petId,
    },
  });
  return response.data;
};

export const getChatSession = async (
  sessionId: number,
): Promise<ChatSessionDetailResponse> => {
  const response = await apiClient.get<ChatSessionDetailResponse>(
    `/chat/sessions/${sessionId}`,
  );
  return response.data;
};

export const deleteChatSession = async (
  sessionId: number,
): Promise<DeleteChatSessionResponse> => {
  const response = await apiClient.delete<DeleteChatSessionResponse>(
    `/chat/sessions/${sessionId}`,
  );
  return response.data;
};

/** 문진 완료·예약 미확정 세션의 슬롯 선택 단계를 서버에서 재개. */
export const resumeSchedule = async (
  sessionId: number,
): Promise<ResumeScheduleResponse> => {
  const response = await apiClient.post<ResumeScheduleResponse>(
    `/chat/sessions/${sessionId}/resume-schedule`,
  );
  return response.data;
};

/**
 * 탭/브라우저 종료(beforeunload) 시점에 빈 세션을 삭제하기 위한 best-effort 호출.
 * sendBeacon은 Authorization 헤더를 못 실으므로 keepalive fetch를 사용한다.
 */
export const deleteChatSessionKeepalive = (
  sessionId: number,
  accessToken: string,
): void => {
  try {
    void fetch(
      `${import.meta.env.VITE_API_BASE_URL}/chat/sessions/${sessionId}`,
      {
        method: "DELETE",
        keepalive: true,
        headers: { Authorization: `Bearer ${accessToken}` },
      },
    );
  } catch {
    // best-effort — 실패해도 무시
  }
};

export interface TranslateResponse {
  code: number;
  result?: {
    translations: string[];
  };
}

/** 임의의 문구 목록을 target 언어로 일괄 번역(언어 변경 시 메시지/추천 번역). */
export const translateTexts = async (
  texts: string[],
  targetLang: string,
): Promise<string[]> => {
  const response = await apiClient.post<TranslateResponse>("/chat/translate", {
    texts,
    target_lang: targetLang,
  });
  return response.data.result?.translations ?? texts;
};

export const getChatUploadPresignedUrl = async (
  fileName: string,
  contentType: string,
  fileSize: number,
): Promise<ChatUploadPresignedUrlResponse> => {
  const response = await apiClient.get<ChatUploadPresignedUrlResponse>(
    "/chat/upload/presigned-url",
    {
      params: {
        file_name: fileName,
        content_type: contentType,
        file_size: fileSize,
      },
    },
  );
  return response.data;
};

export const uploadChatAttachment = async (
  file: File,
): Promise<ChatUploadFileResponse> => {
  const formData = new FormData();
  formData.append("file", file);

  const response = await apiClient.post<ChatUploadFileResponse>(
    "/chat/upload/file",
    formData,
    {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    },
  );
  return response.data;
};

const readStreamingResponseText = (event?: ProgressEvent) => {
  const target = event?.target as XMLHttpRequest | null;
  return typeof target?.responseText === "string" ? target.responseText : "";
};

const parseSseDataLine = (line: string): ChatStreamEvent | null => {
  const trimmedLine = line.trim();
  if (!trimmedLine.startsWith("data:")) {
    return null;
  }

  const rawData = trimmedLine.slice("data:".length).trim();
  if (!rawData) {
    return null;
  }

  try {
    return JSON.parse(rawData) as ChatStreamEvent;
  } catch {
    return {
      type: "error",
      message: "응답 데이터를 해석하지 못했습니다.",
    };
  }
};

const parseJsonErrorResponse = (responseText: string) => {
  try {
    const parsed = JSON.parse(responseText) as ApiErrorResponse;
    return parsed.message;
  } catch {
    return undefined;
  }
};

export const sendChatMessage = async (
  sessionId: number,
  payload: SendChatMessagePayload,
  onEvent: (event: ChatStreamEvent) => void,
) => {
  let receivedLength = 0;
  let pendingLine = "";
  let emittedEventCount = 0;

  const response = await apiClient.post<string>(
    `/chat/sessions/${sessionId}/messages`,
    payload,
    {
      responseType: "text",
      headers: {
        Accept: "text/event-stream",
      },
      timeout: 120_000, // OpenAI streaming max wait — axios throws after 2 min, caller catches
      onDownloadProgress: (progressEvent) => {
        const responseText = readStreamingResponseText(progressEvent.event);
        const chunk = responseText.slice(receivedLength);
        receivedLength = responseText.length;
        pendingLine += chunk;

        const lines = pendingLine.split(/\r?\n/);
        pendingLine = lines.pop() || "";

        lines.forEach((line) => {
          const event = parseSseDataLine(line);
          if (!event) {
            return;
          }

          emittedEventCount += 1;
          onEvent(event);
        });
      },
    },
  );

  const finalEvent = parseSseDataLine(pendingLine);
  if (finalEvent) {
    emittedEventCount += 1;
    onEvent(finalEvent);
  }

  if (emittedEventCount === 0 && typeof response.data === "string") {
    const errorMessage = parseJsonErrorResponse(response.data);
    if (errorMessage) {
      onEvent({
        type: "error",
        message: errorMessage,
      });
    }
  }
};
