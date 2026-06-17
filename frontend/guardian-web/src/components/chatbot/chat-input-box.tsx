import {
  memo,
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type RefObject,
} from "react";

import { transcribeAudio } from "../../api/chat-api";
import type { PendingAttachment } from "../../hooks/use-chat-upload";
import { useVoiceRecording } from "../../hooks/use-voice-recording";
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

  // STT — 마이크 녹음 + 실시간 미리보기 + 전사 상태
  const { isRecording, liveText, start, stop } = useVoiceRecording();
  const [isTranscribing, setIsTranscribing] = useState(false);
  const baseTextRef = useRef(""); // 녹음 시작 시점의 기존 입력(미리보기는 이 뒤에 덧붙임)
  const messageInputRef = useRef(messageInput); // 최신 입력값 참조(콜백 안정화용)
  const finishingRef = useRef(false); // 정지 처리 중복 방지(무음 타이머 vs 수동 클릭)

  const SILENCE_MS = 2000; // 이만큼 무음이면 자동 정지+전송

  useEffect(() => {
    messageInputRef.current = messageInput;
  }, [messageInput]);

  // STT — 녹음 정지 → Groq 최종 교정 → (autoSend면) 자동 전송
  const finishVoice = useCallback(
    async (autoSend: boolean) => {
      if (finishingRef.current) {
        return;
      }
      finishingRef.current = true;

      const audio = await stop();
      if (!audio) {
        finishingRef.current = false;
        return;
      }

      // 정지 시점: 입력창엔 이미 실시간 미리보기가 있음 → Groq 정확 전사로 교체
      setIsTranscribing(true);
      let finalText = messageInputRef.current; // 전사 실패 시 미리보기를 그대로 사용
      try {
        const { result } = await transcribeAudio(audio);
        const text = (result?.text || "").trim();
        if (text) {
          const base = baseTextRef.current;
          finalText = base && text ? `${base} ${text}` : base + text;
          setMessageInput(finalText);
        }
      } catch {
        // 전사 실패 — 미리보기 텍스트 유지
      } finally {
        setIsTranscribing(false);
        finishingRef.current = false;
      }

      // 무음 자동 정지 → 엔터처럼 바로 전송
      if (autoSend && finalText.trim()) {
        onSubmitMessage(finalText);
        setMessageInput("");
      }
    },
    [stop, onSubmitMessage],
  );

  // STT — 실시간 미리보기 반영 + 3초 무음이면 자동 정지(타이머는 말할 때마다 리셋)
  useEffect(() => {
    if (!isRecording) {
      return;
    }
    const base = baseTextRef.current;
    setMessageInput(base && liveText ? `${base} ${liveText}` : base + liveText);

    if (!liveText.trim()) {
      return; // 아직 한마디도 안 함 → 무음 타이머 안 켬
    }
    const timer = window.setTimeout(() => {
      void finishVoice(true);
    }, SILENCE_MS);
    return () => window.clearTimeout(timer); // 다음 말이 들어오면 타이머 리셋
  }, [liveText, isRecording, finishVoice]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmitMessage(messageInput);
    setMessageInput("");
  };

  // STT — 마이크 토글: 녹음 시작 / 수동 정지(전송 안 하고 입력창에만 채움)
  const handleVoiceClick = async () => {
    if (!isRecording) {
      baseTextRef.current = messageInput; // 기존 입력 보존
      finishingRef.current = false;
      try {
        await start();
      } catch {
        // 마이크 권한 거부 등 — 조용히 무시
      }
      return;
    }
    await finishVoice(false); // true면 자동 전송, false면 입력창에만 채움
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
          disabled={isStreaming || isUploadingAttachment || isRecording || isTranscribing}
          placeholder={isRecording ? t("chatbot.voiceListening") : t("chatbot.inputPlaceholder")}
          className="h-11 min-w-0 flex-1 bg-transparent px-2 text-sm font-semibold text-slate-700 outline-none placeholder:text-slate-400 disabled:text-slate-400"
        />
        <button
          type="button"
          onClick={handleVoiceClick}
          disabled={isStreaming || isUploadingAttachment || isTranscribing}
          className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border shadow-sm transition disabled:opacity-60 ${
            isRecording
              ? "border-red-200 bg-red-50 text-red-600 hover:bg-red-100"
              : "border-blue-100 bg-white text-blue-600 hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"
          }`}
          aria-label={t("chatbot.voiceInput")}
        >
          {isTranscribing ? "..." : <MicrophoneIcon />}
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
