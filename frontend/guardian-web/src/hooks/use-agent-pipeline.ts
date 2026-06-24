import { useRef, useState } from "react";

import { createFollowup } from "../api/followup-api";
import { ensureFollowupLimitNotice } from "../api/chat-api";
import {
  getScheduleRecommendation,
  confirmSchedule,
  updateSchedule,
  cancelSchedule,
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
  sessionId?: number | null;
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
  sessionId,
}: UseAgentPipelineParams) => {
  const { lang, t } = useTranslation();
  const [phase, setPhase] = useState<PipelinePhase>("chatting");
  const [showDatePicker, setShowDatePicker] = useState(false);

  // Mutable refs — no re-render needed
  const scheduleResultRef = useRef<Record<string, unknown> | null>(null);
  const currentPetRef = useRef<Pet | null>(null);
  // 슬롯 단계에서 병원을 바꾸면 같은 문진으로 새 병원 슬롯을 다시 추천하기 위해 보관.
  const triageInfoRef = useRef<Record<string, unknown> | null>(null);
  // 재예약(예약 변경) 흐름 표시 + 변경할 기존 예약 id — 슬롯 선택 시 confirm 대신 reschedule.
  const rebookingRef = useRef(false);
  const confirmedScheduleIdRef = useRef<number | null>(null);
  const slotMapRef = useRef<Record<string, { date: string; time: string; doctorid: number; doctorName?: string }>>({});
  const emridRef = useRef<number | null>(null);
  const lastRequestRef = useRef<number>(0);
  const scheduleRequestRef = useRef<number>(0);
  const limitNoticeTimerRef = useRef<number | null>(null);
  const limitNoticeShownRef = useRef(false);
  // 예약 확정 잠금 — 확정 진행 중/완료 시 중복 예약(슬롯·날짜피커 재클릭)을 막는다.
  // 새 슬롯 조회(runSchedule)나 새 상담(resetPipeline)에서만 다시 풀린다.
  const bookingLockRef = useRef(false);

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

  const scheduleFollowupLimitNotice = (confirmedTimeIso: string) => {
    if (limitNoticeTimerRef.current != null) {
      window.clearTimeout(limitNoticeTimerRef.current);
      limitNoticeTimerRef.current = null;
    }
    limitNoticeShownRef.current = false;
    const noticeAt = new Date(confirmedTimeIso).getTime() - 10 * 60 * 1000;
    const delay = Math.max(0, noticeAt - Date.now());
    limitNoticeTimerRef.current = window.setTimeout(() => {
      if (limitNoticeShownRef.current) return;
      limitNoticeShownRef.current = true;
      void (async () => {
        let notice = t("chatbot.followupLimitNotice");
        if (sessionId != null) {
          try {
            const resp = await ensureFollowupLimitNotice(sessionId);
            if (resp.result?.message) notice = resp.result.message;
          } catch {
            // 서버 동기화가 늦어져도 보호자 화면의 사전 안내는 유지한다.
          }
        }
        appendBot(notice);
      })();
      setQuickReplies(["병원 정보", "예약 내역", "내원 준비사항", "상태 계속 알려주기", "진료 때 전달할 내용 정리하기"]);
    }, delay);
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
    // 병원 변경 직후엔 hospitalId prop이 아직 갱신 전일 수 있어, 새 병원 id를 직접 받는다.
    hospitalOverride?: number,
  ) => {
    currentPetRef.current = pet;
    triageInfoRef.current = collectedInfo;
    emridRef.current = emrid ?? null;
    bookingLockRef.current = false;  // 새 슬롯 조회 → 예약 잠금 해제
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
        hospitalid: (hospitalOverride ?? hospitalId) ?? undefined,
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
    // 이미 예약을 확정했거나 확정 진행 중이면 중복 생성 차단(슬롯/날짜피커 재클릭·더블클릭).
    if (bookingLockRef.current) {
      return false;
    }
    const slot = slotMapRef.current[label];
    if (!slot) {
      return false;
    }
    bookingLockRef.current = true;

    setPhase("booking");
    setIsStreaming(true);
    appendBotKey("chatbot.processingBooking", "booking-status");  // 로딩 버블

    const emrid = emridRef.current;
    if (!emrid) {
      removeByPipelineKey("booking-status");  // 로딩 버블 제거
      appendBot(t("chatbot.noTriageData"));
      setPhase("chatting");
      setIsStreaming(false);
      bookingLockRef.current = false;  // 확정 못 했으니 잠금 해제(재시도 허용)
      return false;
    }

    try {
      const duration = (scheduleResultRef.current?.estimated_duration_min as number) || 30;
      const confirmedTime = `${slot.date}T${slot.time}:00+09:00`;

      // 재예약이면 기존 예약 시간만 변경(PATCH) — 원래 예약과 동일한 슬롯 UI, 확정만 reschedule.
      // 그 외엔 신규 확정(POST). 재예약은 이미 확정된 예약이 있어 confirm은 409가 나므로 분기 필수.
      const isRebook = rebookingRef.current && confirmedScheduleIdRef.current != null;
      let ok: boolean;
      let hospitalName: string | undefined;
      if (isRebook) {
        const r = await updateSchedule(confirmedScheduleIdRef.current as number, {
          confirmed_time: confirmedTime,
          duration_min: duration,
        });
        ok = r.code === 200 || r.code === 201;
      } else {
        const resp = await confirmSchedule({
          emrid: emrid,
          doctorid: slot.doctorid,
          confirmed_time: confirmedTime,
          duration_min: duration,
          hospitalid: hospitalId ?? undefined,
          // 재진입 복원용 — 확정 시 주의사항도 함께 저장
          pre_visit_instructions:
            (scheduleResultRef.current?.pre_visit_instructions as string[] | undefined) ?? [],
        });
        ok = resp.code === 200 || resp.code === 201;
        hospitalName = resp.result?.hospital_name ?? undefined;
        if (ok) confirmedScheduleIdRef.current = resp.result?.schedule_id ?? confirmedScheduleIdRef.current;
      }
      removeByPipelineKey("booking-status");  // 로딩 버블 제거

      if (ok) {
        rebookingRef.current = false;  // 재예약 완료 → 일반 흐름 복귀
        setShowDatePicker(false);  // 확정됐으니 날짜 피커 닫기(중복 선택 방지)
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
          hospitalName: hospitalName,
        });

        // ② 내원 전 준비사항 — 확정 카드 아래 별도 카드로 정리
        const instructions =
          (scheduleResultRef.current?.pre_visit_instructions as string[] | undefined) ?? [];
        if (instructions.length) {
          appendCard({ kind: "instructions", items: instructions });
        }

        // 예약 확정 후에는 항상 경과 보고(followup) 모드를 켠다.
        // need_followup 게이팅 폐기 — 라이브/재진입 모두 '예약 있으면 followup'으로 일관.
        appendBot(t("chatbot.monitoring"));
        scheduleFollowupLimitNotice(confirmedTime);
        setPhase("followup");
      } else {
        appendBot(
          t("chatbot.bookingError"),
        );
        appendCard({ kind: "slots", slots: buildSlotOptions() });
        setPhase("slot-selection");
        bookingLockRef.current = false;  // 확정 실패 → 잠금 해제(다시 선택 허용)
      }
    } catch {
      removeByPipelineKey("booking-status");  // 로딩 버블 제거
      appendBot(t("chatbot.bookingError"));
      appendCard({ kind: "slots", slots: buildSlotOptions() });
      setPhase("slot-selection");
      bookingLockRef.current = false;  // 확정 실패 → 잠금 해제(다시 선택 허용)
    } finally {
      setIsStreaming(false);
    }
    return true;
  };

  const handleFollowupMessage = async (content: string, images: string[] = []) => {
    const emrid = emridRef.current;
    if (!emrid || phase !== "followup") return;

    const requestId = ++lastRequestRef.current;
    setIsStreaming(true);
    // 로딩 문구 — 사진이면 '이미지 분석중', 아니면 '내용 확인중'. (응답 오면 제거)
    appendBotKey(images.length ? "chatbot.analyzingImage" : "chatbot.checkingFollowup", "followup-loading");

    try {
      // 경과 메시지는 서버에서 followup_filter가 분류·누적요약·이미지저장하고
      // 자연스러운 응답(reply)을 돌려준다. 그 응답을 말풍선으로 노출한다.
      const resp = await createFollowup({ emrid, message: content, images });

      if (requestId !== lastRequestRef.current) {
        return; // Stale request, ignore
      }
      removeByPipelineKey("followup-loading");  // 로딩 버블 제거
      // followup_filter가 띄운 후속 행동 pill(예: '더 빠른 시간 찾기', 의도 선택지) 노출.
      if (resp.result?.quick_replies?.length) setQuickReplies(resp.result.quick_replies);

      // 예약 취소 요청 → 확인(confirm) 후 실제 취소(cancelSchedule).
      if (resp.result?.cancel) {
        if (resp.result?.reply) appendBot(resp.result.reply);
        const sid = resp.result.cancel_schedule_id;
        if (sid != null && window.confirm("예약을 취소할까요? 취소하면 되돌릴 수 없어요.")) {
          try {
            await cancelSchedule(sid);
            appendBot("예약이 취소되었어요. 다시 예약하시려면 '예약 도와줘'라고 말씀해 주세요.");
          } catch {
            appendBot("예약 취소 중 문제가 생겼어요. 잠시 후 다시 시도해 주세요.");
          }
        } else if (sid != null) {
          appendBot("예약은 그대로 둘게요.");
        }
        return;
      }

      // 재예약 요청 → 백엔드가 emrid로 계산해 준 슬롯(rebook_slots)을 원래 예약과 '동일한 구조'로 렌더.
      // 슬롯 선택 시 handleSlotSelect가 confirm 대신 reschedule(PATCH)로 기존 예약 시간을 변경한다.
      // (세션 ref 상태와 무관하게 동작 — 재진입한 상담에서도 예약 변경이 된다.)
      if (resp.result?.rebook) {
        if (resp.result?.reply) appendBot(resp.result.reply);
        const rs = resp.result.rebook_slots;
        if (rs && rs.schedule_id != null) {
          rebookingRef.current = true;
          confirmedScheduleIdRef.current = rs.schedule_id;
          scheduleResultRef.current = rs as unknown as Record<string, unknown>;
          bookingLockRef.current = false;
          const durationMin = (rs.estimated_duration_min as number) || 30;
          const recs = (rs.recommendations ?? {}) as {
            recommended?: RecommendSlotRaw[];
            earliest?: RecommendSlotRaw[];
            by_doctor?: Record<string, { doctor_name?: string; slots?: RecommendSlotRaw[] }>;
          };
          const slotMap: Record<string, { date: string; time: string; doctorid: number; doctorName?: string }> = {};
          const recommended = (recs.recommended ?? []).map((s) => toSlotOption(s, durationMin, slotMap));
          const earliest = (recs.earliest ?? []).map((s) => toSlotOption(s, durationMin, slotMap));
          const byDoctor = Object.entries(recs.by_doctor ?? {}).map(([id, v]) => ({
            doctorid: Number(id),
            doctorName: v.doctor_name,
            slots: (v.slots ?? []).map((s) => toSlotOption(s, durationMin, slotMap)),
          }));
          slotMapRef.current = slotMap;
          if (recommended.length > 0 || earliest.length > 0) {
            appendCard(
              { kind: "slots", slots: recommended.length ? recommended : earliest, recommended, earliest, byDoctor },
              "slots-result",
            );
          } else {
            appendCard({ kind: "slots", slots: [] }, "slots-result");
            setShowDatePicker(true);
          }
          setPhase("slot-selection");
        } else {
          // 백엔드가 슬롯을 못 만들면(문진/예약 데이터 없음) 홈 화면 변경으로 안내.
          appendBot("예약 변경을 도와드릴게요. 홈 화면의 '예약하기'에서도 변경하실 수 있어요.");
        }
        return;
      }

      // 예약 내역 보기 → 다가오는 확정 예약 요약 카드 + 예약내역 탭 이동 pill.
      if (resp.result?.show_schedules) {
        if (resp.result?.reply) appendBot(resp.result.reply);
        const items = (resp.result.schedules ?? []).map((s) => ({
          schedule_id: s.schedule_id,
          when: s.when,
          petName: s.pet_name,
          doctorName: s.doctor_name,
          hospitalName: s.hospital_name,
          status: s.status,
        }));
        if (items.length) {
          appendCard({ kind: "schedules", items });
        } else {
          appendBot(t("chatbot.noUpcomingSchedules"));
        }
        return;
      }

      // 내원 전 준비사항 다시 보기 → 저장된 준비사항 카드를 다시 렌더.
      if (resp.result?.show_prep) {
        if (resp.result?.reply) appendBot(resp.result.reply);
        const items = resp.result.prep_instructions ?? [];
        if (items.length) {
          appendCard({ kind: "instructions", items });
        } else {
          appendBot(t("chatbot.noPrepInstructions"));
        }
        return;
      }

      // '문진 작성 후 예약하기' → 같은 챗에서 문진 모드로 전환(이후 메시지는 일반 챗 → 문진).
      if (resp.result?.start_triage) {
        if (resp.result?.reply) appendBot(resp.result.reply);
        setQuickReplies([]);
        setPhase("chatting");
        return;
      }

      // followup_filter가 만든 자연스러운 응답을 말풍선으로 노출.
      if (resp.result?.reply) {
        appendBot(resp.result.reply);
      } else if (resp.result?.offtopic) {
        appendBot(t("chatbot.followupOfftopic"));
      }
    } catch (err) {
      if (requestId === lastRequestRef.current) {
        removeByPipelineKey("followup-loading");  // 로딩 버블 제거
        // 서버가 예외를 반환해도 채팅방 자체는 닫지 않는다.
        const status = (err as { response?: { status?: number } })?.response?.status;
        if (status === 403) {
          setPhase("followup");
          appendBot(t("chatbot.followupClosed"));
          setQuickReplies(["병원 정보", "예약 내역", "내원 준비사항", "상태 계속 알려주기", "진료 때 전달할 내용 정리하기"]);
        } else {
          appendBot(t("chatbot.recordFailed"));
        }
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
    // 이미 확정했거나 확정 진행 중이면 메시지 말풍선도 띄우지 않고 무시(중복 클릭).
    // 가드가 handleSlotSelect 내부에만 있으면 메시지는 보내지고 답장만 안 와 어색하므로 append 앞에서 차단.
    if (bookingLockRef.current) return;
    const emrid = emridRef.current;
    if (!emrid) {
      appendBot(t("chatbot.noTriageDataRestart"));
      return;
    }
    // 슬롯맵에 등록 후 기존 handleSlotSelect 재사용.
    // 날짜 피커는 '모달에서 시간을 고른 동작'이라 채팅 발화가 아니다 — 유저 말풍선("6월 25일 10:00")을
    // 남기지 않고 바로 확정으로 보낸다(선택한 시간은 확정 카드에 그대로 표시됨). 추천 슬롯 칩 경로와 달리
    // 여기서 말풍선을 띄우면, 확정이 막히거나 라벨이 안 맞을 때 '답장 없는 빈 메시지'로 남는다.
    slotMapRef.current[label] = { date, time, doctorid };
    setQuickReplies([]);
    await handleSlotSelect(label, currentPetRef.current?.pet_id ?? 0);
  };

  const isSlotLabel = (label: string) => label in slotMapRef.current;

  // 예약 확정 완료/진행 중 여부 — 슬롯 재클릭 시 '메시지 전송' 자체를 막기 위해 호출부에서 사전 검사.
  const isBookingLocked = () => bookingLockRef.current;

  const getSlotLabels = () => Object.keys(slotMapRef.current);

  /** 직접 날짜 선택 피커가 빈 슬롯을 조회할 때 쓸 진료 소요시간(분).
   *  확정(handleSlotSelect)과 동일한 값을 써야 추천 슬롯과 실제 예약이 어긋나지 않는다. */
  const getScheduleDurationMin = () =>
    (scheduleResultRef.current?.estimated_duration_min as number) || 30;

  const resetPipeline = () => {
    setPhase("chatting");
    setShowDatePicker(false);
    bookingLockRef.current = false;  // 새 상담 → 예약 잠금 해제
    scheduleRequestRef.current += 1;
    scheduleResultRef.current = null;
    currentPetRef.current = null;
    slotMapRef.current = {};
    emridRef.current = null;
    if (limitNoticeTimerRef.current != null) {
      window.clearTimeout(limitNoticeTimerRef.current);
      limitNoticeTimerRef.current = null;
    }
    limitNoticeShownRef.current = false;
  };

  const restoreFollowupPhase = (emrid: number) => {
    emridRef.current = emrid;
    setPhase("followup");
    appendBotKey("chatbot.restoreFollowup", "followup-restore");
  };

  // legacy 제한 세션도 채팅은 계속 열어 둔다.
  const restoreFollowupClosedPhase = (emrid: number) => {
    emridRef.current = emrid;
    setPhase("followup");
  };

  // 일반(followup 미활성) 예약 완료 세션 재진입.
  const restoreConfirmedPhase = (emrid: number) => {
    emridRef.current = emrid;
    setPhase("confirmed");
  };

  // 예약(슬롯) 단계에서 상단 병원을 바꾸면 → 같은 문진으로 새 병원의 슬롯을 다시 추천한다.
  // 슬롯/예약 단계가 아니거나 문진정보가 없으면 아무것도 안 한다(false).
  const reselectHospital = async (newHospitalId: number): Promise<boolean> => {
    const pet = currentPetRef.current;
    const triage = triageInfoRef.current;
    if (!pet || !triage) return false;
    if (phase !== "scheduling" && phase !== "slot-selection" && phase !== "booking") return false;
    bookingLockRef.current = false; // 병원이 바뀌었으니 이전 예약 잠금 해제
    await startSchedulePhase(pet, triage, emridRef.current ?? undefined, undefined, newHospitalId);
    return true;
  };

  return {
    phase,
    showDatePicker,
    setShowDatePicker,
    isSlotLabel,
    isBookingLocked,
    getSlotLabels,
    getScheduleDurationMin,
    startSchedulePhase,
    reselectHospital,
    handleSlotSelect,
    handleManualSlotSelect,
    handleFollowupMessage,
    resetPipeline,
    restoreFollowupPhase,
    restoreFollowupClosedPhase,
    restoreConfirmedPhase,
  };
};
