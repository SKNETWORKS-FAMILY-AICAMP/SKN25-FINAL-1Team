import {
  useEffect,
  useCallback,
  useMemo,
  useRef,
  useState,
} from "react";
import { isAxiosError } from "axios";
import { useNavigationType, useSearchParams } from "react-router-dom";
import {
  deleteChatSessionKeepalive,
  resumeSchedule,
  type ChatSessionHistory,
} from "../../api/chat-api";
import { getPets, type Pet } from "../../api/pets-api";
import { useAuthStore } from "../../stores/auth-store";
import type { LiveSessionInfo } from "../../hooks/use-chat-sessions";
import ChatDatePicker from "../../components/chatbot/chat-date-picker";
import ChatInputBox from "../../components/chatbot/chat-input-box";
import ChatMessageList from "../../components/chatbot/chat-message-list";
import ChatSessionList from "../../components/chatbot/chat-session-list";
import PetSelector from "../../components/chatbot/pet-selector";
import { useMyHospitals } from "../../hooks/use-my-hospitals";
import { useAgentPipeline } from "../../hooks/use-agent-pipeline";
import { useChatConversation } from "../../hooks/use-chat-conversation";
import {
  useChatSessions,
  readActiveChatSession,
  writeActiveChatSession,
  clearActiveChatSession,
} from "../../hooks/use-chat-sessions";
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
// FOLLOWUP_CLOSED          → pipeline.phase === "followup-closed" (진료 시작 시간 경과)
type ChatPhase =
  | "IDLE"
  | "SYMPTOM_COLLECTING"
  | "TRIAGE_RUNNING"
  | "SLOT_RECOMMENDING"
  | "BOOKING_CONFIRMED"
  | "FOLLOWUP_ACTIVE"
  | "FOLLOWUP_CLOSED";

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

// 메모된 자식에 넘기는 안정 콜백/상수 — identity가 매 렌더 바뀌면 React.memo가
// 무력화되므로 고정한다.
const EMPTY_QUICK_REPLIES: string[] = [];
const noop = () => {};

// 본문이 매 렌더 바뀌더라도 identity는 고정인 콜백을 만든다(useEffectEvent 패턴).
const useStableCallback = <Args extends unknown[], Return>(
  fn: (...args: Args) => Return,
) => {
  const ref = useRef(fn);
  ref.current = fn;
  return useCallback((...args: Args) => ref.current(...args), []);
};

