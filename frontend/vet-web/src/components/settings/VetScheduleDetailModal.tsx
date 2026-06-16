import { useEffect, useState } from "react";
import { X } from "lucide-react";
import {
  type DaySchedule,
  fetchVetWeeklySchedule,
  fetchWeeklySchedule,
  updateVetWeeklySchedule,
} from "../../api/settingsApi";
import { fetchHospitalDoctors, type DoctorInfo } from "../../api/emrApi";
import type { AuthSession } from "../../api/authApi";
import { useEscapeToClose } from "../../hooks/useEscapeToClose";
import { DAY_LABELS, defaultWeek, InlineTimeSelect } from "./settingsShared";

interface Props {
  session: AuthSession;
  initialVetId?: number;
  onClose: () => void;
}

export function VetScheduleDetailModal({ session, initialVetId, onClose }: Props) {
  const [doctors, setDoctors] = useState<DoctorInfo[]>([]);
  const [selectedVetId, setSelectedVetId] = useState<number | undefined>(initialVetId);
  const [schedule, setSchedule] = useState<DaySchedule[]>(defaultWeek);
  const [hospSchedule, setHospSchedule] = useState<DaySchedule[]>([]);
  const [selectedDow, setSelectedDow] = useState(0);
  const [loadingDoctors, setLoadingDoctors] = useState(true);
  const [loadingSchedule, setLoadingSchedule] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEscapeToClose(onClose, !saving);

  useEffect(() => {
    fetchWeeklySchedule(session.accessToken).then(setHospSchedule).catch(() => {});
    fetchHospitalDoctors(session.accessToken)
      .then((docs) => {
        setDoctors(docs);
        if (!selectedVetId && docs.length > 0) {
          setSelectedVetId(docs[0].doctorid);
        }
      })
      .catch(() => {})
      .finally(() => setLoadingDoctors(false));
  }, [session.accessToken]);

  useEffect(() => {
    if (!selectedVetId) return;
    setLoadingSchedule(true);
    fetchVetWeeklySchedule(session.accessToken, selectedVetId)
      .then((doctorSchedule) => {
        // 의사가 설정하지 않은 요일(is_open=false)은 병원 운영시간을 기본값으로 채움
        const merged = doctorSchedule.map((day) => {
          if (day.is_open) return day;
          const hosp = hospSchedule.find((h) => h.day_of_week === day.day_of_week);
          return hosp?.is_open ? { ...hosp, day_of_week: day.day_of_week } : day;
        });
        setSchedule(merged);
      })
      .catch(() => {})
      .finally(() => setLoadingSchedule(false));
  }, [session.accessToken, selectedVetId, hospSchedule]);

  const currentDay = schedule.find((d) => d.day_of_week === selectedDow) ?? schedule[0];

  const updateCurrentDay = (patch: Partial<DaySchedule>) => {
    setSchedule((prev) =>
      prev.map((d) => (d.day_of_week === selectedDow ? { ...d, ...patch } : d))
    );
  };

  const handleSave = async () => {
    if (!selectedVetId) return;
    setSaving(true);
    setError("");
    try {
      await updateVetWeeklySchedule(session.accessToken, selectedVetId, schedule);
      onClose();
    } catch (err: unknown) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const detail = (err as any)?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "저장에 실패했습니다.");
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
        className="w-full max-w-md rounded-xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 헤더 */}
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <div>
            <h2 className="text-lg font-extrabold text-slate-900">의사별 근무 시간 상세 설정</h2>
            <p className="mt-0.5 text-xs font-semibold text-slate-400">
              요일별로 다른 근무 시간을 설정할 수 있습니다.
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

        <div className="px-6 py-4 space-y-5">
          {/* 수의사 선택 */}
          <div>
            <label className="mb-1.5 block text-xs font-extrabold text-slate-600">수의사 선택</label>
            {loadingDoctors ? (
              <p className="text-xs text-slate-400">불러오는 중...</p>
            ) : (
              <select
                value={selectedVetId ?? ""}
                onChange={(e) => setSelectedVetId(Number(e.target.value))}
                className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm font-bold text-slate-800 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-50"
              >
                {doctors.map((d) => (
                  <option key={d.doctorid} value={d.doctorid}>
                    {d.doctor_name}
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* 요일 탭 */}
          <div className="flex gap-1">
            {DAY_LABELS.map((label, i) => (
              <button
                key={i}
                type="button"
                onClick={() => setSelectedDow(i)}
                className={`flex-1 h-9 rounded-lg text-sm font-extrabold transition ${
                  selectedDow === i
                    ? "bg-blue-600 text-white"
                    : "bg-slate-100 text-slate-500 hover:bg-slate-200"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {loadingSchedule ? (
            <p className="py-4 text-center text-sm text-slate-400">불러오는 중...</p>
          ) : (
            <>
              {/* 근무 시간 */}
              <div>
                <p className="mb-3 text-xs font-extrabold text-slate-600">근무 시간</p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="mb-1 block text-xs font-semibold text-slate-400">출근 시간</label>
                    <InlineTimeSelect
                      value={currentDay?.start_time ?? "09:00"}
                      onChange={(v) => updateCurrentDay({ start_time: v, is_open: true })}
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-semibold text-slate-400">퇴근 시간</label>
                    <InlineTimeSelect
                      value={currentDay?.end_time ?? "18:00"}
                      onChange={(v) => updateCurrentDay({ end_time: v })}
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-semibold text-slate-400">점심 시작</label>
                    <InlineTimeSelect
                      value={currentDay?.lunch_start ?? "12:00"}
                      onChange={(v) => updateCurrentDay({ lunch_start: v })}
                      disabled={!currentDay?.lunch_start}
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-semibold text-slate-400">점심 종료</label>
                    <InlineTimeSelect
                      value={currentDay?.lunch_end ?? "13:00"}
                      onChange={(v) => updateCurrentDay({ lunch_end: v })}
                      disabled={!currentDay?.lunch_start}
                    />
                  </div>
                </div>
              </div>

              {/* 옵션 */}
              <div>
                <p className="mb-2 text-xs font-extrabold text-slate-600">옵션</p>
                <div className="space-y-2">
                  <label className="flex cursor-pointer items-center gap-2">
                    <input
                      type="checkbox"
                      checked={!currentDay?.is_open}
                      onChange={(e) => {
                        if (e.target.checked) {
                          updateCurrentDay({
                            is_open: false,
                            start_time: null,
                            end_time: null,
                            lunch_start: null,
                            lunch_end: null,
                          });
                        } else {
                          updateCurrentDay({
                            is_open: true,
                            start_time: "09:00",
                            end_time: "18:00",
                            lunch_start: "12:00",
                            lunch_end: "13:00",
                          });
                        }
                      }}
                      className="h-4 w-4 rounded border-slate-300 accent-blue-600"
                    />
                    <span className="text-sm font-semibold text-slate-700">이 요일은 휴무입니다.</span>
                  </label>
                  <label className="flex cursor-pointer items-center gap-2">
                    <input
                      type="checkbox"
                      checked={!currentDay?.lunch_start}
                      onChange={(e) => {
                        if (e.target.checked) {
                          updateCurrentDay({ lunch_start: null, lunch_end: null });
                        } else {
                          updateCurrentDay({ lunch_start: "12:00", lunch_end: "13:00" });
                        }
                      }}
                      className="h-4 w-4 rounded border-slate-300 accent-blue-600"
                    />
                    <span className="text-sm font-semibold text-slate-700">점심 시간이 없습니다.</span>
                  </label>
                </div>
              </div>

              <p className="text-xs font-semibold text-slate-400">
                적용 요일:{" "}
                <span className="font-extrabold text-slate-700">{DAY_LABELS[selectedDow]}</span>
              </p>
            </>
          )}

          {error && <p className="text-xs font-bold text-red-600">{error}</p>}
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
            disabled={saving || !selectedVetId}
            className="h-10 rounded-lg bg-blue-600 px-5 text-sm font-extrabold text-white hover:bg-blue-700 disabled:bg-blue-200"
          >
            {saving ? "저장 중..." : "저장"}
          </button>
        </div>
      </div>
    </div>
  );
}
