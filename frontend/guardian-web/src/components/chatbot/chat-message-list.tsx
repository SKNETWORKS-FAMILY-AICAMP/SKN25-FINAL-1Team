import type { ChatCard, ChatMessage } from "../../hooks/use-chat-conversation";

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
}: {
  card: Extract<ChatCard, { kind: "slots" }>;
  isStreaming: boolean;
  onSendMessage: (content: string) => void;
  onOpenDatePicker: () => void;
}) => (
  <div className="w-full overflow-hidden rounded-3xl rounded-bl-lg border border-slate-200 bg-white shadow-sm">
    {card.slots.length > 0 && (
      <>
        <ul className="divide-y divide-slate-100">
          {card.slots.map((slot) => (
            <li
              key={slot.label}
              className="flex items-center justify-between gap-3 px-5 py-4"
            >
              <div className="min-w-0">
                <p className="text-sm font-extrabold text-slate-900">
                  {slot.monthDay} ({slot.weekday})
                </p>
                <p className="mt-0.5 text-xs font-semibold text-slate-500">
                  {slot.timeText}
                  <span className="mx-1.5 text-slate-300">|</span>
                  <span className="text-blue-600">{slot.durationText} 진료 예상</span>
                </p>
              </div>
              <button
                type="button"
                onClick={() => onSendMessage(slot.label)}
                disabled={isStreaming}
                className="shrink-0 rounded-xl bg-blue-600 px-4 py-2 text-xs font-extrabold text-white transition hover:bg-blue-700 disabled:opacity-50"
              >
                선택
              </button>
            </li>
          ))}
        </ul>
        <p className="px-5 pb-1 pt-2 text-[10px] font-medium text-slate-400">
          * 진료 시간은 예상치이며 실제 진료에 따라 달라질 수 있어요.
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
        📅 예약 가능한 날짜 보기
      </button>
    </div>
  </div>
);

/** 예약 확정 카드 */
const ConfirmationCard = ({
  card,
}: {
  card: Extract<ChatCard, { kind: "confirmation" }>;
}) => (
  <div className="w-full rounded-3xl rounded-bl-lg border border-emerald-100 bg-white px-5 py-4 shadow-sm">
    <p className="flex items-center gap-2 text-sm font-extrabold text-emerald-600">
      <span>✅</span> 예약이 확정되었어요!
    </p>
    <dl className="mt-3 space-y-2 text-sm font-semibold text-slate-700">
      <div className="flex items-center gap-2">
        <span>🐶</span>
        <span>{card.petName}</span>
      </div>
      <div className="flex items-center gap-2">
        <span>📅</span>
        <span>{card.dateText}</span>
      </div>
      <div className="flex items-center gap-2">
        <span>⏱️</span>
        <span>진료 예상 시간: {card.durationText}</span>
      </div>
      {card.hospitalName && (
        <div className="flex items-center gap-2">
          <span>🏥</span>
          <span>{card.hospitalName}</span>
        </div>
      )}
    </dl>
    <p className="mt-3 border-t border-slate-100 pt-3 text-xs font-medium text-slate-400">
      예약 변경/취소는 '예약 내역'에서 가능합니다.
    </p>
    <p className="mt-1 text-[11px] font-medium text-slate-400">
      * 진료 예상 시간은 예상치이며 실제 진료에 따라 달라질 수 있어요.
    </p>
  </div>
);

/** 내원 전 준비사항 카드 */
const InstructionsCard = ({
  card,
}: {
  card: Extract<ChatCard, { kind: "instructions" }>;
}) => (
  <div className="w-full rounded-3xl rounded-bl-lg border border-slate-200 bg-slate-50 px-5 py-4 shadow-sm">
    <p className="flex items-center gap-2 text-sm font-extrabold text-slate-800">
      <span>📋</span> 내원 전 준비사항
    </p>
    <ul className="mt-2.5 space-y-1.5">
      {card.items.map((item, idx) => (
        <li
          key={idx}
          className="flex gap-2 text-sm font-semibold leading-6 text-slate-600"
        >
          <span className="text-blue-500">•</span>
          <span>{item}</span>
        </li>
      ))}
    </ul>
  </div>
);

const ChatMessageList = ({
  messages,
  quickReplies,
  isStreaming,
  onSendMessage,
  onOpenDatePicker,
}: ChatMessageListProps) => {
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
                />
              )}
              {message.card.kind === "confirmation" && (
                <ConfirmationCard card={message.card} />
              )}
              {message.card.kind === "instructions" && (
                <InstructionsCard card={message.card} />
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
            {message.content || "응답을 작성하고 있어요..."}
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
                  alt="첨부 이미지"
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
              {reply}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
};

export default ChatMessageList;
