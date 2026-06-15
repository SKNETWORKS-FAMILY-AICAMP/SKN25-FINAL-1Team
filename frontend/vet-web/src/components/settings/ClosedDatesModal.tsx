import { useEffect, useState } from "react";
import { AlertTriangle, Plus, Trash2, X } from "lucide-react";
import { fetchClosedDates, addClosedDate, removeClosedDate } from "../../api/settingsApi";
import type { AuthSession } from "../../api/authApi";
import { useEscapeToClose } from "../../hooks/useEscapeToClose";

interface Props {
  session: AuthSession;
  onClose: () => void;
}

export function ClosedDatesModal({ session, onClose }: Props) {
  const [closedDates, setClosedDates] = useState<string[]>([]);
  const [newDate, setNewDate] = useState("");
  const [loading, setLoading] = useState(true);
  const [warning, setWarning] = useState("");
  const [error, setError] = useState("");

  useEscapeToClose(onClose);

  useEffect(() => {
    fetchClosedDates(session.accessToken)
      .then(setClosedDates)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [session.accessToken]);

  const handleAdd = async () => {
    if (!newDate) return;
    setWarning("");
    setError("");
    try {
      const result = await addClosedDate(session.accessToken, newDate);
      setClosedDates((prev) => [...prev, newDate].sort());
      setNewDate("");
      if (result.has_existing_reservations) {
        setWarning(
          `해당 날짜에 예약이 ${result.reservation_count}건 있습니다. 기존 예약은 직접 처리해주세요.`
        );
      }
    } catch {
      setError("휴진일 등록에 실패했습니다.");
    }
  };

  const handleRemove = async (d: string) => {
    setWarning("");
    setError("");
    try {
      await removeClosedDate(session.accessToken, d);
      setClosedDates((prev) => prev.filter((x) => x !== d));
    } catch {
      setError("휴진일 해제에 실패했습니다.");
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 헤더 */}
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <div>
            <h2 className="text-lg font-extrabold text-slate-900">특정일 휴진 설정</h2>
            <p className="mt-0.5 text-xs font-semibold text-slate-400">
              특정 날짜를 지정하여 휴진일을 관리할 수 있습니다.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="px-6 py-4 space-y-4">
          {/* 날짜 추가 */}
          <div>
            <p className="mb-2 text-xs font-extrabold text-slate-600">날짜 추가</p>
            <div className="flex items-center gap-2">
              <input
                type="date"
                value={newDate}
                onChange={(e) => {
                  setNewDate(e.target.value);
                  setError("");
                  setWarning("");
                }}
                className="h-9 flex-1 rounded-lg border border-slate-200 bg-white px-3 text-sm font-bold text-slate-800 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-50"
              />
              <button
                type="button"
                onClick={handleAdd}
                disabled={!newDate}
                className="flex h-9 items-center gap-1.5 rounded-lg bg-blue-600 px-3 text-xs font-extrabold text-white hover:bg-blue-700 disabled:bg-blue-200 disabled:cursor-not-allowed"
              >
                <Plus className="h-3.5 w-3.5" />
                추가
              </button>
            </div>
          </div>

          {warning && (
            <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
              <p className="text-xs font-bold text-amber-700">{warning}</p>
            </div>
          )}
          {error && <p className="text-xs font-bold text-red-600">{error}</p>}

          {/* 등록된 휴진일 */}
          <div>
            <p className="mb-2 text-xs font-extrabold text-slate-600">
              등록된 휴진일 ({closedDates.length})
            </p>
            {loading ? (
              <p className="text-xs text-slate-400">불러오는 중...</p>
            ) : closedDates.length > 0 ? (
              <ul className="max-h-60 overflow-y-auto space-y-1.5">
                {closedDates.map((d) => (
                  <li
                    key={d}
                    className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2.5"
                  >
                    <span className="text-sm font-bold text-slate-800">{d}</span>
                    <button
                      type="button"
                      onClick={() => handleRemove(d)}
                      className="flex h-7 w-7 items-center justify-center rounded-lg text-slate-400 hover:bg-red-50 hover:text-red-500"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs font-semibold text-slate-300">등록된 휴진일이 없습니다.</p>
            )}
          </div>
        </div>

        {/* 푸터 */}
        <div className="flex justify-end gap-3 border-t border-slate-200 px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="h-10 rounded-lg border border-slate-200 px-5 text-sm font-extrabold text-slate-600 hover:bg-slate-50"
          >
            취소
          </button>
          <button
            type="button"
            onClick={onClose}
            className="h-10 rounded-lg bg-blue-600 px-5 text-sm font-extrabold text-white hover:bg-blue-700"
          >
            저장
          </button>
        </div>
      </div>
    </div>
  );
}
