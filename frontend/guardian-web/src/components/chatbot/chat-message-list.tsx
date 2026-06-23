import { memo, useEffect, useRef, useState } from "react";

import type { ChatCard, ChatMessage, SlotOption } from "../../hooks/use-chat-conversation";
import { useTranslation } from "../../i18n/language-context";
import { useDynamicTranslation, type TranslationStatus } from "../../i18n/use-dynamic-translation";
import {
  formatChatDateTimeFull,
  formatChatDuration,
  formatChatMonthDay,
  formatChatTime,
  weekdayOf,
} from "../../utils/chat-format";
import { isVideoAttachment } from "../../utils/chat-attachment";
import type { Language } from "../../i18n/translations";

interface ChatMessageListProps {
  messages: ChatMessage[];
  quickReplies: string[];
  isStreaming: boolean;
  onSendMessage: (content: string, displayContent?: string) => void;
  onOpenDatePicker: () => void;
}

type SlotsT = (key: string, vars?: Record<string, string | number>) => string;

const sortSlots = (slots: SlotOption[]) =>
  [...slots].sort(
    (a, b) =>
      (a.date ?? "").localeCompare(b.date ?? "") ||
      (a.time ?? "").localeCompare(b.time ?? ""),
  );

/** 슬롯 한 줄 (시간 + 진료시간 + 원장명) */
const SlotRow = ({
  slot,
  showDoctor,
  isStreaming,
  onSendMessage,
  t,
  lang,
}: {
  slot: SlotOption;
  showDoctor: boolean;
  isStreaming: boolean;
  onSendMessage: (content: string) => void;
  t: SlotsT;
  lang: Language;
}) => {
  const monthDay = slot.date ? formatChatMonthDay(slot.date, t) : slot.monthDay;
  const weekday = slot.date ? weekdayOf(slot.date, lang) : slot.weekday;
  const timeText = slot.time ? formatChatTime(slot.time, t) : slot.timeText;
  const durationText = slot.durationMin
    ? formatChatDuration(slot.durationMin, t)
    : slot.durationText;
  return (
    <li className="flex items-center justify-between gap-3 px-5 py-4">
      <div className="min-w-0">
        <p className="text-sm font-extrabold text-slate-900">
          {monthDay} ({weekday})
        </p>
        <p className="mt-0.5 text-xs font-semibold text-slate-500">
          {timeText}
          <span className="mx-1.5 text-slate-300">|</span>
          <span className="text-blue-600">
            {durationText} {t("chatbot.durationEstimate")}
          </span>
          {showDoctor && slot.doctorName ? (
            <>
              <span className="mx-1.5 text-slate-300">|</span>
              <span className="text-slate-600">{slot.doctorName}</span>
            </>
          ) : null}
        </p>
      </div>
      <button
        type="button"
        onClick={() => onSendMessage(slot.label)}
        disabled={isStreaming}
        className="shrink-0 rounded-xl bg-blue-600 px-4 py-2 text-xs font-extrabold text-white transition hover:bg-blue-700 disabled:opacity-50"
      >
        {t("chatbot.cardSelect")}
      </button>
    </li>
  );
};

