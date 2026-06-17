import { useRef, useState } from "react";

import { createFollowup } from "../api/followup-api";
import {
  getScheduleRecommendation,
  confirmSchedule,
} from "../api/schedule-api";
import type { RecommendSlotRaw } from "../api/schedule-api";
import { useTranslation } from "../i18n/language-context";
import type { Pet } from "../api/pets-api";
import type { ChatCard, ChatMessage, SlotOption } from "./use-chat-conversation";
import {
  formatChatDateTimeFull,
  formatChatDuration,
  formatChatMonthDay,
  formatChatTime,
  weekdayOf,
} from "../utils/chat-format";

export type PipelinePhase =
  | "chatting"
  | "scheduling"
  | "slot-selection"
  | "booking"
  | "confirmed"
  | "followup"
  | "followup-closed";

interface AgentPet {
  name: string;
  species: string;
  breed: string;
  age: number | string;
  gender: string;
  weight: number | string;
}

interface UseAgentPipelineParams {
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  setQuickReplies: React.Dispatch<React.SetStateAction<string[]>>;
  setIsStreaming: React.Dispatch<React.SetStateAction<boolean>>;
  // 선택된 병원 — 슬롯 조회·예약을 해당 병원으로 스코핑(다중 병원).
  hospitalId?: number | null;
}

const toPetPayload = (pet: Pet): AgentPet => {
  const age = pet.birth_date
    ? new Date().getFullYear() - new Date(pet.birth_date).getFullYear()
    : "?";
  return {
    name: pet.petname,
    species: pet.species || "dog",
    breed: pet.breed || "알 수 없음",
    age,
    gender: pet.gender || "미상",
    weight: pet.weight_kg ?? "?",
  };
};

const nextId = () => Date.now() + Math.random();

