import { useRef, useState } from "react";

import { runAgentTask, streamAgentResult } from "../api/agent-api";
import { createFollowup } from "../api/followup-api";
import {
  getAvailableScheduleSlots,
  confirmSchedule,
} from "../api/schedule-api";
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

const WINDOW_DAYS: Record<string, { start: number; count: number }> = {
  immediate: { start: 0, count: 1 },
  emergency_today: { start: 0, count: 1 },
  urgent_24h: { start: 1, count: 2 },
  semi_urgent_48h: { start: 2, count: 3 },
  routine_72h: { start: 3, count: 3 },
};

// 한국 법정 공휴일 집합 (주말 체크는 별도)
const KR_HOLIDAYS = new Set([
  "2026-01-01","2026-02-16","2026-02-17","2026-02-18","2026-03-01","2026-03-02",
  "2026-05-01","2026-05-05","2026-05-24","2026-05-25","2026-06-03","2026-06-06",
  "2026-07-17","2026-08-15","2026-08-17","2026-09-24","2026-09-25","2026-09-26",
  "2026-10-03","2026-10-05","2026-10-09","2026-12-25",
  "2027-01-01","2027-02-06","2027-02-07","2027-02-08","2027-02-09","2027-03-01",
  "2027-05-01","2027-05-05","2027-05-13","2027-06-06","2027-07-17","2027-08-15",
  "2027-08-16","2027-09-14","2027-09-15","2027-09-16","2027-10-03","2027-10-04",
  "2027-10-09","2027-10-11","2027-12-25","2027-12-27",
]);

const isClinicClosed = (dateStr: string): boolean => {
  const d = new Date(dateStr);
  const day = d.getDay(); // 0=Sun, 6=Sat
  return day === 0 || day === 6 || KR_HOLIDAYS.has(dateStr);
};

const getDatesForWindow = (slotWindow: string): string[] => {
  const { start, count } = WINDOW_DAYS[slotWindow] ?? { start: 1, count: 2 };
  const dates: string[] = [];
  const today = new Date();
  // 주말/공휴일 건너뛰며 영업일 기준으로 날짜 수집
  let scanned = 0;
  for (let i = start; dates.length < count && scanned < 30; i++, scanned++) {
    const d = new Date(today);
    d.setDate(d.getDate() + i);
    const ds = d.toISOString().split("T")[0];
    if (!isClinicClosed(ds)) dates.push(ds);
  }
  return dates;
};

/** 슬롯이 없을 때 최대 scanDays 영업일 내에서 추가 날짜 탐색 */
const getExtendedBusinessDates = (startOffset: number, scanDays = 21): string[] => {
  const dates: string[] = [];
  const today = new Date();
  for (let i = startOffset; dates.length < scanDays; i++) {
    const d = new Date(today);
    d.setDate(d.getDate() + i);
    const ds = d.toISOString().split("T")[0];
    if (!isClinicClosed(ds)) dates.push(ds);
  }
  return dates;
};

const nextId = () => Date.now() + Math.random();

