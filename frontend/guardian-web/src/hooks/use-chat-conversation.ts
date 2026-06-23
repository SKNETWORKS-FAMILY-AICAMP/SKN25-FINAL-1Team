import {
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";

import {
  sendChatMessage,
  type ChatSessionResult,
  type ChatStreamEvent,
} from "../api/chat-api";
import { useTranslation } from "../i18n/language-context";
import { primeTranslationCache } from "../i18n/use-dynamic-translation";
import type { PendingAttachment } from "./use-chat-upload";

/** 슬롯 카드에 표시할 단일 예약 가능 시간 */
export interface SlotOption {
  label: string; // 선택 라우팅용 ("5월 20일 16:00")
  date?: string; // "2026-06-09"
  time?: string; // "09:00"
  durationMin?: number;
  doctorid?: number; // 슬롯 담당 원장 (백엔드 슬롯에 포함됨)
  doctorName?: string; // 원장 이름 (표시·그룹핑용)
  monthDay?: string; // legacy fallback: "5월 20일"
  weekday?: string; // legacy fallback: "월"
  timeText?: string; // legacy fallback: "오후 4:00"
  durationText?: string; // legacy fallback: "1시간 30분"
}

/** 챗봇 말풍선 대신 렌더링하는 구조화 카드 */
export type ChatCard =
  // slots: 기본 표시용 slots + (있으면) 3모드 미리계산본 — 칩 전환 시 재요청 없음
  | {
      kind: "slots";
      slots: SlotOption[];
      recommended?: SlotOption[]; // 추천시간(응급도 분배)
      earliest?: SlotOption[]; // 가장 가까운 시간
      byDoctor?: { doctorid: number; doctorName?: string; slots: SlotOption[] }[]; // 수의사별
    }
  | {
      kind: "confirmation";
      petName: string;
      date?: string;
      time?: string;
      durationMin?: number;
      dateText?: string; // legacy fallback: "2024년 5월 20일 (월) 오후 4:00"
      durationText?: string; // legacy fallback: "1시간 30분"
      hospitalName?: string;
    }
  | { kind: "instructions"; items: string[] }
  // 예약 내역 보기 — 다가오는 확정 예약 요약 카드(+ 예약내역 탭 이동 pill).
  | {
      kind: "schedules";
      items: {
        schedule_id: number;
        when?: string | null;
        petName?: string | null;
        doctorName?: string | null;
        hospitalName?: string | null;
        status?: string | null;
      }[];
    };

export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  /** Pill 번역본처럼 UI에 표시할 별도 텍스트. 있으면 content 대신 버블에 노출. */
  displayContent?: string;
  attachmentUrl?: string;
  attachmentType?: string;
  card?: ChatCard;
  /** content가 한국어가 아닐 때 보관하는 한국어 원문 — 이후 언어 전환 시 재번역 원본. */
  sourceContent?: string;
  /** content가 이미 어떤 언어로 렌더링됐는지(백엔드 선번역 스트리밍 결과). */
  contentLang?: string;
  /** 생성 시점 문자열 대신 렌더 시점 언어로 다시 표시할 로컬 UI 문구 키. */
  i18nKey?: string;
  i18nVars?: Record<string, string | number>;
  pipelineKey?: "checking-slots" | "slots-result" | "slot-error" | "booking-status" | "followup-restore" | "followup-loading";
  /** 응답 대기 중 진행 단계 — 빈 말풍선 로딩 문구 분기용. */
  statusPhase?: "image_analysis" | "generating" | "searching";
}

interface UseChatConversationParams {
  pendingAttachment: PendingAttachment | null;
  setPendingAttachment: Dispatch<SetStateAction<PendingAttachment | null>>;
  clearPendingAttachment: () => void;
  isUploadingAttachment: boolean;
  setErrorMessage: (message: string) => void;
  getErrorMessage: (error: unknown, fallbackMessage: string) => string;
  onTriageComplete?: (
    sessionId: number,
    keywords: string[],
    collectedInfo: Record<string, unknown>,
    emrid?: number,
    scheduleTaskId?: string,
  ) => void;
  /** 문진 완료 시 생성된 대화 요약 제목 — 채팅 목록 제목 실시간 갱신용. */
  onTitleUpdate?: (sessionId: number, title: string) => void;
}

