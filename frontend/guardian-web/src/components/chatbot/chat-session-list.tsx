import type { ChatSessionHistory } from "../../api/chat-api";
import type { Pet } from "../../api/pets-api";
import { useTranslation } from "../../i18n/language-context";

const HistoryIcon = () => (
  <svg viewBox="0 0 24 24" className="h-7 w-7" fill="none" aria-hidden="true">
    <path
      d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2m-6 7h6m-6 4h4"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

interface ChatSessionListProps {
  selectedPet?: Pet;
  chatHistories: ChatSessionHistory[];
  selectedHistoryId: number | null;
  isLoadingHistories: boolean;
  creatingPetId: number | null;
  onCreateSession: () => void;
  onSelectHistory: (historyId: number) => void;
  onDeleteHistory: (history: ChatSessionHistory) => void;
  getHistoryTitle: (history: ChatSessionHistory) => string;
}

const ChatSessionList = ({
  selectedPet,
  chatHistories,
  selectedHistoryId,
  isLoadingHistories,
  creatingPetId,
  onCreateSession,
  onSelectHistory,
  onDeleteHistory,
  getHistoryTitle,
}: ChatSessionListProps) => {
  const { t } = useTranslation();

  return (
    <aside className="flex h-[220px] flex-col border-b border-slate-100 bg-white lg:h-auto lg:min-h-0 lg:border-b-0 lg:border-r">
      <div className="flex h-14 shrink-0 items-center justify-center border-b border-slate-100 px-4">
        <h2 className="text-center text-[15px] font-bold text-slate-900">
          {t("chatbot.history")}
        </h2>
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        {!selectedPet ? (
          <div className="flex flex-1 flex-col items-center px-4 pt-[150px] text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-slate-100 text-slate-400">
              <HistoryIcon />
            </div>
            <p className="mt-4 text-[13px] font-bold text-slate-800 [text-wrap:balance]">
              {t("chatbot.historyEmptyTitle")}
            </p>
            <p className="mt-2 text-xs font-semibold leading-5 text-slate-500">
              {t("chatbot.historyEmptyDescription")}
            </p>
          </div>
        ) : (
          <>
            <div className="shrink-0 px-4 pt-6">
              <button
                type="button"
                onClick={onCreateSession}
                disabled={creatingPetId !== null}
                className="flex h-10 w-full items-center justify-center rounded-xl bg-blue-600 px-4 text-sm font-bold text-white transition hover:bg-blue-700 disabled:bg-blue-300"
              >
                {creatingPetId ? t("chatbot.creating") : t("chatbot.newChat")}
              </button>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
              {isLoadingHistories ? (
                <div className="mt-8 flex justify-center">
                  <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-100 border-t-blue-600" />
                </div>
              ) : chatHistories.length === 0 ? (
                <p className="mt-6 text-center text-xs font-semibold leading-5 text-slate-500">
                  {t("chatbot.noHistory")}
                </p>
              ) : (
                <div className="mt-4 divide-y divide-slate-100 border-y border-slate-100">
                  {chatHistories.map((history) => {
                    const isSelected = history.session_id === selectedHistoryId;

                    return (
                      <div
                        key={history.session_id}
                        className={[
                          "relative border-l-2 transition",
                          isSelected
                            ? "border-blue-300 bg-blue-50"
                            : "border-transparent bg-white hover:bg-blue-50/60",
                        ].join(" ")}
                      >
                        <button
                          type="button"
                          onClick={() => onSelectHistory(history.session_id)}
                          className="block w-full px-1 py-3 pr-9 text-left"
                        >
                          <span className="block truncate text-sm font-extrabold text-slate-900">
                            {getHistoryTitle(history)}
                          </span>
                          <span className="mt-2 block text-[10px] font-bold text-slate-400">
                            {history.created_at}
                          </span>
                        </button>
                        <button
                          type="button"
                          onClick={() => onDeleteHistory(history)}
                          className="absolute right-1 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full text-sm font-extrabold text-slate-400 transition hover:bg-white hover:text-rose-500"
                          aria-label={t("chatbot.deleteHistory")}
                        >
                          x
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </aside>
  );
};

export default ChatSessionList;
