import { memo, useState, type ChangeEvent, type FormEvent, type RefObject } from "react";

import type { PendingAttachment } from "../../hooks/use-chat-upload";
import { useTranslation } from "../../i18n/language-context";

const MicrophoneIcon = () => (
  <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" aria-hidden="true">
    <path
      d="M12 14.5a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v5.5a3 3 0 0 0 3 3Z"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      d="M18.5 11.5a6.5 6.5 0 0 1-13 0M12 18v3M9 21h6"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

const SendIcon = () => (
  <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" aria-hidden="true">
    <path d="M5 12 19 5l-4 14-3-6-7-1Z" fill="currentColor" />
  </svg>
);

interface ChatInputBoxProps {
  fileInputRef: RefObject<HTMLInputElement>;
  pendingAttachment: PendingAttachment | null;
  isStreaming: boolean;
  isUploadingAttachment: boolean;
  onClearPendingAttachment: () => void;
  onSelectAttachment: (event: ChangeEvent<HTMLInputElement>) => void;
  onSubmitMessage: (value: string) => void;
}

const ChatInputBox = ({
  fileInputRef,
  pendingAttachment,
  isStreaming,
  isUploadingAttachment,
  onClearPendingAttachment,
  onSelectAttachment,
  onSubmitMessage,
}: ChatInputBoxProps) => {
  const { t } = useTranslation();
  // 입력 텍스트는 이 컴포넌트에서만 관리한다 — 타이핑이 페이지(메시지 리스트 등)를
  // 재렌더하지 않도록 국소화. 제출은 onSubmitMessage로 값을 올리고 스스로 비운다.
  const [messageInput, setMessageInput] = useState("");

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmitMessage(messageInput);
    setMessageInput("");
  };

  return (
    <div className="border-t border-slate-100 px-4 py-3 sm:px-5">
      {pendingAttachment ? (
        <div className="mb-3 flex items-center justify-between gap-3 rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <div className="h-14 w-14 shrink-0 overflow-hidden rounded-xl bg-white ring-1 ring-blue-100">
              {pendingAttachment.contentType.startsWith("video/") ? (
                <video
                  src={pendingAttachment.previewUrl}
                  className="h-full w-full object-cover"
                  muted
                  playsInline
                />
              ) : (
                <img
                  src={pendingAttachment.previewUrl}
                  alt={t("chatbot.attachPreview")}
                  className="h-full w-full object-cover"
                />
              )}
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-extrabold text-slate-800">
                {pendingAttachment.fileName}
              </p>
              <p className="mt-1 text-xs font-bold text-blue-600">
                {t("chatbot.attachDone")}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClearPendingAttachment}
            className="h-9 rounded-xl bg-white px-3 text-xs font-extrabold text-slate-500 transition hover:text-blue-600"
          >
            {t("chatbot.attachDelete")}
          </button>
        </div>
      ) : null}
      <form
        onSubmit={handleSubmit}
        className="flex h-14 items-center gap-2 rounded-2xl bg-slate-50 p-1.5 ring-1 ring-slate-100"
      >
        <input
          ref={fileInputRef}
          type="file"
          accept="image/jpeg,image/png,video/mp4"
          onChange={onSelectAttachment}
          className="hidden"
        />
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploadingAttachment || isStreaming}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-blue-100 bg-white text-lg font-extrabold text-blue-600 shadow-sm transition hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700 disabled:opacity-60"
          aria-label={t("chatbot.attachAdd")}
        >
          {isUploadingAttachment ? "..." : "+"}
        </button>
        <input
          type="text"
          value={messageInput}
          onChange={(event) => setMessageInput(event.target.value)}
          disabled={isStreaming || isUploadingAttachment}
          placeholder={t("chatbot.inputPlaceholder")}
          className="h-11 min-w-0 flex-1 bg-transparent px-2 text-sm font-semibold text-slate-700 outline-none placeholder:text-slate-400 disabled:text-slate-400"
        />
        <button
          type="button"
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-blue-100 bg-white text-blue-600 shadow-sm transition hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"
          aria-label={t("chatbot.voiceInput")}
        >
          <MicrophoneIcon />
        </button>
        <button
          type="submit"
          disabled={
            (!messageInput.trim() && !pendingAttachment) ||
            isStreaming ||
            isUploadingAttachment
          }
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white transition hover:bg-blue-700 disabled:bg-slate-300"
          aria-label={t("chatbot.sendMessage")}
        >
          <SendIcon />
        </button>
      </form>
    </div>
  );
};

export default memo(ChatInputBox);
