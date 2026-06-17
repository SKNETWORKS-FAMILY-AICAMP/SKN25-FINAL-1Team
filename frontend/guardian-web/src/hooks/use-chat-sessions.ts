import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
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
import { isVideoAttachment } from "../utils/chat-attachment";

/** 현재 화면에 떠 있는 라이브 세션의 식별자 + 보호자가 한마디라도 했는지 여부. */
export interface LiveSessionInfo {
  id: number;
  hasUserMessage: boolean;
}

// 새로고침(F5) 후에도 진행 중이던 상담을 복원하기 위해 현재 열린 세션을 보관.
// sessionStorage라 같은 탭의 새로고침에는 살아남고, 탭을 닫으면 사라진다.
const ACTIVE_SESSION_KEY = "medipaw-chatbot-active";

interface ActiveChatSession {
  petId: number;
  /** 선택된 상담 세션 id. 펫만 선택하고 세션은 안 연 상태면 null. */
  sessionId: number | null;
}

export const readActiveChatSession = (): ActiveChatSession | null => {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(ACTIVE_SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ActiveChatSession;
    if (
      typeof parsed.petId === "number" &&
      (typeof parsed.sessionId === "number" || parsed.sessionId === null)
    ) {
      return parsed;
    }
    return null;
  } catch {
    return null;
  }
};

// 사용자가 펫/세션을 고른 시점에 명시적으로 저장한다(반응형 effect의 마운트
// 타이밍 경쟁을 피하기 위해). 저장 실패는 무시 — 복원만 안 될 뿐 기능엔 영향 없음.
export const writeActiveChatSession = (petId: number, sessionId: number | null) => {
  try {
    window.sessionStorage.setItem(
      ACTIVE_SESSION_KEY,
      JSON.stringify({ petId, sessionId }),
    );
  } catch {
    // 무시
  }
};

export const clearActiveChatSession = () => {
  try {
    window.sessionStorage.removeItem(ACTIVE_SESSION_KEY);
  } catch {
    // 무시
  }
};

interface UseChatSessionsParams {
  selectedPet?: Pet;
  /** 새로고침/직접진입(POP)일 때만 true — 저장된 세션 자동 복원 허용. */
  allowRefreshRestore: boolean;
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
  allowRefreshRestore,
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
  // 무한스크롤 페이지네이션 — 10개씩, 더 있는지(hasMore) / 추가 로딩중(isLoadingMore)
  const [hasMoreHistories, setHasMoreHistories] = useState(false);
  const [isLoadingMoreHistories, setIsLoadingMoreHistories] = useState(false);
  const [selectedHistoryId, setSelectedHistoryId] = useState<number | null>(
    null,
  );
  // 마운트 시 펫이 복원되면 곧바로 히스토리를 불러오므로, 초기값을 true로 두어
  // 펫 로드~히스토리 로드 사이 빈 화면 깜빡임을 막는다. (펫 없으면 effect가 false로)
  const [isLoadingHistories, setIsLoadingHistories] = useState(true);
  const [isLoadingHistoryMessages, setIsLoadingHistoryMessages] =
    useState(false);
  const [creatingPetId, setCreatingPetId] = useState<number | null>(null);

  // 새로고침 복원용 — 히스토리 첫 로드 시 저장된 세션을 한 번만 자동 선택한다.
  const initialRestoreDoneRef = useRef(false);
  const handleSelectHistoryRef = useRef<((id: number) => void) | null>(null);
  const allowRefreshRestoreRef = useRef(allowRefreshRestore);
  allowRefreshRestoreRef.current = allowRefreshRestore;

  const selectedHistory = useMemo(
    () =>
      chatHistories.find((history) => history.session_id === selectedHistoryId),
    [chatHistories, selectedHistoryId],
  );

  // 목록 갱신 — 항상 첫 페이지(offset 0)로 리셋
  const refreshChatHistories = async (petId: number) => {
    try {
      const response = await getChatSessions(petId);
      if (response.code === 200) {
        setChatHistories(response.result);
        setHasMoreHistories(Boolean(response.has_more));
      }
    } catch {
      // 갱신 실패는 무시 — 이미 표시 중인 목록 유지
    }
  };

