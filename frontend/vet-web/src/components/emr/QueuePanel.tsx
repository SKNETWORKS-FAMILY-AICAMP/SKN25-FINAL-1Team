import { ChevronLeft, ChevronRight, RefreshCcw } from "lucide-react";
import type { DoctorInfo } from "../../api/emrApi";
import type { QueuePatient, QueueTab } from "../../types/emr";
import { Panel, StatusBadge } from "./EmrShared";

export function QueuePanel({
  title,
  activeTab,
  queue,
  selectedScheduleId,
  lastRefreshText,
  waitingCount,
  completedCount,
  selectedDate,
  isTodayView,
  onChangeTab,
  onSelectPatient,
  onRefresh,
  onChangeDate,
  onMoveDate,
  onGoToday,
  doctors,
  selectedDoctorId,
  onSelectDoctor,
}: {
  title: string;
  activeTab: QueueTab;
  queue: QueuePatient[];
  selectedScheduleId?: number;
  lastRefreshText: string;
  waitingCount: number;
  completedCount: number;
  selectedDate: string;
  isTodayView: boolean;
  onChangeTab: (tab: QueueTab) => void;
  onSelectPatient: (scheduleId: number) => void;
  onRefresh: () => void;
  onChangeDate: (dateValue: string) => void;
  onMoveDate: (days: number) => void;
  onGoToday: () => void;
  doctors: DoctorInfo[];
  selectedDoctorId: number | undefined;
  onSelectDoctor: (id: number | undefined) => void;
}) {
  return (
    <Panel className="flex h-full min-h-0 flex-col overflow-hidden">
      {/* 헤더 - 고정 */}
      <div className="shrink-0 px-4 py-2.5">
        {/* 제목 + 수의사 드롭다운 */}
        <div className="flex items-start justify-between gap-2">
          <div>
            <h2 className="text-sm font-extrabold text-slate-900">{title}</h2>
            <p className="mt-0.5 text-xs font-bold text-slate-400">
              갱신 {lastRefreshText}
            </p>
          </div>
          {doctors.length > 0 && (
            <div className="flex shrink-0 items-center gap-1.5">
              <span className="text-xs font-bold text-slate-400">수의사</span>
              <select
                value={selectedDoctorId ?? ""}
                onChange={(e) =>
                  onSelectDoctor(e.target.value ? Number(e.target.value) : undefined)
                }
                className="h-7 w-auto rounded-lg border border-slate-200 bg-white px-2 text-xs font-extrabold text-slate-700 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-50"
              >
                {doctors.map((d) => (
                  <option key={d.doctorid} value={d.doctorid}>
                    {d.doctor_name}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* 날짜 네비 + 새로고침 */}
        <div className="mt-2 grid grid-cols-[32px_minmax(0,1fr)_32px_48px_32px] gap-1.5">
          <button
            type="button"
            onClick={() => onMoveDate(-1)}
            aria-label="이전 날짜"
            className="flex h-8 items-center justify-center rounded-lg border border-slate-200 text-slate-600 transition hover:border-blue-500 hover:text-blue-600"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <div className="relative min-w-0">
            <input
              type="date"
              value={selectedDate}
              onChange={(event) => onChangeDate(event.target.value)}
              className="h-8 w-full min-w-0 rounded-lg border border-slate-200 px-2 text-xs font-extrabold text-transparent outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-50 [&::-webkit-calendar-picker-indicator]:hidden"
            />
            <span className="pointer-events-none absolute inset-y-0 left-0 right-0 flex items-center justify-center text-xs font-extrabold tabular-nums text-slate-600">
              {formatQueueDateLabel(selectedDate)}
            </span>
          </div>
          <button
            type="button"
            onClick={() => onMoveDate(1)}
            aria-label="다음 날짜"
            className="flex h-8 items-center justify-center rounded-lg border border-slate-200 text-slate-600 transition hover:border-blue-500 hover:text-blue-600"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={onGoToday}
            disabled={isTodayView}
            className="h-8 rounded-lg border border-slate-200 text-xs font-extrabold text-slate-600 transition hover:border-blue-500 hover:text-blue-600 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400"
          >
            오늘
          </button>
          <button
            type="button"
            onClick={onRefresh}
            aria-label="대기열 새로고침"
            className="flex h-8 items-center justify-center rounded-lg bg-blue-50 text-blue-600 transition hover:bg-blue-100"
          >
            <RefreshCcw className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* 탭 - 고정 */}
      <div className="grid shrink-0 grid-cols-2 border-y border-slate-100 bg-slate-50 p-1">
        <QueueTabButton
          active={activeTab === "waiting"}
          label={`진료 대기 ${waitingCount}`}
          onClick={() => onChangeTab("waiting")}
        />
        <QueueTabButton
          active={activeTab === "completed"}
          label={`진료 완료 ${completedCount}`}
          onClick={() => onChangeTab("completed")}
        />
      </div>

      {/* 환자 목록 - 패널 내부 스크롤 */}
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <table className="w-full table-fixed text-left">
          <tbody className="divide-y divide-slate-100">
            {queue.map((patient) => (
              <tr
                key={patient.schedule_id}
                onClick={() => onSelectPatient(patient.schedule_id)}
                className={`cursor-pointer text-xs text-slate-500 ${
                  patient.schedule_id === selectedScheduleId
                    ? "bg-slate-50"
                    : "hover:bg-slate-50"
                }`}
              >
                <td className="w-[86px] px-6 py-2 font-extrabold tabular-nums">
                  {patient.time}
                </td>
                <td className="px-4 py-2">
                  <p className="font-extrabold text-slate-800">
                    {patient.pet_name}
                  </p>
                  <p className="mt-0.5 truncate font-bold text-slate-400">
                    {patient.guardian_name} · {patient.species}
                  </p>
                </td>
                <td className="w-[88px] px-4 py-2">
                  <StatusBadge status={patient.triage_status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function formatQueueDateLabel(dateValue: string) {
  return dateValue.replace(/-/g, ".");
}

function QueueTabButton({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`h-8 rounded-md text-sm font-extrabold transition ${
        active ? "bg-white text-blue-600 shadow-sm" : "text-slate-500"
      }`}
    >
      {label}
    </button>
  );
}