const ChatbotPage = () => {
  const { lang, t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [searchParams] = useSearchParams();
  const selectedPetIdFromQuery = Number(searchParams.get("petId"));
  // 새로고침/직접진입은 "POP", 네비바 Link 클릭 재진입은 "PUSH".
  // POP일 때만 이전 챗봇 상태(펫/세션)를 복원한다.
  const navigationType = useNavigationType();
  const allowRefreshRestore = navigationType === "POP";
  const [pets, setPets] = useState<Pet[]>([]);
  // 펫 선택은 초기 렌더에서 동기 복원해 "펫 미선택" 화면 깜빡임을 없앤다.
  const [selectedPetId, setSelectedPetId] = useState<number | null>(() => {
    if (Number.isFinite(selectedPetIdFromQuery) && selectedPetIdFromQuery > 0) {
      return selectedPetIdFromQuery;
    }
    if (allowRefreshRestore) {
      const stored = readActiveChatSession();
      if (stored) return stored.petId;
    }
    return null;
  });
  const [isLoadingPets, setIsLoadingPets] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  // 선택 병원 — 병원탭/예약 모달과 동일 키로 공유. 내 병원 목록은 API(백엔드 미가동 시 mock 폴백).
  const { hospitals: myHospitals } = useMyHospitals();
  const [selectedHospitalId, setSelectedHospitalId] = useState<number | null>(() => {
    const stored = Number(window.localStorage.getItem("medipaw.guardian.hospitalid"));
    return stored > 0 ? stored : null;
  });
  useEffect(() => {
    if (myHospitals.length === 0) return;
    setSelectedHospitalId((prev) =>
      prev != null && myHospitals.some((h) => h.hospitalid === prev)
        ? prev
        : myHospitals[0].hospitalid,
    );
  }, [myHospitals]);
  const handleSelectHospital = (id: number) => {
    setSelectedHospitalId(id);
    window.localStorage.setItem("medipaw.guardian.hospitalid", String(id));
  };
  // 보호자가 한마디도 안 한 빈 세션 추적 — 이탈 시 삭제(req1).
  const liveSessionRef = useRef<LiveSessionInfo | null>(null);

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
    hospitalId: selectedHospitalId,
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
    discardEmptyLiveSession,
  } = useChatSessions({
    selectedPet,
    allowRefreshRestore,
    // 세션 전환 시 pipeline phase도 함께 초기화 → 이전 세션의 phase(followup 등)가
    // 다음 세션에 잔류해 입력창/배너가 잘못 뜨는 것을 방지한다.
    resetConversationState: () => {
      resetConversationState();
      pipeline.resetPipeline();
    },
    setSession,
    setMessages,
    setErrorMessage,
    getErrorMessage,
    getProfileImage,
    onFollowupRestore: pipeline.restoreFollowupPhase,
    onFollowupClosed: pipeline.restoreFollowupClosedPhase,
    onBookingComplete: pipeline.restoreConfirmedPhase,
    onResumeTriage: ({ sessionId, messages: restoredMessages, quickReplies: resumedQuickReplies }) => {
      if (!selectedPet) return;
      // 라이브 문진 재개 — 세션을 살리고 입력을 활성화한다(req4).
      pipeline.resetPipeline();
      setSession({
        session_id: sessionId,
        pet_name: selectedPet.petname,
        profile_image: getProfileImage(selectedPet),
      });
      // 저장되지 않는 최초 질문 말풍선을 앞에 복원해 라이브 UX와 맞춘다.
      setMessages([
        {
          id: sessionId * 100000 - 1,
          role: "assistant",
          content: t("chatbot.initialQuestion"),
        },
        ...restoredMessages,
      ]);
      setQuickReplies(resumedQuickReplies);
    },
    onResumeSchedule: ({ sessionId, emrid }) => {
      if (!selectedPet) return;
      // 슬롯 선택 단계 재개 — 서버에서 schedule 재실행 후 슬롯 카드 노출(req4).
      pipeline.resetPipeline();
      setSession({
        session_id: sessionId,
        pet_name: selectedPet.petname,
        profile_image: getProfileImage(selectedPet),
      });
      void (async () => {
        try {
          const response = await resumeSchedule(sessionId);
          if (response.code === 200 && response.result) {
            await pipeline.startSchedulePhase(
              selectedPet,
              response.result.triage_info ?? {},
              response.result.emrid ?? emrid,
              response.result.schedule_task_id,
            );
          } else {
            setErrorMessage(response.message || t("chatbot.slotsLoadError"));
          }
        } catch (error) {
          setErrorMessage(getErrorMessage(error, t("chatbot.slotsLoadError")));
        }
      })();
    },
    liveSessionRef,
  });

  // 라이브 세션의 '보호자 발화 여부'를 ref로 동기화한다.
  useEffect(() => {
    liveSessionRef.current = session
      ? {
          id: session.session_id,
          hasUserMessage: messages.some((message) => message.role === "user"),
        }
      : null;
  }, [session, messages]);

  // 페이지 이탈(SPA 언마운트) 및 탭/새로고침 종료 시 빈 세션 정리.
  useEffect(() => {
    const handleBeforeUnload = () => {
      const live = liveSessionRef.current;
      if (!live || live.hasUserMessage) return;
      const accessToken = useAuthStore.getState().guardian?.accessToken;
      if (accessToken) {
        deleteChatSessionKeepalive(live.id, accessToken);
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
      discardEmptyLiveSession();
    };
  }, [discardEmptyLiveSession]);

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
      case "followup-closed": return "FOLLOWUP_CLOSED";
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

        setPets(
          [...response].sort((a, b) =>
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

  // 네비바 Link로 챗봇에 재진입(PUSH)한 경우엔 이전 선택 잔상을 지운다 → 새 화면.
  // (이후 F5(POP) 시에도 깨끗한 진입 화면을 유지)
  useEffect(() => {
    if (!allowRefreshRestore) {
      clearActiveChatSession();
    }
    // 마운트 시 1회만 실행
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSelectPet = (petId: number) => {
    if (petId === selectedPetId) return;
    setSelectedPetId(petId);
    resetSessionStateForPetChange();
    // 펫 선택 상태를 저장 → 새로고침 시 이 펫이 복원된다(세션은 아직 없음).
    writeActiveChatSession(petId, null);
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
      clearPendingAttachment();
      await pipeline.handleFollowupMessage(trimmed, images);
      return;
    }

    if (pipeline.phase === "confirmed") return; // 상담 완료 — 입력 차단

    // 일반 트리아지 채팅
    await handleSendMessage(trimmed);
  };

  // 메모된 자식들에 넘길 안정 콜백 — latest-ref로 identity를 고정해 React.memo 유지.
  const stableSelectPet = useStableCallback(handleSelectPet);
  const stableSendCombined = useStableCallback((content: string) => {
    void handleSendCombined(content);
  });
  const stableOpenDatePicker = useStableCallback(() => {
    pipeline.setShowDatePicker(true);
  });
  const stableCreateSession = useStableCallback(handleCreateSession);
  const stableSelectHistory = useStableCallback(handleSelectHistory);
  const stableDeleteHistory = useStableCallback(handleDeleteHistory);

  return (
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
              onSelectPet={stableSelectPet}
              getProfileImage={getProfileImage}
            />

            <ChatSessionList
              selectedPet={selectedPet}
              selectedPetId={selectedPetId}
              isLoadingPets={isLoadingPets}
              chatHistories={chatHistories}
              selectedHistoryId={selectedHistoryId}
              isLoadingHistories={isLoadingHistories}
              creatingPetId={creatingPetId}
              onCreateSession={stableCreateSession}
              onSelectHistory={stableSelectHistory}
              onDeleteHistory={stableDeleteHistory}
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
                    {myHospitals.length > 0 ? (
                      <label className="flex shrink-0 items-center gap-1.5">
                        <span className="text-xs font-bold text-slate-400">
                          {t("chatbot.hospitalLabel")}
                        </span>
                        <select
                          value={selectedHospitalId ?? ""}
                          onChange={(event) => handleSelectHospital(Number(event.target.value))}
                          className="h-9 max-w-[170px] rounded-lg border border-slate-200 bg-white px-2 text-xs font-bold text-slate-700 outline-none transition focus:border-blue-400"
                        >
                          {myHospitals.map((hospital) => (
                            <option key={hospital.hospitalid} value={hospital.hospitalid}>
                              {hospital.name}
                            </option>
                          ))}
                        </select>
                      </label>
                    ) : null}
                  </div>

                  <ChatMessageList
                    messages={messages}
                    quickReplies={quickReplies}
                    isStreaming={isStreaming}
                    onSendMessage={stableSendCombined}
                    onOpenDatePicker={stableOpenDatePicker}
                  />

                  {/* 직접 날짜 선택 피커 — 팝업으로 띄움 */}
                  {pipeline.showDatePicker && (
                    <div className="absolute bottom-16 right-4 z-10">
                      <ChatDatePicker
                        durationMin={pipeline.getScheduleDurationMin()}
                        hospitalId={selectedHospitalId}
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
                  ) : chatPhase === "FOLLOWUP_CLOSED" ? (
                    <div className="border-t border-slate-100 px-5 py-4 text-center text-sm font-semibold text-slate-400">
                      {t("chatbot.followupClosed")}
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
                      isStreaming={isStreaming || chatPhase === "TRIAGE_RUNNING"}
                      isUploadingAttachment={isUploadingAttachment}
                      onClearPendingAttachment={clearPendingAttachment}
                      onSelectAttachment={handleSelectAttachment}
                      onSubmitMessage={stableSendCombined}
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
                      quickReplies={EMPTY_QUICK_REPLIES}
                      isStreaming={isStreaming}
                      onSendMessage={noop}
                      onOpenDatePicker={noop}
                    />
                  )}

                  {pipeline.phase === "followup" && (
                    <ChatInputBox
                      fileInputRef={fileInputRef}
                      pendingAttachment={pendingAttachment}
                      isStreaming={isStreaming}
                      isUploadingAttachment={isUploadingAttachment}
                      onClearPendingAttachment={clearPendingAttachment}
                      onSelectAttachment={handleSelectAttachment}
                      onSubmitMessage={stableSendCombined}
                    />
                  )}

                  {pipeline.phase === "followup-closed" && (
                    <div className="border-t border-slate-100 px-5 py-4 text-center text-sm font-semibold text-slate-400">
                      {t("chatbot.followupClosed")}
                    </div>
                  )}

                  {pipeline.phase === "confirmed" && (
                    <div className="border-t border-slate-100 px-5 py-4 text-center text-sm font-semibold text-slate-400">
                      {t("chatbot.bookingComplete")}
                    </div>
                  )}
                </>
              ) : creatingPetId !== null ||
                (selectedPetId !== null && isLoadingPets) ||
                (selectedPet && isLoadingHistories) ||
                isLoadingHistoryMessages ? (
                // 새 상담 생성/펫·히스토리·세션상세 로드 대기 중 —
                // 빈 진입 화면 깜빡임 대신 로딩 표시(상담기록 복원 중간 단계 포함).
                <>
                  <div className="flex h-14 shrink-0 items-center justify-center border-b border-slate-100 px-5 sm:px-7">
                    <h2 className="truncate text-[15px] font-bold text-slate-900">
                      {t("chatbot.title")}
                    </h2>
                  </div>
                  <div className="flex flex-1 items-center justify-center">
                    <div className="h-10 w-10 animate-spin rounded-full border-4 border-blue-100 border-t-blue-600" />
                  </div>
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
  );
};

export default ChatbotPage;