  // 더 보기 — 스크롤 바닥 도달 시 다음 10개를 이어 붙임(append)
  const loadMoreChatHistories = useCallback(async () => {
    if (!selectedPet || !hasMoreHistories || isLoadingMoreHistories) {
      return;
    }
    try {
      setIsLoadingMoreHistories(true);
      // offset = 이미 불러온 개수 (별도 page 카운터 불필요)
      const response = await getChatSessions(
        selectedPet.pet_id,
        10,
        chatHistories.length,
      );
      if (response.code === 200) {
        setChatHistories((prev) => [...prev, ...response.result]);
        setHasMoreHistories(Boolean(response.has_more));
      }
    } catch {
      // 추가 로딩 실패는 무시 — 이미 표시 중인 목록 유지
    } finally {
      setIsLoadingMoreHistories(false);
    }
  }, [selectedPet, hasMoreHistories, isLoadingMoreHistories, chatHistories.length]);

  useEffect(() => {
    if (!selectedPet) {
      // isLoadingHistories는 끄지 않는다 — 마운트~펫 해결 사이 false 프레임이 생겨
      // 빈 화면이 깜빡이기 때문. 펫이 없을 땐 ChatSessionList가 이 값을 무시한다.
      setChatHistories([]);
      setHasMoreHistories(false);
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
          setHasMoreHistories(false);
          return;
        }

        // 첫 페이지 — 교체 후 다음 페이지 존재 여부 세팅
        setChatHistories(response.result);
        setHasMoreHistories(Boolean(response.has_more));

        // 새로고침/직접진입(POP) 직후 첫 로드라면, 저장된 세션을 한 번만 자동 복원.
        // 인앱 Link 재진입(PUSH)은 allowRefreshRestore=false라 복원하지 않는다.
        // (펫은 페이지가 초기 렌더에서 이미 복원 — 여기선 세션만 이어 붙인다.)
        if (!initialRestoreDoneRef.current) {
          initialRestoreDoneRef.current = true;
          if (allowRefreshRestoreRef.current) {
            const stored = readActiveChatSession();
            const sessionStillExists =
              stored?.sessionId != null &&
              stored.petId === selectedPet.pet_id &&
              response.result.some(
                (history) => history.session_id === stored.sessionId,
              );
            if (sessionStillExists) {
              handleSelectHistoryRef.current?.(stored.sessionId as number);
            }
          }
        }
      } catch (error) {
        if (!isMounted) {
          return;
        }

        setErrorMessage(
          getErrorMessage(error, t("chatbot.historyLoadError")),
        );
        setChatHistories([]);
        setHasMoreHistories(false);
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
    // 새 펫의 히스토리를 곧 불러오므로 즉시 로딩 상태로 — 펫 전환 시 빈 화면 깜빡임 방지.
    setIsLoadingHistories(true);
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
      writeActiveChatSession(selectedPet.pet_id, response.result.session_id);
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
    if (selectedPet) {
      writeActiveChatSession(selectedPet.pet_id, historyId);
    }
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
      // 저장 안 되는 시작 인사말을 맨 앞에 복원(라이브 UX와 동일)
      const greeting: ChatMessage = {
        id: historyId * 100000 - 1,
        role: "assistant",
        content: t("chatbot.initialQuestion"),
      };
      // 저장된 메시지 복원 — meta.card가 있으면 확정·주의사항 카드로 되살림
      const restoredMessages: ChatMessage[] = [
        greeting,
        ...detail.messages.map((message, index) => ({
          id: historyId * 100000 + index,
          role: message.role,
          content: message.content,
          attachmentUrl: message.image_url || undefined,
          attachmentType: isVideoAttachment(undefined, message.image_url || undefined)
            ? "video/*"
            : undefined,
          card: (message.meta as { card?: ChatMessage["card"] } | undefined)?.card,
        })),
      ];

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

  // 히스토리 로드 효과(위)에서 최신 handleSelectHistory를 호출하기 위한 ref 동기화.
  handleSelectHistoryRef.current = handleSelectHistory;

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
        // 열려 있던 세션이 삭제됨 — 펫 선택만 유지(세션 복원 대상에서 제외).
        if (selectedPet) {
          writeActiveChatSession(selectedPet.pet_id, null);
        }
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
    // 무한스크롤 페이지네이션
    hasMoreHistories,
    isLoadingMoreHistories,
    loadMoreChatHistories,
    resetSessionStateForPetChange,
    handleCreateSession,
    handleSelectHistory,
    handleDeleteHistory,
    refreshChatHistories,
    updateChatHistoryKeywords,
    discardEmptyLiveSession,
  };
};
