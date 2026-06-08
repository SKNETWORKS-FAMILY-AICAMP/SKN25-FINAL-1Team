import {
  useState,
  type Dispatch,
  type FormEvent,
  type SetStateAction,
} from "react";

import {
  sendChatMessage,
  type ChatSessionResult,
  type ChatStreamEvent,
} from "../api/chat-api";
import { useTranslation } from "../i18n/language-context";
import type { PendingAttachment } from "./use-chat-upload";

/** 슬롯 카드에 표시할 단일 예약 가능 시간 */
export interface SlotOption {
  label: string; // 선택 라우팅용 ("5월 20일 16:00")
  monthDay: string; // "5월 20일"
  weekday: string; // "월"
  timeText: string; // "오후 4:00"
  durationText: string; // "1시간 30분"
}

/** 챗봇 말풍선 대신 렌더링하는 구조화 카드 */
export type ChatCard =
  | { kind: "slots"; slots: SlotOption[] }
  | {
      kind: "confirmation";
      petName: string;
      dateText: string; // "2024년 5월 20일 (월) 오후 4:00"
      durationText: string; // "1시간 30분"
      hospitalName?: string;
    }
  | { kind: "instructions"; items: string[] };

export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  attachmentUrl?: string;
  attachmentType?: string;
  card?: ChatCard;
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
}

export const useChatConversation = ({
  pendingAttachment,
  setPendingAttachment,
  clearPendingAttachment,
  isUploadingAttachment,
  setErrorMessage,
  getErrorMessage,
  onTriageComplete,
}: UseChatConversationParams) => {
  const { t } = useTranslation();
  const [session, setSession] = useState<ChatSessionResult | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [messageInput, setMessageInput] = useState("");
  const [quickReplies, setQuickReplies] = useState<string[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);

  const resetConversationState = () => {
    setSession(null);
    setMessages([]);
    setQuickReplies([]);
    setMessageInput("");
    clearPendingAttachment();
    setIsStreaming(false);
  };

  const applyStreamEvent = (
    event: ChatStreamEvent,
    assistantMessageId: number,
  ) => {
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

    if (event.type === "quick_replies") {
      setQuickReplies(event.options);
      return;
    }

    if (event.type === "triage_complete") {
      const keywords = event.data?.symptom_keywords ?? [];
      if (session && onTriageComplete) {
        onTriageComplete(
          session.session_id,
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

  const handleSendMessage = async (content: string) => {
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

    setMessages((currentMessages) => [
      ...currentMessages,
      {
        id: userMessageId,
        role: "user",
        content: trimmedContent || t("chatbot.attachmentSent"),
        attachmentUrl: attachmentToSend?.previewUrl,
        attachmentType: attachmentToSend?.contentType,
      },
      {
        id: assistantMessageId,
        role: "assistant",
        content: "",
      },
    ]);
    setMessageInput("");
    setPendingAttachment(null);
    setQuickReplies([]);
    setIsStreaming(true);
    setErrorMessage("");

    let caughtError = false;
    try {
      await sendChatMessage(
        session.session_id,
        {
          content: trimmedContent,
          image_url: attachmentToSend?.cloudfrontUrl,
        },
        (event) => applyStreamEvent(event, assistantMessageId),
      );
    } catch (error) {
      caughtError = true;
      setErrorMessage(getErrorMessage(error, t("chatbot.sendFailed")));
      setMessages((currentMessages) =>
        currentMessages.filter((message) => message.id !== assistantMessageId),
      );
    } finally {
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

  const handleSubmitMessage = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    handleSendMessage(messageInput);
  };

  return {
    session,
    setSession,
    messages,
    setMessages,
    messageInput,
    setMessageInput,
    quickReplies,
    setQuickReplies,
    isStreaming,
    setIsStreaming,
    resetConversationState,
    handleSendMessage,
    handleSubmitMessage,
  };
};
