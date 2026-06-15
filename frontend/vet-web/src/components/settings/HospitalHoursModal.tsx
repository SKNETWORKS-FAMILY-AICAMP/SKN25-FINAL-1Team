import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { type DaySchedule, fetchWeeklySchedule, updateWeeklySchedule } from "../../api/settingsApi";
import type { AuthSession } from "../../api/authApi";
import { useEscapeToClose } from "../../hooks/useEscapeToClose";
import { DAY_LABELS, defaultWeek, Toggle, InlineTimeSelect } from "./settingsShared";

interface Props {
  session: AuthSession;
  onClose: () => void;
}

export function HospitalHoursModal({ session, onClose }: Props) {
  const [schedule, setSchedule] = useState<DaySchedule[]>(defaultWeek);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEscapeToClose(onClose, !saving);

  useEffect(() => {
    fetchWeeklySchedule(session.accessToken)
      .then(setSchedule)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [session.accessToken]);

  const updateDay = (dow: number, patch: Partial<DaySchedule>) => {
    setSchedule((prev) => prev.map((d) => (d.day_of_week === dow ? { ...d, ...patch } : d)));
  };

  const toggleOpen = (dow: number) => {
    const day = schedule.find((d) => d.day_of_week === dow)!;
    if (!day.is_open) {
      updateDay(dow, { is_open: true, start_time: "09:00", end_time: "18:00", lunch_start: "12:00", lunch_end: "13:00" });
    } else {
      updateDay(dow, { is_open: false, start_time: null, end_time: null, lunch_start: null, lunch_end: null });
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError("");
    try {
      const saved = await updateWeeklySchedule(session.accessToken, schedule);
      setSchedule(saved);
      onClose();
    } catch {
      setError("저장에 실패했습니다.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl rounded-xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 헤더 */}
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <div>
            <h2 className="text-lg font-extrabold text-slate-900">병원 운영 시간 설정</h2>
            <p className="mt-0.5 text-xs font-semibold text-slate-400">
              요일별 기본 운영 시간과 점심 시간을 설정합니다.
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

        {/* 테이블 */}
        <div className="px-6 py-4">
          {loading ? (
            <p className="py-8 text-center text-sm text-slate-400">불러오는 중...</p>
          ) : (
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-100">
                  <th className="pb-2 w-12 text-left text-xs font-extrabold text-slate-500">요일</th>
                  <th className="pb-2 text-left text-xs font-extrabold text-slate-500">운영 시간</th>
                  <th className="pb-2 text-left text-xs font-extrabold text-slate-500">점심 시간</th>
                  <th className="pb-2 w-20 text-center text-xs font-extrabold text-slate-500">운영 여부</th>
                </tr>
              </thead>
              <tbody>
                {schedule.map((day) => (
                  <tr key={day.day_of_week} className="border-b border-slate-50 last:border-0">
                    <td className="py-3 text-sm font-extrabold text-slate-700">
                      {DAY_LABELS[day.day_of_week]}
                    </td>
                    <td className="py-3">
                      {day.is_open ? (
                        <div className="flex items-center gap-1.5">
                          <InlineTimeSelect
                            value={day.start_time ?? "09:00"}
                            onChange={(v) => updateDay(day.day_of_week, { start_time: v })}
                          />
                          <span className="text-xs text-slate-400">~</span>
                          <InlineTimeSelect
                            value={day.end_time ?? "18:00"}
                            onChange={(v) => updateDay(day.day_of_week, { end_time: v })}
                          />
                        </div>
                      ) : (
                        <span className="text-xs font-semibold text-slate-300">휴진</span>
                      )}
                    </td>
                    <td className="py-3">
                      {day.is_open ? (
                        <div className="flex items-center gap-1.5">
                          <InlineTimeSelect
                            value={day.lunch_start ?? "12:00"}
                            onChange={(v) => updateDay(day.day_of_week, { lunch_start: v })}
                          />
                          <span className="text-xs text-slate-400">~</span>
                          <InlineTimeSelect
                            value={day.lunch_end ?? "13:00"}
                            onChange={(v) => updateDay(day.day_of_week, { lunch_end: v })}
                          />
                        </div>
                      ) : (
                        <span className="text-xs text-slate-300">-</span>
                      )}
                    </td>
                    <td className="py-3 text-center">
                      <Toggle checked={day.is_open} onChange={() => toggleOpen(day.day_of_week)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {error && <p className="mt-3 text-xs font-bold text-red-600">{error}</p>}
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
            onClick={handleSave}
            disabled={saving || loading}
            className="h-10 rounded-lg bg-blue-600 px-5 text-sm font-extrabold text-white hover:bg-blue-700 disabled:bg-blue-200"
          >
            {saving ? "저장 중..." : "저장"}
          </button>
        </div>
      </div>
    </div>
  );
}