export const useChatConversation = ({
  pendingAttachment,
  setPendingAttachment,
  clearPendingAttachment,
  isUploadingAttachment,
  setErrorMessage,
  getErrorMessage,
  onTriageComplete,
  onTitleUpdate,
}: UseChatConversationParams) => {
  const { t, lang } = useTranslation();
  const [session, setSession] = useState<ChatSessionResult | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [quickReplies, setQuickReplies] = useState<string[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const activeSessionIdRef = useRef<number | null>(null);
  const activeRequestIdRef = useRef(0);

  useEffect(() => {
    activeSessionIdRef.current = session?.session_id ?? null;
  }, [session?.session_id]);

  const isCurrentStream = (sessionId: number, requestId: number) =>
    activeSessionIdRef.current === sessionId && activeRequestIdRef.current === requestId;

  const resetConversationState = () => {
    activeRequestIdRef.current += 1;
    setSession(null);
    setMessages([]);
    setQuickReplies([]);
    clearPendingAttachment();
    setIsStreaming(false);
  };

  const applyStreamEvent = (
    event: ChatStreamEvent,
    assistantMessageId: number,
    requestSessionId: number,
    requestId: number,
  ) => {
    if (!isCurrentStream(requestSessionId, requestId)) return;

    if (event.type === "message") {
      setMessages((currentMessages) =>
        currentMessages.map((message) =>
          message.id === assistantMessageId
            ? {
                ...message,
                content: `${message.content}${event.content}`,
              }
            : message,
        ),
      );
      return;
    }

    // 진행 단계 알림 → 빈 말풍선의 로딩 문구 분기에 사용
    if (event.type === "status") {
      setMessages((currentMessages) =>
        currentMessages.map((message) =>
          message.id === assistantMessageId
            ? { ...message, statusPhase: event.phase }
            : message,
        ),
      );
      return;
    }

    if (event.type === "quick_replies") {
      // 라우팅용 한국어 원문을 저장하고, 표시용 번역본으로 캐시를 미리 채워 즉시 표시.
      if (event.options_display && event.options_display.length === event.options.length) {
        const entries: Record<string, string> = {};
        event.options.forEach((option, index) => {
          entries[option] = event.options_display![index];
        });
        primeTranslationCache(lang, entries);
      }
      setQuickReplies(event.options);
      return;
    }

    if (event.type === "message_meta") {
      // 스트리밍된 본문이 어떤 언어인지 + 한국어 원문을 메시지에 보관.
      setMessages((currentMessages) =>
        currentMessages.map((message) =>
          message.id === assistantMessageId
            ? { ...message, sourceContent: event.source, contentLang: event.lang }
            : message,
        ),
      );
      return;
    }

    if (event.type === "chat_title") {
      if (onTitleUpdate && event.title) {
        onTitleUpdate(requestSessionId, event.title);
      }
      return;
    }

    if (event.type === "triage_complete") {
      const keywords = event.data?.symptom_keywords ?? [];
      if (onTriageComplete) {
        onTriageComplete(
          requestSessionId,
          keywords,
          event.data,
          event.emrid,
          event.schedule_task_id,
        );
      }
      return;
    }

    if (event.type === "done") {
      setIsStreaming(false);
      return;
    }

    if (event.type === "error") {
      setErrorMessage(event.message || t("chatbot.responseLoadError"));
      setIsStreaming(false);
    }
  };

  const handleSendMessage = async (content: string, displayContent?: string) => {
    const trimmedContent = content.trim();
    if (
      !session ||
      (!trimmedContent && !pendingAttachment) ||
      isStreaming ||
      isUploadingAttachment
    ) {
      return;
    }

    const userMessageId = Date.now();
    const assistantMessageId = userMessageId + 1;
    const attachmentToSend = pendingAttachment;
    const requestSessionId = session.session_id;
    const requestId = activeRequestIdRef.current + 1;
    activeRequestIdRef.current = requestId;

    setMessages((currentMessages) => [
      ...currentMessages,
      {
        id: userMessageId,
        role: "user",
        content: trimmedContent || t("chatbot.attachmentSent"),
        displayContent: displayContent?.trim() || undefined,
        attachmentUrl: attachmentToSend?.previewUrl,
        attachmentType: attachmentToSend?.contentType,
      },
      {
        id: assistantMessageId,
        role: "assistant",
        content: "",
      },
    ]);
    setPendingAttachment(null);
    setQuickReplies([]);
    setIsStreaming(true);
    setErrorMessage("");

    let caughtError = false;
    try {
      await sendChatMessage(
        requestSessionId,
        {
          content: trimmedContent,
          image_url: attachmentToSend?.cloudfrontUrl,
          lang,
        },
        (event) => applyStreamEvent(event, assistantMessageId, requestSessionId, requestId),
      );
    } catch (error) {
      if (!isCurrentStream(requestSessionId, requestId)) return;
      caughtError = true;
      setErrorMessage(getErrorMessage(error, t("chatbot.sendFailed")));
      setMessages((currentMessages) =>
        currentMessages.filter((message) => message.id !== assistantMessageId),
      );
    } finally {
      if (!isCurrentStream(requestSessionId, requestId)) return;
      if (!caughtError) {
        // 서버가 "done" 없이 연결을 닫거나 timeout 발생 시 빈 말풍선 대신 안내 메시지 표시
        setMessages((currentMessages) =>
          currentMessages.map((message) =>
            message.id === assistantMessageId && message.content.trim() === ""
              ? { ...message, content: t("chatbot.responseDelayed") }
              : message,
          ),
        );
      }
      setIsStreaming(false);
    }
  };

  return {
    session,
    setSession,
    messages,
    setMessages,
    quickReplies,
    setQuickReplies,
    isStreaming,
    setIsStreaming,
    resetConversationState,
    handleSendMessage,
  };
};
