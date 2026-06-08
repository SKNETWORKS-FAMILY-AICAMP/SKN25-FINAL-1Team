import {
  useEffect,
  useCallback,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { isAxiosError } from "axios";
import { useSearchParams } from "react-router-dom";
import { type ChatSessionHistory } from "../../api/chat-api";
import { getPets, type Pet } from "../../api/pets-api";
import ChatDatePicker from "../../components/chatbot/chat-date-picker";
import ChatInputBox from "../../components/chatbot/chat-input-box";
import ChatMessageList from "../../components/chatbot/chat-message-list";
import ChatSessionList from "../../components/chatbot/chat-session-list";
import PetSelector from "../../components/chatbot/pet-selector";
import GuardianNavbar from "../../components/guardian-navbar";
import { useAgentPipeline } from "../../hooks/use-agent-pipeline";
import { useChatConversation } from "../../hooks/use-chat-conversation";
import { useChatSessions } from "../../hooks/use-chat-sessions";
import { useChatUpload } from "../../hooks/use-chat-upload";
import { useTranslation } from "../../i18n/language-context";
import { translateKnownText } from "../../i18n/known-text";

const SYMPTOM_PILLS = [
  "구토",
  "설사",
  "피부",
  "기침",
  "식욕저하",
  "눈물",
  "절뚝거림",
] as const;

// chatPhase: UI 레이어에서 사용하는 상태 머신
// IDLE / SYMPTOM_COLLECTING → pipeline.phase === "chatting"
// TRIAGE_RUNNING           → pipeline.phase === "scheduling"
// SLOT_RECOMMENDING        → pipeline.phase === "slot-selection"
// BOOKING_CONFIRMED        → pipeline.phase === "confirmed"
// FOLLOWUP_ACTIVE          → pipeline.phase === "followup"
type ChatPhase =
  | "IDLE"
  | "SYMPTOM_COLLECTING"
  | "TRIAGE_RUNNING"
  | "SLOT_RECOMMENDING"
  | "BOOKING_CONFIRMED"
  | "FOLLOWUP_ACTIVE";

const defaultProfileImages = [
  "/assets/profile1.png",
  "/assets/profile2.png",
  "/assets/profile3.png",
  "/assets/profile4.png",
  "/assets/profile5.png",
  "/assets/profile6.png",
];

const getProfileImage = (pet: Pet) =>
  pet.profile_image ||
  defaultProfileImages[Math.abs(pet.pet_id) % defaultProfileImages.length];

const getErrorMessage = (error: unknown, fallbackMessage: string) => {
  if (isAxiosError<{ message?: string } | string>(error)) {
    const responseData = error.response?.data;

    if (typeof responseData === "string") {
      try {
        const parsedData = JSON.parse(responseData) as { message?: string };
        return parsedData.message || fallbackMessage;
      } catch {
        return fallbackMessage;
      }
    }

    return responseData?.message || fallbackMessage;
  }

  return fallbackMessage;
};

const formatDateToYyyyMmDd = (date: Date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
};

const MessageCircleIcon = () => (
  <svg viewBox="0 0 24 24" className="h-7 w-7" fill="none" aria-hidden="true">
    <path
      d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

const TrashIcon = () => (
  <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" aria-hidden="true">
    <path
      d="M9 4h6M4 7h16M18 7l-.7 11.2A2 2 0 0 1 15.3 20H8.7a2 2 0 0 1-2-1.8L6 7M10 11v5M14 11v5"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

const ChatbotPage = () => {
  const { lang, t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [searchParams] = useSearchParams();
  const selectedPetIdFromQuery = Number(searchParams.get("petId"));
  const [pets, setPets] = useState<Pet[]>([]);
  const [selectedPetId, setSelectedPetId] = useState<number | null>(
    Number.isFinite(selectedPetIdFromQuery) ? selectedPetIdFromQuery : null,
  );
  const [isLoadingPets, setIsLoadingPets] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");

  const {
    pendingAttachment,
    setPendingAttachment,
    clearPendingAttachment,
    handleSelectAttachment,
    isUploadingAttachment,
  } = useChatUpload({
    setErrorMessage,
    getErrorMessage,
  });

  // onTriageComplete를 ref로 관리 — pipeline 초기화 전 순환 참조 방지
  const onTriageCompleteRef = useRef<
    | ((
        sessionId: number,
        keywords: string[],
        collectedInfo: Record<string, unknown>,
        emrid?: number,
        scheduleTaskId?: string,
      ) => void)
    | undefined
  >(undefined);

  const {
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
  } = useChatConversation({
    pendingAttachment,
    setPendingAttachment,
    clearPendingAttachment,
    isUploadingAttachment,
    setErrorMessage,
    getErrorMessage,
    onTriageComplete: (sessionId, keywords, collectedInfo, emrid, scheduleTaskId) =>
      onTriageCompleteRef.current?.(sessionId, keywords, collectedInfo, emrid, scheduleTaskId),
  });

  const pipeline = useAgentPipeline({
    setMessages,
    setQuickReplies,
    setIsStreaming,
  });

  const selectedPet = useMemo(
    () => pets.find((pet) => pet.pet_id === selectedPetId),
    [pets, selectedPetId],
  );

  const {
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
  } = useChatSessions({
    selectedPet,
    resetConversationState,
    setSession,
    setMessages,
    setErrorMessage,
    getErrorMessage,
    getProfileImage,
    onFollowupRestore: pipeline.restoreFollowupPhase,
  });

  // pipeline이 정의된 후 ref를 최신 값으로 동기화
  onTriageCompleteRef.current = (sessionId, keywords, collectedInfo, emrid, scheduleTaskId) => {
    if (selectedPet) {
      updateChatHistoryKeywords(sessionId, keywords);
      refreshChatHistories(selectedPet.pet_id);
      void pipeline.startSchedulePhase(selectedPet, collectedInfo, emrid, scheduleTaskId);
    }
  };

  // 세션 초기화 시 pipeline도 초기화
  useEffect(() => {
    if (!session) {
      pipeline.resetPipeline();
    }
  }, [session]); // eslint-disable-line react-hooks/exhaustive-deps

  // 새 세션 시작 시 초기 증상 질문 + symptom pills 자동 출력
  // (decision tree Q_INIT_SYMPTOM을 백엔드가 단일 출처로 내려준다)
  useEffect(() => {
    if (session && messages.length === 0) {
      setMessages([
        {
          id: Date.now(),
          role: "assistant",
          content: session.initial_message || t("chatbot.initialQuestion"),
        },
      ]);
      setQuickReplies(session.initial_pills?.length ? session.initial_pills : [...SYMPTOM_PILLS]);
    }
  }, [session, t]); // eslint-disable-line react-hooks/exhaustive-deps

  // pipeline.phase → chatPhase 매핑 (UI 상태 제어용)
  const chatPhase = useMemo((): ChatPhase => {
    switch (pipeline.phase) {
      case "scheduling": return "TRIAGE_RUNNING";
      case "slot-selection": return "SLOT_RECOMMENDING";
      case "booking": return "SLOT_RECOMMENDING";
      case "confirmed": return "BOOKING_CONFIRMED";
      case "followup": return "FOLLOWUP_ACTIVE";
      default:
        return messages.length === 0 ? "IDLE" : "SYMPTOM_COLLECTING";
    }
  }, [pipeline.phase, messages.length]);

  const todayChatTitle = useMemo(() => formatDateToYyyyMmDd(new Date()), []);

  const getHistoryTitle = useCallback(
    (history: ChatSessionHistory) => {
      const keywords = history.keywords
        .map((keyword) => translateKnownText(keyword.trim(), t, lang))
        .filter((keyword) => keyword && keyword.length <= 24)
        .slice(0, 3);
      return keywords.length > 0 ? keywords.join(", ") : t("chatbot.historyDefaultTitle");
    },
    [lang, t],
  );

  useEffect(() => {
    let isMounted = true;

    const loadPets = async () => {
      try {
        setIsLoadingPets(true);
        setErrorMessage("");

        const response = await getPets();
        if (!isMounted) return;

        if (response.code !== 200) {
          setErrorMessage(
            response.message || t("chatbot.petLoadError"),
          );
          setPets([]);
          return;
        }

        setPets(
          [...response.result].sort((a, b) =>
            a.petname.localeCompare(b.petname, "ko"),
          ),
        );
      } catch (error) {
        if (!isMounted) return;
        setErrorMessage(
          getErrorMessage(error, t("chatbot.petLoadError")),
        );
      } finally {
        if (isMounted) setIsLoadingPets(false);
      }
    };

    loadPets();
    return () => { isMounted = false; };
  }, [t]);

  const handleSelectPet = (petId: number) => {
    if (petId === selectedPetId) return;
    setSelectedPetId(petId);
    resetSessionStateForPetChange();
  };

  // 통합 메시지 전송 핸들러 — phase에 따라 분기
  const handleSendCombined = async (content: string) => {
    const trimmed = content.trim();
    // 텍스트가 없어도 첨부파일만 있으면 전송 허용(특히 경과보고에 사진만 올리는 경우).
    if ((!trimmed && !pendingAttachment) || isStreaming || isUploadingAttachment) return;

    if (pipeline.phase === "slot-selection") {
      // 슬롯 버튼 클릭 또는 텍스트 입력
      setMessages((prev) => [
        ...prev,
        { id: Date.now(), role: "user" as const, content: trimmed },
      ]);
      setQuickReplies([]);
      setMessageInput("");
      if (pipeline.isSlotLabel(trimmed) && selectedPet) {
        await pipeline.handleSlotSelect(trimmed, selectedPet.pet_id);
      } else {
        // 슬롯이 아닌 텍스트 — 안내 메시지 표시
        setMessages((prev) => [
          ...prev,
          {
            id: Date.now() + 1,
            role: "assistant" as const,
            content: t("chatbot.selectSlotPrompt"),
          },
        ]);
        setQuickReplies(pipeline.getSlotLabels());
      }
      return;
    }

    if (pipeline.phase === "followup") {
      // 경과 모니터링 메시지 — 첨부 이미지가 있으면 함께 전송하고 대화에도 노출한다.
      const att = pendingAttachment;
      const images = att?.cloudfrontUrl ? [att.cloudfrontUrl] : [];
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now(),
          role: "user" as const,
          content: trimmed,
          attachmentUrl: att?.cloudfrontUrl,
          attachmentType: att?.contentType,
        },
      ]);
      setQuickReplies([]);
      setMessageInput("");
      clearPendingAttachment();
      await pipeline.handleFollowupMessage(trimmed, images);
      return;
    }

    if (pipeline.phase === "confirmed") return; // 상담 완료 — 입력 차단

    // 일반 트리아지 채팅
    await handleSendMessage(trimmed);
  };

  const handleSubmitCombined = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void handleSendCombined(messageInput);
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-950">
      <GuardianNavbar />

      <main className="mx-auto flex w-full max-w-[1200px] flex-col px-6 pt-10 pb-6 lg:h-[calc(100vh-4rem)] lg:min-h-0">
        <div className="mb-6 shrink-0 flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">
              {t("chatbot.title")}
            </h1>
            <p className="mt-0.5 text-sm text-slate-500">
              {t("chatbot.subtitle")}
            </p>
          </div>
        </div>
        <section className="flex flex-col overflow-hidden rounded-2xl border border-slate-100 bg-white shadow-sm lg:min-h-0 lg:flex-1">

          {/* 상태 확인 안내 배너 (followup에서 escalationPromptVisible=true 시) */}
          {pipeline.escalationPromptVisible ? (
            <div className="border-b border-blue-200 bg-blue-50 px-5 py-3 text-sm font-bold text-blue-700 sm:px-7 flex justify-between items-center flex-wrap gap-2">
              <span>{t("chatbot.escalation")}</span>
              <div className="flex gap-2">
                {pipeline.guardianCareRecommendation.map((actionLabel, idx) => (
                  <button
                    key={idx}
                    type="button"
                    className="inline-flex items-center gap-1 bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded-xl text-xs font-extrabold transition"
                  >
                    {actionLabel}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {errorMessage ? (
            <div className="border-b border-rose-100 bg-rose-50 px-5 py-3 text-sm font-bold text-rose-600 sm:px-7">
              {errorMessage}
            </div>
          ) : null}

          <div className="grid lg:min-h-0 lg:flex-1 lg:grid-cols-[200px_200px_1fr]">
            <PetSelector
              pets={pets}
              selectedPetId={selectedPetId}
              isLoadingPets={isLoadingPets}
              onSelectPet={handleSelectPet}
              getProfileImage={getProfileImage}
            />

            <ChatSessionList
              selectedPet={selectedPet}
              chatHistories={chatHistories}
              selectedHistoryId={selectedHistoryId}
              isLoadingHistories={isLoadingHistories}
              creatingPetId={creatingPetId}
              onCreateSession={handleCreateSession}
              onSelectHistory={handleSelectHistory}
              onDeleteHistory={handleDeleteHistory}
              getHistoryTitle={getHistoryTitle}
            />

            <section className="relative flex min-h-[480px] flex-col overflow-hidden bg-white lg:min-h-0">
              {session ? (
                <>
                  <div className="flex h-14 shrink-0 items-center gap-3 border-b border-slate-100 px-5 sm:px-7">
                    <div className="min-w-0 flex-1">
                      <h2 className="truncate text-base font-extrabold text-slate-950">
                        {t("chatbot.newChatTitle", { date: todayChatTitle })}
                      </h2>
                    </div>
                  </div>

                  <ChatMessageList
                    messages={messages}
                    quickReplies={quickReplies}
                    isStreaming={isStreaming}
                    onSendMessage={(content) => {
                      void handleSendCombined(content);
                    }}
                    onOpenDatePicker={() => pipeline.setShowDatePicker(true)}
                  />

                  {/* 직접 날짜 선택 피커 — 팝업으로 띄움 */}
                  {pipeline.showDatePicker && (
                    <div className="absolute bottom-16 right-4 z-10">
                      <ChatDatePicker
                        onSelectSlot={(date, time, doctorid, label) => {
                          void pipeline.handleManualSlotSelect(date, time, doctorid, label);
                        }}
                        onCancel={() => pipeline.setShowDatePicker(false)}
                      />
                    </div>
                  )}

                  {/* 상태별 입력 영역 */}
                  {chatPhase === "BOOKING_CONFIRMED" ? (
                    <div className="border-t border-slate-100 px-5 py-4 text-center text-sm font-semibold text-slate-400">
                      {t("chatbot.bookingComplete")}
                    </div>
                  ) : chatPhase === "SLOT_RECOMMENDING" ? (
                    <div className="border-t border-slate-100 px-4 py-3 text-center">
                      <span className="text-xs font-semibold text-slate-400">
                        {t("chatbot.slotHint")}
                      </span>
                    </div>
                  ) : (
                    <ChatInputBox
                      fileInputRef={fileInputRef}
                      pendingAttachment={pendingAttachment}
                      messageInput={messageInput}
                      isStreaming={isStreaming || chatPhase === "TRIAGE_RUNNING"}
                      isUploadingAttachment={isUploadingAttachment}
                      onClearPendingAttachment={clearPendingAttachment}
                      onSelectAttachment={handleSelectAttachment}
                      onSubmitMessage={handleSubmitCombined}
                      onChangeMessageInput={setMessageInput}
                    />
                  )}
                </>
              ) : selectedHistory && selectedPet ? (
                <>
                  <div className="flex h-14 shrink-0 items-center gap-3 border-b border-slate-100 px-5 sm:px-7">
                    <div className="min-w-0 flex-1">
                      <h2 className="truncate text-base font-extrabold text-slate-950">
                        {getHistoryTitle(selectedHistory)}
                      </h2>
                      <p className="text-xs font-bold text-slate-500">
                        {selectedPet.petname} · {selectedHistory.created_at}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleDeleteHistory(selectedHistory)}
                      className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-slate-400 transition hover:bg-rose-50 hover:text-rose-500"
                      aria-label={t("chatbot.deleteHistory")}
                    >
                      <TrashIcon />
                    </button>
                  </div>

                  {isLoadingHistoryMessages ? (
                    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-5 sm:p-7">
                      <div className="flex-1" />
                      <div className="max-w-[82%] rounded-3xl rounded-bl-lg bg-slate-100 px-5 py-4 text-sm font-semibold leading-6 text-slate-700">
                        {t("chatbot.loadingHistory")}
                      </div>
                    </div>
                  ) : (
                    <ChatMessageList
                      messages={messages}
                      quickReplies={[]}
                      isStreaming={isStreaming}
                      onSendMessage={() => {}}
                      onOpenDatePicker={() => {}}
                    />
                  )}

                  {pipeline.phase === "followup" && (
                    <ChatInputBox
                      fileInputRef={fileInputRef}
                      pendingAttachment={pendingAttachment}
                      messageInput={messageInput}
                      isStreaming={isStreaming}
                      isUploadingAttachment={isUploadingAttachment}
                      onClearPendingAttachment={clearPendingAttachment}
                      onSelectAttachment={handleSelectAttachment}
                      onSubmitMessage={handleSubmitCombined}
                      onChangeMessageInput={setMessageInput}
                    />
                  )}
                </>
              ) : (
                <>
                  <div className="flex h-14 shrink-0 items-center justify-center border-b border-slate-100 px-5 sm:px-7">
                    <h2 className="truncate text-[15px] font-bold text-slate-900">
                      {t("chatbot.title")}
                    </h2>
                  </div>
                  <div className="flex flex-1 flex-col items-center px-6 pt-[150px] text-center">
                    <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-slate-100 text-slate-400">
                      <MessageCircleIcon />
                    </div>
                    <div>
                      <h2 className="mt-5 text-2xl font-bold text-slate-800">
                        {t("chatbot.emptyTitle")}
                      </h2>
                      <p className="mt-3 text-sm font-semibold leading-5 text-slate-500">
                        {t("chatbot.emptyDescription")}
                      </p>
                    </div>
                  </div>
                </>
              )}
            </section>
          </div>
        </section>
      </main>
    </div>
  );
};

export default ChatbotPage;
