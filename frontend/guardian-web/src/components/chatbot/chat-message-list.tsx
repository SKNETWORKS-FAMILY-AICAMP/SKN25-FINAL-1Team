import { useEffect, useRef } from "react";

import type { ChatCard, ChatMessage } from "../../hooks/use-chat-conversation";
import { useTranslation } from "../../i18n/language-context";
import { useDynamicTranslation } from "../../i18n/use-dynamic-translation";
import {
  formatChatDateTimeFull,
  formatChatDuration,
  formatChatMonthDay,
  formatChatTime,
  weekdayOf,
} from "../../utils/chat-format";
import type { Language } from "../../i18n/translations";

interface ChatMessageListProps {
  messages: ChatMessage[];
  quickReplies: string[];
  isStreaming: boolean;
  onSendMessage: (content: string) => void;
  onOpenDatePicker: () => void;
}

/** 예약 가능 시간 카드 — 슬롯 목록 + '예약 가능한 날짜 보기' 버튼 */
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
  t: (key: string, vars?: Record<string, string | number>) => string;
  lang: Language;
}) => (
  <div className="w-full overflow-hidden rounded-3xl rounded-bl-lg border border-slate-200 bg-white shadow-sm">
    {card.slots.length > 0 && (
      <>
        <ul className="divide-y divide-slate-100">
          {card.slots.map((slot) => {
            const monthDay = slot.date
              ? formatChatMonthDay(slot.date, t)
              : slot.monthDay;
            const weekday = slot.date ? weekdayOf(slot.date, lang) : slot.weekday;
            const timeText = slot.time ? formatChatTime(slot.time, t) : slot.timeText;
            const durationText = slot.durationMin
              ? formatChatDuration(slot.durationMin, t)
              : slot.durationText;
            return (
              <li
                key={slot.label}
                className="flex items-center justify-between gap-3 px-5 py-4"
              >
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
          })}
        </ul>
        <p className="px-5 pb-1 pt-2 text-[10px] font-medium text-slate-400">
          {t("chatbot.slotsDisclaimer")}
        </p>
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
  translate,
}: {
  card: Extract<ChatCard, { kind: "instructions" }>;
  t: (key: string) => string;
  translate: (text: string) => string;
}) => (
  <div className="w-full rounded-3xl rounded-bl-lg border border-slate-200 bg-slate-50 px-5 py-4 shadow-sm">
    <p className="flex items-center gap-2 text-sm font-extrabold text-slate-800">
      <span>📋</span> {t("chatbot.instructionsTitle")}
    </p>
    <ul className="mt-2.5 space-y-1.5">
      {card.items.map((item, idx) => (
        <li
          key={idx}
          className="flex gap-2 text-sm font-semibold leading-6 text-slate-600"
        >
          <span className="text-blue-500">•</span>
          <span>{translate(item)}</span>
        </li>
      ))}
    </ul>
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
  const { translate, translateWithStatus, ensureTranslated, lang } =
    useDynamicTranslation();
  const scrollAnchorRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, quickReplies, isStreaming]);

  // 언어 변경 시 메시지 본문·추천(pill)·준비사항을 선택 언어로 번역(req2/3).
  useEffect(() => {
    const texts: Array<string | null | undefined> = [];
    for (const message of messages) {
      if (message.i18nKey) continue;
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
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-5 sm:p-7">
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
                <InstructionsCard card={message.card} t={t} translate={translate} />
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
              if (!message.content) return t("chatbot.writingResponse");
              // 백엔드가 이미 현재 언어로 보내준 본문은 그대로 노출(플래시 없음).
              if (message.contentLang === lang) return message.content;
              const source = message.sourceContent ?? message.content;
              const { text, pending } = translateWithStatus(source);
              return pending ? <TranslatingDots /> : text;
            })()}
            {message.attachmentUrl ? (
              message.attachmentType === "video/mp4" ? (
                <video
                  src={message.attachmentUrl}
                  className="mt-3 max-h-56 rounded-2xl"
                  controls
                />
              ) : (
                <img
                  src={message.attachmentUrl}
                  alt={t("chatbot.attachmentImageAlt")}
                  className="mt-3 max-h-56 rounded-2xl object-cover"
                />
              )
            ) : null}
          </div>
        );
      })}
      {quickReplies.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {quickReplies.map((reply) => (
            <button
              key={reply}
              type="button"
              onClick={() => onSendMessage(reply)}
              disabled={isStreaming}
              className="rounded-full border border-blue-200 bg-white px-4 py-2 text-xs font-extrabold text-blue-600 transition hover:bg-blue-50 disabled:opacity-60"
            >
              {translate(reply)}
            </button>
          ))}
        </div>
      ) : null}
      <div ref={scrollAnchorRef} />
    </div>
  );
};

export default ChatMessageList;
