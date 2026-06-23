import {
  useEffect,
  useCallback,
  useMemo,
  useRef,
  useState,
} from "react";
import { isAxiosError } from "axios";
import { useNavigate, useNavigationType, useSearchParams } from "react-router-dom";
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
import { useHospitalStore } from "../../stores/hospital-store";
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
import { useDynamicTranslation } from "../../i18n/use-dynamic-translation";

const SYMPTOM_PILLS = [
  "구토",
  "설사",
  "피부",
  "기침",
  "식욕저하",
  "눈물",
  "절뚝거림",
] as const;

const INITIAL_TITLE_EXCLUDED_PILLS = new Set([
  "증상을 말하고 예약할래요",
  "궁금한 게 있어요",
]);

// chatPhase: UI 레이어에서 사용하는 상태 머신
// IDLE / SYMPTOM_COLLECTING → pipeline.phase === "chatting"
// TRIAGE_RUNNING           → pipeline.phase === "scheduling"
// SLOT_RECOMMENDING        → pipeline.phase === "slot-selection"
// BOOKING_CONFIRMED        → pipeline.phase === "confirmed"
// FOLLOWUP_ACTIVE          → pipeline.phase === "followup"
// FOLLOWUP_CLOSED          → legacy 제한 안내. 채팅 입력은 닫지 않는다.
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
  if (isAxiosError<{ message?: string; detail?: string } | string>(error)) {
    const responseData = error.response?.data;

    if (typeof responseData === "string") {
      try {
        const parsedData = JSON.parse(responseData) as { message?: string; detail?: string };
        return parsedData.message || parsedData.detail || fallbackMessage;
      } catch {
        return fallbackMessage;
      }
    }

    // FastAPI는 사유를 detail 키로 반환 → message 없으면 detail 사용
    return responseData?.message || responseData?.detail || fallbackMessage;
  }

  return fallbackMessage;
};

const formatDateToYyyyMmDd = (date: Date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
};

