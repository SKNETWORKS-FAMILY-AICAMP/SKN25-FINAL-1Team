import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type Dispatch,
  type MutableRefObject,
  type SetStateAction,
} from "react";

import {
  createChatSession,
  deleteChatSession,
  getChatSession,
  getChatSessions,
  type ChatSessionHistory,
  type ChatSessionResult,
} from "../api/chat-api";
import { useTranslation } from "../i18n/language-context";
import type { Pet } from "../api/pets-api";
import type { ChatMessage } from "./use-chat-conversation";

/** 현재 화면에 떠 있는 라이브 세션의 식별자 + 보호자가 한마디라도 했는지 여부. */
export interface LiveSessionInfo {
  id: number;
  hasUserMessage: boolean;
}

interface UseChatSessionsParams {
  selectedPet?: Pet;
  resetConversationState: () => void;
  setSession: Dispatch<SetStateAction<ChatSessionResult | null>>;
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>;
  setErrorMessage: (message: string) => void;
  getErrorMessage: (error: unknown, fallbackMessage: string) => string;
  getProfileImage: (pet: Pet) => string;
  onFollowupRestore?: (emrid: number) => void;
  /** 경과보고 마감(진료 시작 시간 경과) 세션 — 마감 안내 표시. */
  onFollowupClosed?: (emrid: number) => void;
  /** 일반(followup 미활성) 예약 완료 세션 — '상담 완료' 안내 표시. */
  onBookingComplete?: (emrid: number) => void;
  /** 문진 미완료 세션을 라이브 문진으로 재개(req4). */
  onResumeTriage?: (params: {
    sessionId: number;
    messages: ChatMessage[];
    quickReplies: string[];
  }) => void;
  /** 문진 완료·예약 미확정 세션의 슬롯 선택 단계 재개(req4). */
  onResumeSchedule?: (params: { sessionId: number; emrid: number }) => void;
  /** 보호자가 한마디도 안 한 빈 세션을 떠날 때 삭제하기 위한 추적 ref. */
  liveSessionRef: MutableRefObject<LiveSessionInfo | null>;
}