export const useAgentPipeline = ({
  setMessages,
  setQuickReplies,
  setIsStreaming,
  hospitalId,
}: UseAgentPipelineParams) => {
  const { lang, t } = useTranslation();
  const [phase, setPhase] = useState<PipelinePhase>("chatting");
  const [showDatePicker, setShowDatePicker] = useState(false);

  // Mutable refs — no re-render needed
  const triageResultRef = useRef<Record<string, unknown> | null>(null);
  const scheduleResultRef = useRef<Record<string, unknown> | null>(null);
  const currentPetRef = useRef<Pet | null>(null);
  const slotMapRef = useRef<Record<string, { date: string; time: string; doctorid: number; doctorName?: string }>>({});
  const emridRef = useRef<number | null>(null);
  const lastRequestRef = useRef<number>(0);
  const scheduleRequestRef = useRef<number>(0);

  const appendBot = (content: string) => {
    setMessages((prev) => [
      ...prev,
      { id: nextId(), role: "assistant" as const, content },
    ]);
  };

  const appendBotKey = (
    i18nKey: string,
    pipelineKey: ChatMessage["pipelineKey"],
    i18nVars?: Record<string, string | number>,
  ) => {
    setMessages((prev) => [
      ...prev,
      {
        id: nextId(),
        role: "assistant" as const,
        content: i18nKey,
        i18nKey,
        i18nVars,
        pipelineKey,
      },
    ]);
  };

  const appendCard = (card: ChatCard, pipelineKey?: ChatMessage["pipelineKey"]) => {
    setMessages((prev) => [
      ...prev,
      { id: nextId(), role: "assistant" as const, content: "", card, pipelineKey },
    ]);
  };

  // 로딩 말풍선 제거 — 결과(슬롯/확정)가 나오면 "찾는 중"·"예약 중"을 지운다
  const removeByPipelineKey = (key: NonNullable<ChatMessage["pipelineKey"]>) =>
    setMessages((prev) => prev.filter((message) => message.pipelineKey !== key));

  const clearScheduleArtifacts = () => {
    setMessages((prev) =>
      prev.filter(
        (message) =>
          message.pipelineKey !== "checking-slots" &&
          message.pipelineKey !== "slots-result" &&
          message.pipelineKey !== "slot-error" &&
          message.card?.kind !== "slots",
      ),
    );
  };

  /** 현재 slotMapRef로부터 슬롯 카드 옵션을 재구성(예약 실패 시 카드 재노출용) */
  const buildSlotOptions = (): SlotOption[] => {
    const durationMin = (scheduleResultRef.current?.estimated_duration_min as number) || 30;
    return Object.entries(slotMapRef.current).map(([label, s]) => {
      return {
        label,
        date: s.date,
        time: s.time,
        durationMin,
        doctorid: s.doctorid,
        doctorName: s.doctorName,
        monthDay: formatChatMonthDay(s.date, t),
        weekday: weekdayOf(s.date, lang),
        timeText: formatChatTime(s.time, t),
        durationText: formatChatDuration(durationMin, t),
      };
    });
  };

  // 백엔드 추천 슬롯(원시) → SlotOption + slotMap 등록 (라벨로 선택 라우팅)
  const toSlotOption = (
    s: RecommendSlotRaw,
    durationMin: number,
    slotMap: Record<string, { date: string; time: string; doctorid: number; doctorName?: string }>,
  ): SlotOption => {
    const time = s.start_time.slice(0, 5);
    const [, m, d] = s.date.split("-");
    const label = t("chatbot.slotLabel", { month: Number(m), day: Number(d), time });
    slotMap[label] = { date: s.date, time, doctorid: s.doctorid || 1, doctorName: s.doctor_name };
    return {
      label,
      date: s.date,
      time,
      durationMin,
      doctorid: s.doctorid,
      doctorName: s.doctor_name,
      monthDay: formatChatMonthDay(s.date, t),
      weekday: weekdayOf(s.date, lang),
      timeText: formatChatTime(time, t),
      durationText: formatChatDuration(durationMin, t),
    };
  };

  const startSchedulePhase = async (
    pet: Pet,
    collectedInfo: Record<string, unknown>,
    emrid?: number,
    _scheduleTaskId?: string, // (구) 서버 선실행 task_id — 현재 미사용
  ) => {
    triageResultRef.current = collectedInfo;
    currentPetRef.current = pet;
    emridRef.current = emrid ?? null;
    setPhase("scheduling");
    setIsStreaming(true);
    const requestId = ++scheduleRequestRef.current;
    clearScheduleArtifacts();
    appendBotKey("chatbot.checkingSlots", "checking-slots");

    try {
      // LangGraph(schedule): duration 산정(LLM) → 3모드 슬롯(결정론)을 한 번에 받음
      const resp = await getScheduleRecommendation({
        pet: toPetPayload(pet),
        triage: collectedInfo,
        hospitalid: hospitalId ?? undefined,
      });
      if (requestId !== scheduleRequestRef.current) return;
      removeByPipelineKey("checking-slots");  // 로딩 버블 제거

      const result = resp.result;
      const durationMin = result?.estimated_duration_min || 30;
      scheduleResultRef.current = result as unknown as Record<string, unknown>;

      // 3모드를 미리 SlotOption으로 변환 (칩 전환 시 재요청 없음)
      const recs = result?.recommendations;
      const slotMap: Record<string, { date: string; time: string; doctorid: number; doctorName?: string }> = {};
      const recommended = (recs?.recommended ?? []).map((s) => toSlotOption(s, durationMin, slotMap));
      const earliest = (recs?.earliest ?? []).map((s) => toSlotOption(s, durationMin, slotMap));
      const byDoctor = Object.entries(recs?.by_doctor ?? {}).map(([id, v]) => ({
        doctorid: Number(id),
        doctorName: v.doctor_name,
        slots: (v.slots ?? []).map((s) => toSlotOption(s, durationMin, slotMap)),
      }));
      slotMapRef.current = slotMap;

      if (recommended.length > 0 || earliest.length > 0) {
        appendBotKey("chatbot.slotsFound", "slots-result");
        appendCard(
          { kind: "slots", slots: recommended.length ? recommended : earliest, recommended, earliest, byDoctor },
          "slots-result",
        );
        setPhase("slot-selection");
      } else {
        // 슬롯을 못 찾아도 '날짜 보기'는 카드에서 항상 제공
        appendBotKey("chatbot.noSlotsPickDate", "slots-result");
        appendCard({ kind: "slots", slots: [] }, "slots-result");
        setPhase("slot-selection");
        setShowDatePicker(true);
      }
    } catch {
      if (requestId !== scheduleRequestRef.current) return;
      removeByPipelineKey("checking-slots");  // 로딩 버블 제거
      appendBotKey("chatbot.slotCheckRetry", "slot-error");
      appendCard({ kind: "slots", slots: [] }, "slot-error");
      setPhase("slot-selection");
      setShowDatePicker(true);
    } finally {
      if (requestId === scheduleRequestRef.current) setIsStreaming(false);
    }
  };

  const handleSlotSelect = async (label: string, _petId: number) => {
    const slot = slotMapRef.current[label];
    if (!slot) {
      return false;
    }

    setPhase("booking");
    setIsStreaming(true);
    appendBotKey("chatbot.processingBooking", "booking-status");  // 로딩 버블

    const emrid = emridRef.current;
    if (!emrid) {
      removeByPipelineKey("booking-status");  // 로딩 버블 제거
      appendBot(t("chatbot.noTriageData"));
      setPhase("chatting");
      setIsStreaming(false);
      return false;
    }

    try {
      const triage = triageResultRef.current;
      const duration = (scheduleResultRef.current?.estimated_duration_min as number) || 30;

      const resp = await confirmSchedule({
        emrid: emrid,
        doctorid: slot.doctorid,
        confirmed_time: `${slot.date}T${slot.time}:00+09:00`,
        duration_min: duration,
        hospitalid: hospitalId ?? undefined,
        // 재진입 복원용 — 확정 시 주의사항도 함께 저장
        pre_visit_instructions:
          (scheduleResultRef.current?.pre_visit_instructions as string[] | undefined) ?? [],
      });
      removeByPipelineKey("booking-status");  // 로딩 버블 제거

      if (resp.code === 200 || resp.code === 201) {
        const dateText = formatChatDateTimeFull(slot.date, slot.time, lang, t);

        // ① 예약 확정 카드
        appendCard({
          kind: "confirmation",
          petName: currentPetRef.current?.petname ?? t("chatbot.petFallback"),
          date: slot.date,
          time: slot.time,
          durationMin: duration,
          dateText,
          durationText: formatChatDuration(duration, t),
          hospitalName: resp.result?.hospital_name ?? undefined,
        });

        // ② 내원 전 준비사항 — 확정 카드 아래 별도 카드로 정리
        const instructions =
          (scheduleResultRef.current?.pre_visit_instructions as string[] | undefined) ?? [];
        if (instructions.length) {
          appendCard({ kind: "instructions", items: instructions });
        }

        // followup 활성 기준은 백엔드 can_followup(= triage.need_followup, '동적 증상군'
        // 단일 판정)과 일치시킨다. 예전 urgency<=2 fallback을 두면 라이브에선 켜지고
        // 재진입(can_followup)에선 꺼져 "나갔다 들어오면 막히는" 불일치가 생긴다.
        const needFollowup = Boolean(triage?.need_followup);
        if (needFollowup) {
          appendBot(
            t("chatbot.monitoring"),
          );
          setPhase("followup");
        } else {
          setPhase("confirmed");
        }
      } else {
        appendBot(
          t("chatbot.bookingError"),
        );
        appendCard({ kind: "slots", slots: buildSlotOptions() });
        setPhase("slot-selection");
      }
    } catch {
      removeByPipelineKey("booking-status");  // 로딩 버블 제거
      appendBot(t("chatbot.bookingError"));
      appendCard({ kind: "slots", slots: buildSlotOptions() });
      setPhase("slot-selection");
    } finally {
      setIsStreaming(false);
    }
    return true;
  };

  const handleFollowupMessage = async (content: string, images: string[] = []) => {
    const emrid = emridRef.current;
    if (!emrid || phase !== "followup") return;

    let messagesBackup: ChatMessage[] = [];
    setMessages((prev) => {
      messagesBackup = prev;
      return prev;
    });

    const requestId = ++lastRequestRef.current;
    setIsStreaming(true);

    try {
      // followup은 관련 보고에는 개별 응대를 하지 않는다 — 활성화 시 1회 안내만 남기고,
      // 이후 보고는 조용히 기록만 한다(수의사용 medical_summary는 서버에서 갱신).
      // 단, 경과와 무관한 입력(offtopic)에만 "관련 내용을 보내달라"는 안내를 띄운다.
      const resp = await createFollowup({ emrid, message: content, images });

      if (requestId !== lastRequestRef.current) {
        return; // Stale request, ignore
      }

      if (resp.result?.offtopic) {
        appendBot(t("chatbot.followupOfftopic"));
      }
    } catch (err) {
      if (requestId === lastRequestRef.current) {
        setMessages(messagesBackup); // Rollback to backup state
        appendBot(t("chatbot.recordFailed"));
      }
    } finally {
      if (requestId === lastRequestRef.current) {
        setIsStreaming(false);
      }
    }
  };

  /** 날짜 피커에서 선택한 슬롯으로 직접 예약 확정 */
  const handleManualSlotSelect = async (
    date: string,
    time: string,
    doctorid: number,
    label: string,
  ) => {
    setShowDatePicker(false);
    const emrid = emridRef.current;
    if (!emrid) {
      appendBot(t("chatbot.noTriageDataRestart"));
      return;
    }
    // 슬롯맵에 등록 후 기존 handleSlotSelect 재사용
    slotMapRef.current[label] = { date, time, doctorid };
    setMessages((prev) => [
      ...prev,
      { id: nextId(), role: "user" as const, content: label },
    ]);
    setQuickReplies([]);
    await handleSlotSelect(label, currentPetRef.current?.pet_id ?? 0);
  };

  const isSlotLabel = (label: string) => label in slotMapRef.current;

  const getSlotLabels = () => Object.keys(slotMapRef.current);

  /** 직접 날짜 선택 피커가 빈 슬롯을 조회할 때 쓸 진료 소요시간(분).
   *  확정(handleSlotSelect)과 동일한 값을 써야 추천 슬롯과 실제 예약이 어긋나지 않는다. */
  const getScheduleDurationMin = () =>
    (scheduleResultRef.current?.estimated_duration_min as number) || 30;

  const resetPipeline = () => {
    setPhase("chatting");
    setShowDatePicker(false);
    scheduleRequestRef.current += 1;
    triageResultRef.current = null;
    scheduleResultRef.current = null;
    currentPetRef.current = null;
    slotMapRef.current = {};
    emridRef.current = null;
  };

  const restoreFollowupPhase = (emrid: number) => {
    emridRef.current = emrid;
    setPhase("followup");
    appendBotKey("chatbot.restoreFollowup", "followup-restore");
  };

  // 경과보고 마감(진료 시작 시간 경과) 세션 재진입 — 입력창 대신 마감 안내만 노출.
  const restoreFollowupClosedPhase = (emrid: number) => {
    emridRef.current = emrid;
    setPhase("followup-closed");
  };

  // 일반(followup 미활성) 예약 완료 세션 재진입 — 입력 대신 '상담 완료' 안내만 노출.
  const restoreConfirmedPhase = (emrid: number) => {
    emridRef.current = emrid;
    setPhase("confirmed");
  };

  return {
    phase,
    showDatePicker,
    setShowDatePicker,
    isSlotLabel,
    getSlotLabels,
    getScheduleDurationMin,
    startSchedulePhase,
    handleSlotSelect,
    handleManualSlotSelect,
    handleFollowupMessage,
    resetPipeline,
    restoreFollowupPhase,
    restoreFollowupClosedPhase,
    restoreConfirmedPhase,
  };
};