const buildTemporaryHistoryTitle = (content: string) => {
  const normalized = content.replace(/\s+/g, " ").trim();
  const includesAny = (keywords: string[]) =>
    keywords.some((keyword) => normalized.includes(keyword));
  const matchesAny = (patterns: RegExp[]) =>
    patterns.some((pattern) => pattern.test(normalized));

  const symptomTitles = [
    { title: "구토/설사 상담", keywords: ["구토", "토해", "토하", "토", "설사", "묽은 변"] },
    { title: "기침/호흡 상담", keywords: ["기침", "숨", "호흡", "재채기", "콧물"] },
    { title: "피부/가려움 상담", keywords: ["피부", "가려", "긁", "발진", "털", "탈모"] },
    { title: "눈/귀 증상 상담", keywords: ["눈", "눈물", "귀", "귀지", "충혈"] },
    { title: "보행/통증 상담", keywords: ["절뚝", "다리", "못 걸", "통증", "아파"] },
    {
      title: "식욕 변화 상담",
      keywords: ["식욕", "밥", "사료", "간식", "입맛", "안 먹", "못 먹", "덜 먹", "많이 먹", "배고", "허기", "기운", "무기력"],
    },
  ];
  const matchedSymptom = symptomTitles.find(({ keywords }) => includesAny(keywords));
  if (matchedSymptom) return matchedSymptom.title;

  const asksHospital = includesAny(["병원", "주소", "위치", "전화", "번호", "운영", "시간", "휴진", "수의사", "원장"]);
  if (asksHospital) {
    const parts: string[] = [];
    if (includesAny(["주소", "위치", "어디", "찾아", "오시는", "길"])) parts.push("주소");
    if (includesAny(["전화", "번호", "연락", "문의"])) parts.push("전화");
    if (includesAny(["운영", "시간", "몇 시", "몇시", "휴진", "점심", "오늘"])) parts.push("운영시간");
    if (includesAny(["수의사", "원장", "선생님", "의사", "담당"])) parts.push("수의사");
    if (parts.length > 0) return `병원 ${parts.slice(0, 2).join("/")} 문의`;
    return "병원 정보 문의";
  }

  if (includesAny(["예약", "일정", "진료 가능", "가능한 시간"])) return "예약 문의";
  if (includesAny(["검진", "예방접종", "접종"])) return "검진/접종 문의";
  if (
    includesAny(["애가", "아이가", "강아지", "고양이", "냥이", "댕댕이", "반려동물", "우리 애"]) ||
    matchesAny([/아파(?:요|해)?/, /이상해(?:요)?/, /불편해(?:요)?/, /힘들어해(?:요)?/])
  ) {
    return "증상 상담";
  }

  const maxLength = 18;
  if (normalized.length <= maxLength) return normalized;
  return `${normalized.slice(0, maxLength).trimEnd()}...`;
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

const ChevronLeftIcon = () => (
  <svg viewBox="0 0 24 24" className="h-5 w-5 shrink-0" fill="none" aria-hidden="true">
    <path
      d="M15 18l-6-6 6-6"
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
  const { t } = useTranslation();
  const { translate, ensureTranslated } = useDynamicTranslation();
  const navigate = useNavigate();
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
  // 선택 병원 — 전역 store 단일 소스. 병원탭/예약 모달과 현재 병원 공유.
  const myHospitals = useHospitalStore((state) => state.myHospitals);
  const currentHospitalId = useHospitalStore((state) => state.currentHospitalId);
  const setCurrentHospital = useHospitalStore((state) => state.setCurrent);
  const [selectedHospitalId, setSelectedHospitalId] = useState<number | null>(currentHospitalId);
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
    setCurrentHospital(id);
    // 예약(슬롯) 단계에서 병원을 바꾸면 → 그 병원 기준으로 슬롯을 다시 추천한다.
    // (슬롯 단계가 아니면 reselectHospital이 내부에서 무시함)
    void pipeline.reselectHospital(id);
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
    onTitleUpdate: (sessionId, title) => updateChatHistoryTitle(sessionId, title),
  });

  const pipeline = useAgentPipeline({
    setMessages,
    setQuickReplies,
    setIsStreaming,
    hospitalId: selectedHospitalId,
    sessionId: session?.session_id ?? null,
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
    hasMoreHistories,
    isLoadingMoreHistories,
    loadMoreChatHistories,
    resetSessionStateForPetChange,
    closeActiveSession,
    handleCreateSession,
    handleSelectHistory,
    handleDeleteHistory,
    refreshChatHistories,
    updateChatHistoryKeywords,
    updateChatHistoryTitle,
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
      // 인사말은 restoredMessages 맨 앞에 이미 포함됨(복원 매핑에서 prepend)
      setMessages(restoredMessages);
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

  // 채팅 제목 번역: chatHistories에 title이 생기거나 언어가 바뀔 때 일괄 번역 큐에 등록.
  useEffect(() => {
    const titles = chatHistories.flatMap((h) => (h.title?.trim() ? [h.title.trim()] : []));
    if (titles.length > 0) ensureTranslated(titles);
  }, [chatHistories, ensureTranslated]);

  // 상담 제목 = 완료 시 생성된 요약 title 우선(번역 적용), 없으면 기존 keywords 표시(하위호환).
  const getHistoryTitle = useCallback(
    (history: ChatSessionHistory) => {
      const title = history.title?.trim();
      if (title) return translate(title) || title;
      const keywords = history.keywords
        .map((keyword) => keyword.trim())
        .filter((keyword) => keyword && keyword.length <= 24)
        .slice(0, 3);
      return keywords.length > 0 ? keywords.join(", ") : t("chatbot.historyDefaultTitle");
    },
    [t, translate],
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

  // 모바일 드릴다운 — 한 번에 한 패널만 보여준다.
  // 채팅 활성(세션/히스토리/생성·로드중) → "chat", 펫 선택됨 → "sessions", 그 외 → "pets".
  // lg(데스크톱) 이상에서는 무시되고 3단 그리드가 모두 표시된다.
  const hasActiveChat =
    Boolean(session) ||
    selectedHistoryId !== null ||
    creatingPetId !== null ||
    isLoadingHistoryMessages;
  const mobilePane: "pets" | "sessions" | "chat" = hasActiveChat
    ? "chat"
    : selectedPetId !== null
      ? "sessions"
      : "pets";

  // 채팅 → 목록: 열린 세션만 닫고 펫/히스토리 목록은 유지.
  const handleBackToSessions = () => {
    closeActiveSession();
    if (selectedPetId !== null) {
      writeActiveChatSession(selectedPetId, null);
    }
  };

  // 목록 → 펫 선택: 펫 선택을 해제한다.
  const handleBackToPets = () => {
    closeActiveSession();
    setSelectedPetId(null);
    clearActiveChatSession();
  };

  // 통합 메시지 전송 핸들러 — phase에 따라 분기
  const handleSendCombined = async (content: string, displayContent?: string) => {
    const trimmed = content.trim();
    // 첨부가 있으면 설명 텍스트 필수(영상 컷 단위라 맥락 보강 → off-topic 오인 방지).
    // 첨부가 없는 일반 메시지도 텍스트가 있어야 전송.
    if (!trimmed || isStreaming || isUploadingAttachment) return;

    // 예약 확정 후엔 phase가 followup으로 넘어가지만, 이전 추천 슬롯 카드의 '선택' 칩은 화면에 남아 클릭된다.
    // 슬롯 라벨("6월 24일 13:00")은 followup 메시지로 보낼 값이 아니므로, slot-selection이 아닐 때의
    // 슬롯 라벨 클릭은 followup 분기로 새어 메시지가 전송되기 전에 입구에서 무시한다.
    if (pipeline.phase !== "slot-selection" && pipeline.isSlotLabel(trimmed)) return;

    if (pipeline.phase === "slot-selection") {
      // 이미 예약을 확정했거나 확정 진행 중인데 옛 슬롯 버튼을 다시 누른 경우 —
      // 메시지 말풍선도 띄우지 않고 무시(답장 없는 빈 메시지 방지).
      if (pipeline.isSlotLabel(trimmed) && pipeline.isBookingLocked()) return;
      // 슬롯 버튼 클릭 또는 텍스트 입력
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now(),
          role: "user" as const,
          content: trimmed,
          displayContent: displayContent?.trim() || undefined,
        },
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

    if (pipeline.phase === "followup" || pipeline.phase === "followup-closed") {
      // followup_filter가 띄운 '동작' pill — 백엔드 전송 없이 프론트에서 해당 화면으로 이동.
      //  · 새 예약하기/바로 예약하기 → 홈의 '예약하기'(검진예약 모달) 자동 오픈
      //  · 예약 내역 탭에서 보기 → 예약 내역 페이지
      if (trimmed === "새 예약하기" || trimmed === "바로 예약하기") {
        navigate(selectedPetId ? `/home?reserve=${selectedPetId}` : "/home");
        return;
      }
      if (trimmed === "예약 내역 탭에서 보기") {
        navigate("/reservations");
        return;
      }
      // 경과 모니터링 메시지 — 첨부 이미지가 있으면 함께 전송하고 대화에도 노출한다.
      const att = pendingAttachment;
      const images = att?.cloudfrontUrl ? [att.cloudfrontUrl] : [];
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now(),
          role: "user" as const,
          content: trimmed,
          displayContent: displayContent?.trim() || undefined,
          attachmentUrl: att?.cloudfrontUrl,
          attachmentType: att?.contentType,
        },
      ]);
      setQuickReplies([]);
      clearPendingAttachment();
      await pipeline.handleFollowupMessage(trimmed, images);
      return;
    }

    if (pipeline.phase === "confirmed") return; // 예약 없는 완료 상태 — 입력 차단

    // 일반 트리아지 채팅
    if (
      session &&
      !selectedHistory?.title?.trim() &&
      !INITIAL_TITLE_EXCLUDED_PILLS.has(trimmed) &&
      !messages.some((message) => message.role === "user")
    ) {
      updateChatHistoryTitle(session.session_id, buildTemporaryHistoryTitle(trimmed));
    }
    await handleSendMessage(trimmed, displayContent);
  };

  // 메모된 자식들에 넘길 안정 콜백 — latest-ref로 identity를 고정해 React.memo 유지.
  const stableSelectPet = useStableCallback(handleSelectPet);
  const stableSendCombined = useStableCallback((content: string, displayContent?: string) => {
    void handleSendCombined(content, displayContent);
  });
  const stableOpenDatePicker = useStableCallback(() => {
    pipeline.setShowDatePicker(true);
  });
  const stableCreateSession = useStableCallback(handleCreateSession);
  const stableSelectHistory = useStableCallback(handleSelectHistory);
  const stableDeleteHistory = useStableCallback(handleDeleteHistory);

  return (
    <main data-tour="guardian-chatbot" className="mx-auto flex h-[calc(100dvh-4rem)] min-h-0 w-full max-w-[1200px] flex-col px-4 pt-6 pb-6 sm:px-6 sm:pt-10">
        <div className="mb-4 shrink-0 flex items-end justify-between sm:mb-6">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">
              {t("chatbot.title")}
            </h1>
            <p className="mt-0.5 text-sm text-slate-500">
              {t("chatbot.subtitle")}
            </p>
          </div>
        </div>
        <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-slate-100 bg-white shadow-sm">

          {errorMessage ? (
            <div className="border-b border-rose-100 bg-rose-50 px-5 py-3 text-sm font-bold text-rose-600 sm:px-7">
              {errorMessage}
            </div>
          ) : null}

          <div className="flex min-h-0 flex-1 flex-col lg:grid lg:grid-cols-[200px_200px_1fr]">
            {/* 패널 1 — 반려동물 (모바일: pets 단계에서만) */}
            <div
              className={`${mobilePane === "pets" ? "flex" : "hidden"} min-h-0 flex-1 flex-col lg:flex lg:min-h-0 lg:flex-none`}
            >
              <PetSelector
                pets={pets}
                selectedPetId={selectedPetId}
                isLoadingPets={isLoadingPets}
                onSelectPet={stableSelectPet}
                getProfileImage={getProfileImage}
              />
            </div>

            {/* 패널 2 — 상담 기록 (모바일: sessions 단계에서만, 뒤로가기 포함) */}
            <div
              className={`${mobilePane === "sessions" ? "flex" : "hidden"} min-h-0 flex-1 flex-col lg:flex lg:min-h-0 lg:flex-none`}
            >
              <button
                type="button"
                onClick={handleBackToPets}
                className="flex h-12 shrink-0 items-center gap-1 border-b border-slate-100 px-3 text-sm font-bold text-slate-600 transition hover:bg-slate-50 lg:hidden"
              >
                <ChevronLeftIcon />
                <span className="truncate">{selectedPet?.petname ?? t("chatbot.pets")}</span>
              </button>
              <ChatSessionList
                selectedPet={selectedPet}
                selectedPetId={selectedPetId}
                isLoadingPets={isLoadingPets}
                chatHistories={chatHistories}
                selectedHistoryId={selectedHistoryId}
                isLoadingHistories={isLoadingHistories}
                hasMoreHistories={hasMoreHistories}
                isLoadingMoreHistories={isLoadingMoreHistories}
                onLoadMoreHistories={loadMoreChatHistories}
                creatingPetId={creatingPetId}
                onCreateSession={stableCreateSession}
                onSelectHistory={stableSelectHistory}
                onDeleteHistory={stableDeleteHistory}
                getHistoryTitle={getHistoryTitle}
              />
            </div>

            {/* 패널 3 — 채팅 (모바일: chat 단계에서만, 뒤로가기 포함) */}
            <div
              className={`${mobilePane === "chat" ? "flex" : "hidden"} min-h-0 flex-1 flex-col lg:flex lg:min-h-0 lg:flex-none`}
            >
              <button
                type="button"
                onClick={handleBackToSessions}
                className="flex h-12 shrink-0 items-center gap-1 border-b border-slate-100 px-3 text-sm font-bold text-slate-600 transition hover:bg-slate-50 lg:hidden"
              >
                <ChevronLeftIcon />
                <span className="truncate">{t("chatbot.history")}</span>
              </button>
            <section className="relative flex min-h-0 flex-1 flex-col overflow-hidden bg-white">
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
                      // 재진입한 followup 세션에서도 pill(의도 선택·재예약·슬롯)을 띄우고 클릭되게 한다.
                      quickReplies={
                        pipeline.phase === "followup" || pipeline.phase === "slot-selection" || pipeline.phase === "followup-closed"
                          ? quickReplies
                          : EMPTY_QUICK_REPLIES
                      }
                      isStreaming={isStreaming}
                      onSendMessage={
                        pipeline.phase === "followup" || pipeline.phase === "slot-selection" || pipeline.phase === "followup-closed"
                          ? stableSendCombined
                          : noop
                      }
                      onOpenDatePicker={
                        pipeline.phase === "followup" || pipeline.phase === "slot-selection"
                          ? stableOpenDatePicker
                          : noop
                      }
                    />
                  )}

                  {/* 재예약(재진입) 시 직접 날짜 선택 피커 — 라이브 흐름과 동일 */}
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

                  {(pipeline.phase === "followup" || pipeline.phase === "followup-closed") && (
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
          </div>
        </section>
      </main>
  );
};

export default ChatbotPage;