const Chip = ({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) => (
  <button
    type="button"
    onClick={onClick}
    className={[
      "rounded-full px-3 py-1.5 text-xs font-bold transition",
      active
        ? "bg-blue-600 text-white"
        : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50",
    ].join(" ")}
  >
    {children}
  </button>
);

/**
 * 예약 가능 시간 카드.
 * 백엔드가 3모드(recommended/earliest/byDoctor)를 미리 계산해 주면 칩 3개
 *   [추천시간 / 수의사별 / 가장 가까운 시간] 으로 보여준다 (수의사별은 원장 2명 이상일 때만).
 * 모드가 없으면(날짜 직접 선택 fallback) 기존처럼 card.slots 를 평평하게 나열.
 */
const SlotsCard = ({
  card,
  isStreaming,
  onSendMessage,
  onOpenDatePicker,
  t,
  lang,
}: {
  card: Extract<ChatCard, { kind: "slots" }>;
  isStreaming: boolean;
  onSendMessage: (content: string) => void;
  onOpenDatePicker: () => void;
  t: SlotsT;
  lang: Language;
}) => {
  const recommended = card.recommended ?? [];
  const earliest = card.earliest ?? [];
  const byDoctor = card.byDoctor ?? [];
  const hasModes = recommended.length > 0 || earliest.length > 0; // 새 추천 경로 여부
  const multiDoctor = byDoctor.length >= 2; // 수의사별 칩은 원장 2명 이상일 때만

  const [view, setView] = useState<{
    mode: "recommended" | "earliest" | "pick";
    doctorId?: number;
  }>({ mode: "recommended" });

  let visible: SlotOption[];
  let showDoctorChooser = false;
  if (!hasModes) {
    visible = sortSlots(card.slots); // fallback: 평평한 목록
  } else if (view.mode === "recommended") {
    visible = sortSlots(recommended.length ? recommended : earliest);
  } else if (view.mode === "earliest") {
    visible = sortSlots(earliest);
  } else {
    // 수의사별 — 원장 먼저 고르고 그 원장 슬롯 표시
    if (view.doctorId == null) {
      showDoctorChooser = true;
      visible = [];
    } else {
      visible = sortSlots(byDoctor.find((d) => d.doctorid === view.doctorId)?.slots ?? []);
    }
  }

  return (
    <div className="w-full overflow-hidden rounded-3xl rounded-bl-lg border border-slate-200 bg-white shadow-sm">
      {(card.slots.length > 0 || hasModes) && (
        <>
          {hasModes && (
            <div className="flex flex-wrap gap-2 px-5 pt-4">
              <Chip active={view.mode === "recommended"} onClick={() => setView({ mode: "recommended" })}>
                {t("chatbot.recommendedTime")}
              </Chip>
              {multiDoctor && (
                <Chip active={view.mode === "pick"} onClick={() => setView({ mode: "pick" })}>
                  {t("chatbot.byDoctor")}
                </Chip>
              )}
              <Chip active={view.mode === "earliest"} onClick={() => setView({ mode: "earliest" })}>
                {t("chatbot.earliestTime")}
              </Chip>
            </div>
          )}

          {showDoctorChooser ? (
            <div className="px-5 py-4">
              <p className="mb-2 text-xs font-bold text-slate-500">
                {t("chatbot.pickDoctorPrompt")}
              </p>
              <div className="flex flex-wrap gap-2">
                {byDoctor.map((d) => (
                  <button
                    key={d.doctorid}
                    type="button"
                    onClick={() => setView({ mode: "pick", doctorId: d.doctorid })}
                    className="rounded-xl border border-blue-200 bg-blue-50 px-3 py-2 text-xs font-bold text-blue-700 transition hover:bg-blue-100"
                  >
                    {d.doctorName ?? `#${d.doctorid}`}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {visible.map((slot) => (
                <SlotRow
                  key={slot.label}
                  slot={slot}
                  showDoctor={multiDoctor}
                  isStreaming={isStreaming}
                  onSendMessage={onSendMessage}
                  t={t}
                  lang={lang}
                />
              ))}
            </ul>
          )}

          {!showDoctorChooser && (
            <p className="px-5 pb-1 pt-2 text-[10px] font-medium text-slate-400">
              {t("chatbot.slotsDisclaimer")}
            </p>
          )}
        </>
      )}
      <div className="p-3">
        <button
          type="button"
          onClick={onOpenDatePicker}
          disabled={isStreaming}
          className="flex w-full items-center justify-center gap-2 rounded-2xl border border-blue-200 bg-blue-50/60 px-4 py-3 text-xs font-extrabold text-blue-600 transition hover:bg-blue-100 disabled:opacity-50"
        >
          {t("chatbot.viewAvailableDates")}
        </button>
      </div>
    </div>
  );
};

/** 예약 확정 카드 */
const ConfirmationCard = ({
  card,
  t,
  lang,
}: {
  card: Extract<ChatCard, { kind: "confirmation" }>;
  t: (key: string, vars?: Record<string, string | number>) => string;
  lang: Language;
}) => (
  <div className="w-full rounded-3xl rounded-bl-lg border border-emerald-100 bg-white px-5 py-4 shadow-sm">
    <p className="flex items-center gap-2 text-sm font-extrabold text-emerald-600">
      <span>✅</span> {t("chatbot.bookingConfirmed")}
    </p>
    <dl className="mt-3 space-y-2 text-sm font-semibold text-slate-700">
      <div className="flex items-center gap-2">
        <span>🐶</span>
        <span>{card.petName}</span>
      </div>
      <div className="flex items-center gap-2">
        <span>📅</span>
        <span>
          {card.date && card.time
            ? formatChatDateTimeFull(card.date, card.time, lang, t)
            : card.dateText}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <span>⏱️</span>
        <span>
          {t("chatbot.estimatedDuration")}{" "}
          {card.durationMin ? formatChatDuration(card.durationMin, t) : card.durationText}
        </span>
      </div>
      {card.hospitalName && (
        <div className="flex items-center gap-2">
          <span>🏥</span>
          <span>{card.hospitalName}</span>
        </div>
      )}
    </dl>
    <p className="mt-3 border-t border-slate-100 pt-3 text-xs font-medium text-slate-400">
      {t("chatbot.bookingChangeNote")}
    </p>
    <p className="mt-1 text-[11px] font-medium text-slate-400">
      {t("chatbot.bookingDisclaimer")}
    </p>
  </div>
);

/** 내원 전 준비사항 카드 */
const InstructionsCard = ({
  card,
  t,
  translateWithStatus,
}: {
  card: Extract<ChatCard, { kind: "instructions" }>;
  t: (key: string) => string;
  translateWithStatus: (text: string) => TranslationStatus;
}) => (
  <div className="w-full rounded-3xl rounded-bl-lg border border-slate-200 bg-slate-50 px-5 py-4 shadow-sm">
    <p className="flex items-center gap-2 text-sm font-extrabold text-slate-800">
      <span>📋</span> {t("chatbot.instructionsTitle")}
    </p>
    <ul className="mt-2.5 space-y-1.5">
      {card.items.map((item, idx) => {
        const { text, pending } = translateWithStatus(item);
        return (
          <li
            key={idx}
            className="flex gap-2 text-sm font-semibold leading-6 text-slate-600"
          >
            <span className="text-blue-500">•</span>
            <span>{pending ? <TranslatingDots /> : text}</span>
          </li>
        );
      })}
    </ul>
  </div>
);

/** 예약 내역 보기 카드 — 다가오는 확정 예약 요약 + 예약내역 탭 이동 버튼 */
const SchedulesCard = ({
  card,
  t,
  onSendMessage,
}: {
  card: Extract<ChatCard, { kind: "schedules" }>;
  t: (key: string) => string;
  onSendMessage: (content: string) => void;
}) => (
  <div className="w-full rounded-3xl rounded-bl-lg border border-slate-200 bg-slate-50 px-5 py-4 shadow-sm">
    <p className="flex items-center gap-2 text-sm font-extrabold text-slate-800">
      <span>📅</span> {t("chatbot.schedulesTitle")}
    </p>
    <ul className="mt-2.5 space-y-2">
      {card.items.map((item) => (
        <li
          key={item.schedule_id}
          className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm"
        >
          <p className="font-extrabold text-slate-800">{item.when ?? "-"}</p>
          <p className="mt-0.5 font-semibold text-slate-500">
            {[item.petName, item.doctorName, item.hospitalName]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </li>
      ))}
    </ul>
    <button
      type="button"
      onClick={() => onSendMessage("예약 내역 탭에서 보기")}
      className="mt-3 w-full rounded-xl bg-blue-600 py-2.5 text-sm font-bold text-white transition hover:bg-blue-700"
    >
      {t("chatbot.viewSchedulesTab")}
    </button>
  </div>
);

/** 번역 대기 중 표시하는 점 셋 shimmer — 한국어 원문 플래시 대신 노출. */
const TranslatingDots = () => (
  <span className="inline-flex items-center gap-1 align-middle">
    {[0, 1, 2].map((index) => (
      <span
        key={index}
        className="h-1.5 w-1.5 animate-pulse rounded-full bg-current opacity-50"
        style={{ animationDelay: `${index * 0.15}s` }}
      />
    ))}
  </span>
);

const ChatMessageList = ({
  messages,
  quickReplies,
  isStreaming,
  onSendMessage,
  onOpenDatePicker,
}: ChatMessageListProps) => {
  const { t } = useTranslation();
  const { translateWithStatus, ensureTranslated, lang } =
    useDynamicTranslation();
  // 스크롤 컨테이너(overflow-y-auto). main이 고정 높이(100dvh-4rem)라 모바일에서도
  // 창이 아니라 이 내부 div가 스크롤 주체다(측정으로 확인). 그래서 scrollIntoView로
  // 창까지 끌어당기지 않고 이 컨테이너의 scrollTop만 조정해 페이지/네비바 흔들림을 막는다.
  const scrollRef = useRef<HTMLDivElement | null>(null);
  // 바닥 센티넬(하단 여부 감지용 IntersectionObserver 타깃).
  const endRef = useRef<HTMLDivElement | null>(null);
  // 센티넬이 보이면 '하단에 있는' 상태(위로 스크롤해 과거를 보는 중이면 끌어올리지 않음).
  const atBottomRef = useRef(true);

  useEffect(() => {
    const end = endRef.current;
    const container = scrollRef.current;
    if (!end || !container) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        atBottomRef.current = entry.isIntersecting;
      },
      // ★ root를 스크롤 컨테이너로 지정 — 없으면 뷰포트 기준이라 '하단' 판정이 어긋나 자동스크롤이 안 됨.
      { root: container, rootMargin: "0px 0px 120px 0px" },
    );
    io.observe(end);
    return () => io.disconnect();
  }, []);

  // 새 메시지·스트리밍·리사이즈·이미지 로드 시 하단에 있으면 '즉시' 맨 아래로.
  // 컨테이너의 scrollTop만 직접 조정한다(창은 건드리지 않아 흔들림 없음).
  // 연속 갱신/리사이즈에서 애니메이션이 겹쳐 진동을 만드므로 instant로 둔다.
  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    const pin = () => {
      if (atBottomRef.current) container.scrollTop = container.scrollHeight;
    };
    pin();
    const ro = new ResizeObserver(pin);
    ro.observe(container); // 내용 높이 변화·리사이즈 추적
    return () => ro.disconnect();
  }, [messages, quickReplies, isStreaming]);

  // 언어 변경 시 메시지 본문·추천(pill)·준비사항을 선택 언어로 번역(req2/3).
  useEffect(() => {
    const texts: Array<string | null | undefined> = [];
    for (const message of messages) {
      if (message.i18nKey) continue;
      // 사용자가 직접 입력한 메시지는 원문 그대로 표시 — 번역 대상에서 제외.
      if (message.role === "user") continue;
      // 이미 현재 언어로 받은 본문은 번역 불필요.
      if (message.contentLang === lang) continue;
      const source = message.sourceContent ?? message.content;
      if (source) texts.push(source);
      if (message.card?.kind === "instructions") texts.push(...message.card.items);
    }
    texts.push(...quickReplies);
    ensureTranslated(texts);
  }, [messages, quickReplies, ensureTranslated, lang]);

  return (
    <div
      ref={scrollRef}
      className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-5 sm:p-7"
    >
      <div className="flex-1" />
      {messages.map((message) => {
        if (message.card) {
          return (
            <div key={message.id} className="max-w-[92%] self-start">
              {message.card.kind === "slots" && (
                <SlotsCard
                  card={message.card}
                  isStreaming={isStreaming}
                  onSendMessage={onSendMessage}
                  onOpenDatePicker={onOpenDatePicker}
                  t={t}
                  lang={lang}
                />
              )}
              {message.card.kind === "confirmation" && (
                <ConfirmationCard card={message.card} t={t} lang={lang} />
              )}
              {message.card.kind === "instructions" && (
                <InstructionsCard card={message.card} t={t} translateWithStatus={translateWithStatus} />
              )}
              {message.card.kind === "schedules" && (
                <SchedulesCard card={message.card} t={t} onSendMessage={onSendMessage} />
              )}
            </div>
          );
        }

        return (
          <div
            key={message.id}
            className={[
              "max-w-[82%] whitespace-pre-line rounded-3xl px-5 py-4 text-sm font-semibold leading-6",
              message.role === "user"
                ? "self-end rounded-br-lg bg-blue-600 text-white"
                : "rounded-bl-lg bg-slate-100 text-slate-700",
            ].join(" ")}
          >
            {(() => {
              if (message.i18nKey) return t(message.i18nKey, message.i18nVars);
              // 빈 말풍선 로딩 문구: 이미지 분석중📷 / 증상 검색중🔍 / 그 외 응답 작성중💬
              if (!message.content) {
                if (message.statusPhase === "image_analysis")
                  return `📷 ${t("chatbot.analyzingImage")}`;
                if (message.statusPhase === "searching")
                  return `🔍 ${t("chatbot.searchingSymptoms")}`;
                return `💬 ${t("chatbot.writingResponse")}`;
              }

              // 사용자 메시지: pill 번역본이 있으면 그걸 표시, 없으면 직접 입력 원문.
              if (message.role === "user") return message.displayContent ?? message.content;
              // 백엔드가 이미 현재 언어로 보내준 본문은 그대로 노출(플래시 없음).
              if (message.contentLang === lang) return message.content;
              const source = message.sourceContent ?? message.content;
              const { text, pending } = translateWithStatus(source);
              if (pending) return `💬 ${t("chatbot.writingResponse")}`;
              return text;
            })()}
            {message.attachmentUrl ? (
              isVideoAttachment(message.attachmentType, message.attachmentUrl) ? (
                <video
                  src={message.attachmentUrl}
                  className="mt-3 max-h-56 max-w-full rounded-2xl object-contain"
                  controls
                  playsInline
                />
              ) : (
                <img
                  src={message.attachmentUrl}
                  alt={t("chatbot.attachmentImageAlt")}
                  className="mt-3 max-h-56 rounded-2xl object-cover"
                  // 이미지가 늦게 로드되며 높이가 늘면, 하단에 있던 경우 한 번 더 맨 아래로 보정.
                  onLoad={() => {
                    const c = scrollRef.current;
                    if (c && atBottomRef.current) c.scrollTop = c.scrollHeight;
                  }}
                />
              )
            ) : null}
          </div>
        );
      })}
      {quickReplies.length > 0 && (() => {
        const translated = quickReplies.map((r) => translateWithStatus(r));
        if (translated.some((r) => r.pending)) return null;
        return (
          <div className="flex flex-wrap gap-2">
            {quickReplies.map((reply, i) => (
              <button
                key={reply}
                type="button"
                onClick={() => onSendMessage(reply, translated[i].text)}
                disabled={isStreaming}
                className="rounded-full border border-blue-200 bg-white px-4 py-2 text-xs font-extrabold text-blue-600 transition hover:bg-blue-50 disabled:opacity-60"
              >
                {translated[i].text}
              </button>
            ))}
          </div>
        );
      })()}
      <div ref={endRef} />
    </div>
  );
};

export default memo(ChatMessageList);