export const useChatSessions = ({
  selectedPet,
  resetConversationState,
  setSession,
  setMessages,
  setErrorMessage,
  getErrorMessage,
  getProfileImage,
  onFollowupRestore,
  onFollowupClosed,
  onBookingComplete,
  onResumeTriage,
  onResumeSchedule,
  liveSessionRef,
}: UseChatSessionsParams) => {
  const { t } = useTranslation();
  const [chatHistories, setChatHistories] = useState<ChatSessionHistory[]>([]);
  const [selectedHistoryId, setSelectedHistoryId] = useState<number | null>(
    null,
  );
  const [isLoadingHistories, setIsLoadingHistories] = useState(false);
  const [isLoadingHistoryMessages, setIsLoadingHistoryMessages] =
    useState(false);
  const [creatingPetId, setCreatingPetId] = useState<number | null>(null);

  const selectedHistory = useMemo(
    () =>
      chatHistories.find((history) => history.session_id === selectedHistoryId),
    [chatHistories, selectedHistoryId],
  );

  const refreshChatHistories = async (petId: number) => {
    try {
      const response = await getChatSessions(petId);
      if (response.code === 200) {
        setChatHistories(response.result);
      }
    } catch {
      // 갱신 실패는 무시 — 이미 표시 중인 목록 유지
    }
  };

  useEffect(() => {
    if (!selectedPet) {
      setChatHistories([]);
      return;
    }

    let isMounted = true;

    const loadChatHistories = async () => {
      try {
        setIsLoadingHistories(true);
        setErrorMessage("");

        const response = await getChatSessions(selectedPet.pet_id);
        if (!isMounted) {
          return;
        }

        if (response.code !== 200) {
          setErrorMessage(response.message || t("chatbot.historyLoadError"));
          setChatHistories([]);
          return;
        }

        setChatHistories(response.result);
      } catch (error) {
        if (!isMounted) {
          return;
        }

        setErrorMessage(
          getErrorMessage(error, t("chatbot.historyLoadError")),
        );
        setChatHistories([]);
      } finally {
        if (isMounted) {
          setIsLoadingHistories(false);
        }
      }
    };

    loadChatHistories();

    return () => {
      isMounted = false;
    };
  }, [getErrorMessage, selectedPet, setErrorMessage, t]);

  // 보호자가 한마디도 안 한 채로 떠나는 라이브 세션을 삭제한다(req1).
  // 새 세션 생성 / 다른 기록 선택 / 반려동물 변경 / 페이지 이탈 시 호출.
  const discardEmptyLiveSession = useCallback(() => {
    const live = liveSessionRef.current;
    if (!live || live.hasUserMessage) {
      return;
    }
    liveSessionRef.current = null;
    const emptyId = live.id;
    setChatHistories((current) =>
      current.filter((history) => history.session_id !== emptyId),
    );
    void deleteChatSession(emptyId).catch(() => {
      // best-effort — 삭제 실패는 무시(다음 진입 시 다시 정리됨)
    });
  }, [liveSessionRef]);

  const resetSessionStateForPetChange = () => {
    discardEmptyLiveSession();
    setSelectedHistoryId(null);
    setChatHistories([]);
    setIsLoadingHistoryMessages(false);
    resetConversationState();
    setErrorMessage("");
  };

  const handleCreateSession = async () => {
    if (!selectedPet || creatingPetId !== null) {
      return;
    }
    discardEmptyLiveSession();

    try {
      setCreatingPetId(selectedPet.pet_id);
      setSelectedHistoryId(null);
      resetConversationState();
      setErrorMessage("");

      const response = await createChatSession({ pet_id: selectedPet.pet_id });
      if (response.code !== 201) {
        setErrorMessage(response.message || t("chatbot.sessionStartError"));
        return;
      }

      const petName = response.result.pet_name || selectedPet.petname;
      const today = new Date().toISOString().slice(0, 10);
      setSelectedHistoryId(response.result.session_id);
      setChatHistories((currentHistories) => [
        {
          session_id: response.result.session_id,
          keywords: [],
          created_at: today,
          status: t("chatbot.statusConsulting"),
        },
        ...currentHistories.filter((history) => history.session_id !== response.result.session_id),
      ]);
      setSession({
        ...response.result,
        pet_name: petName,
        profile_image:
          response.result.profile_image || getProfileImage(selectedPet),
      });
      setMessages([]);
    } catch (error) {
      setErrorMessage(
        getErrorMessage(error, t("chatbot.sessionStartError")),
      );
    } finally {
      setCreatingPetId(null);
    }
  };

  const handleSelectHistory = async (historyId: number) => {
    discardEmptyLiveSession();
    setSelectedHistoryId(historyId);
    resetConversationState();
    setErrorMessage("");
    setIsLoadingHistoryMessages(true);

    try {
      const response = await getChatSession(historyId);

      if (response.code !== 200 || !response.result) {
        setErrorMessage(response.message || t("chatbot.historyLoadError"));
        setMessages([]);
        return;
      }

      const detail = response.result;
      const restoredMessages: ChatMessage[] = detail.messages.map(
        (message, index) => ({
          id: historyId * 100000 + index,
          role: message.role,
          content: message.content,
          attachmentUrl: message.image_url || undefined,
        }),
      );

      // 문진 미완료 → 라이브 문진으로 이어서 진행(입력 활성화).
      if (detail.resumable_triage && selectedPet) {
        onResumeTriage?.({
          sessionId: detail.session_id,
          messages: restoredMessages,
          quickReplies: detail.resume_quick_replies || [],
        });
        return;
      }

      setMessages(restoredMessages);

      // 문진 완료·예약 미확정 → 슬롯 선택 단계 재개.
      if (detail.resumable_schedule && detail.emrid && selectedPet) {
        onResumeSchedule?.({ sessionId: detail.session_id, emrid: detail.emrid });
      } else if (detail.can_followup && detail.emrid) {
        // 팔로우업 활성(진료 시간 전) → 경과 입력 활성화.
        onFollowupRestore?.(detail.emrid);
      } else if (detail.followup_closed && detail.emrid) {
        // 팔로우업 마감(진료 시작 시간 경과) → 입력창 대신 마감 안내.
        onFollowupClosed?.(detail.emrid);
      } else if (detail.booking_complete && detail.emrid) {
        // 일반 예약 완료(followup 미활성) → 입력창 대신 상담 완료 안내.
        onBookingComplete?.(detail.emrid);
      }
    } catch (error) {
      setErrorMessage(
        getErrorMessage(error, t("chatbot.historyLoadError")),
      );
      setMessages([]);
    } finally {
      setIsLoadingHistoryMessages(false);
    }
  };

  const handleDeleteHistory = async (history: ChatSessionHistory) => {
    const isConfirmed = window.confirm(t("chatbot.deleteConfirm"));
    if (!isConfirmed) {
      return;
    }

    try {
      setErrorMessage("");

      const response = await deleteChatSession(history.session_id);
      if (response.code !== 200) {
        setErrorMessage(response.message || t("chatbot.historyDeleteError"));
        return;
      }

      setChatHistories((currentHistories) =>
        currentHistories.filter(
          (currentHistory) =>
            currentHistory.session_id !== history.session_id,
        ),
      );

      if (selectedHistoryId === history.session_id) {
        setSelectedHistoryId(null);
        setIsLoadingHistoryMessages(false);
        resetConversationState();
      }
    } catch (error) {
      setErrorMessage(
        getErrorMessage(error, t("chatbot.historyDeleteError")),
      );
    }
  };

  const updateChatHistoryKeywords = (sessionId: number, keywords: string[]) => {
    setChatHistories((currentHistories) =>
      currentHistories.map((history) =>
        history.session_id === sessionId
          ? { ...history, keywords, status: t("chatbot.statusCompleted") }
          : history,
      ),
    );
  };

  return {
    chatHistories,
    selectedHistoryId,
    selectedHistory,
    isLoadingHistories,
    isLoadingHistoryMessages,
    creatingPetId,
    resetSessionStateForPetChange,
    handleCreateSession,
    handleSelectHistory,
    handleDeleteHistory,
    refreshChatHistories,
    updateChatHistoryKeywords,
    discardEmptyLiveSession,
  };
};