export const useAgentPipeline = ({
  setMessages,
  setQuickReplies,
  setIsStreaming,
}: UseAgentPipelineParams) => {
  const { lang, t } = useTranslation();
  const [phase, setPhase] = useState<PipelinePhase>("chatting");
  const [internalAlertFlag, setInternalAlertFlag] = useState(false);
  const [escalationPromptVisible, setEscalationPromptVisible] = useState(false);
  const [guardianCareRecommendation, setGuardianCareRecommendation] = useState<string[]>([]);
  const [showDatePicker, setShowDatePicker] = useState(false);

  // Mutable refs — no re-render needed
  const triageResultRef = useRef<Record<string, unknown> | null>(null);
  const scheduleResultRef = useRef<Record<string, unknown> | null>(null);
  const currentPetRef = useRef<Pet | null>(null);
  const slotMapRef = useRef<Record<string, { date: string; time: string; doctorid: number }>>({});
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
        monthDay: formatChatMonthDay(s.date, t),
        weekday: weekdayOf(s.date, lang),
        timeText: formatChatTime(s.time, t),
        durationText: formatChatDuration(durationMin, t),
      };
    });
  };

  /** 주어진 날짜들에서 빈 슬롯을 limit 개까지 모은다. 추천/빠른조회 양쪽에서 재사용. */
  const collectSlots = async (
    datesToCheck: string[],
    limit: number,
    durationMin: number,
  ): Promise<{ date: string; start_time: string; doctorid?: number }[]> => {
    const collected: { date: string; start_time: string; doctorid?: number }[] = [];
    for (const date of datesToCheck) {
      if (collected.length >= limit) break;
      try {
        const resp = await getAvailableScheduleSlots({ date, duration_min: durationMin });
        if (resp.code === 200) {
          for (const slot of (resp.result ?? []).slice(0, 2)) {
            collected.push({ date, start_time: slot.start_time, doctorid: slot.doctorid });
            if (collected.length >= limit) break;
          }
        }
      } catch {
        // ignore per-date errors
      }
    }
    return collected;
  };

  const startSchedulePhase = async (
    pet: Pet,
    collectedInfo: Record<string, unknown>,
    emrid?: number,
    scheduleTaskId?: string,
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
      // 서버가 triage 완료 직후 schedule agent를 이미 실행해 둔 경우(schedule_task_id)
      // 그 결과를 재사용한다 → 중복 LLM 호출 제거 + 진단정보를 클라이언트로 내릴 필요 없음.
      // task_id가 없으면(구버전 호환) 클라이언트에서 직접 실행한다.
      let task_id = scheduleTaskId;
      if (!task_id) {
        const started = await runAgentTask("schedule", {
          pet: toPetPayload(pet),
          triage_result: collectedInfo,
        });
        task_id = started.task_id;
      }

      const raw = await streamAgentResult(task_id);
      if (requestId !== scheduleRequestRef.current) return;
      const schedRes = raw as {
        slot_window: string;
        estimated_duration_min: number;
        pre_visit_instructions: string[];
        priority_reason: string;
      } | null;

      if (!schedRes?.slot_window) {
        appendBotKey("chatbot.slotsLoadSlow", "slots-result");
        appendCard({ kind: "slots", slots: [] }, "slots-result");
        setPhase("slot-selection");
        setShowDatePicker(true);
        return;
      }

      scheduleResultRef.current = raw;

      // Collect available slots
      // 1차: urgency window 기준 영업일 탐색 — 추천 슬롯 3개 제시
      const dates = getDatesForWindow(schedRes.slot_window);
      let collected = await collectSlots(dates, 3, schedRes.estimated_duration_min);
      if (requestId !== scheduleRequestRef.current) return;

      // 2차: 1차 탐색에서 슬롯을 못 찾은 경우 최대 21영업일 확장 탐색
      if (collected.length === 0) {
        const windowStart = WINDOW_DAYS[schedRes.slot_window]?.start ?? 1;
        collected = await collectSlots(
          getExtendedBusinessDates(windowStart, 21),
          3,
          schedRes.estimated_duration_min,
        );
        if (requestId !== scheduleRequestRef.current) return;
      }

      const newSlotMap: Record<string, { date: string; time: string; doctorid: number }> = {};
      const slotOptions: SlotOption[] = [];
      const durationMin = schedRes.estimated_duration_min || 30;

      for (const s of collected) {
        const time = s.start_time.slice(0, 5);
        const [, m, d] = s.date.split("-");
        const label = t("chatbot.slotLabel", {
          month: Number(m),
          day: Number(d),
          time,
        });
        newSlotMap[label] = { date: s.date, time, doctorid: s.doctorid || 1 };
        slotOptions.push({
          label,
          date: s.date,
          time,
          durationMin,
          monthDay: formatChatMonthDay(s.date, t),
          weekday: weekdayOf(s.date, lang),
          timeText: formatChatTime(time, t),
          durationText: formatChatDuration(durationMin, t),
        });
      }

      slotMapRef.current = newSlotMap;

      // 내원 전 준비사항(pre_visit_instructions)은 여기서 보여주지 않고
      // 예약 확정 후 확정 카드 아래에 정리해서 노출한다(scheduleResultRef에 보관됨).
      if (slotOptions.length > 0) {
        appendBotKey("chatbot.slotsFound", "slots-result");
        appendCard({ kind: "slots", slots: slotOptions }, "slots-result");
        setPhase("slot-selection");
      } else {
        // 슬롯을 찾지 못했어도 '날짜 보기'는 카드에서 항상 제공
        appendBotKey("chatbot.noSlotsPickDate", "slots-result");
        appendCard({ kind: "slots", slots: [] }, "slots-result");
        setPhase("slot-selection");
        setShowDatePicker(true);
      }
    } catch {
      if (requestId !== scheduleRequestRef.current) return;
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
    appendBot(t("chatbot.processingBooking"));

    const emrid = emridRef.current;
    if (!emrid) {
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
      });

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
      const resp = await createFollowup({ emrid, message: content, images });
      
      if (requestId !== lastRequestRef.current) {
        return; // Stale request, ignore
      }

      const followupRes = resp.result;
      
      if (followupRes?.guardian_message) {
        appendBot(followupRes.guardian_message);
      } else {
        appendBot(t("chatbot.followupRecorded"));
      }

      if (followupRes?.followup_recommended) {
        setInternalAlertFlag(true);
        setEscalationPromptVisible(true);
        
        const actions = followupRes.recommended_actions || [];
        const actionLabels = actions.map((action: string) => {
          if (action === "call_hospital") return t("chatbot.actionCallHospital");
          if (action === "keep_schedule") return t("chatbot.actionKeepSchedule");
          if (action === "fast_booking") return t("chatbot.actionFastBooking");
          return action;
        }).filter((label: string, index: number, arr: string[]) => arr.indexOf(label) === index);
        
        setGuardianCareRecommendation(actionLabels);
        setQuickReplies(actionLabels);
      } else {
        setInternalAlertFlag(false);
        setEscalationPromptVisible(false);
        setGuardianCareRecommendation([]);
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

  return {
    phase,
    showDatePicker,
    setShowDatePicker,
    internalAlertFlag,
    escalationPromptVisible,
    guardianCareRecommendation,
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
  };
};
