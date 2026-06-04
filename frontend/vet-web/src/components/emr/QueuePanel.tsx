import { ChevronLeft, ChevronRight, RefreshCcw } from "lucide-react";
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
}) {
  return (
    <Panel className="flex h-full min-h-0 flex-col overflow-hidden">
      {/* 헤더 - 고정 */}
      <div className="shrink-0 px-4 py-2.5">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-extrabold text-[#151b28]">{title}</h2>
            <p className="mt-0.5 text-xs font-bold text-[#8a94a6]">
              갱신 {lastRefreshText}
            </p>
          </div>
          <button
            type="button"
            onClick={onRefresh}
            className="flex h-8 items-center gap-1.5 rounded-lg bg-[#edf5ff] px-2.5 text-[11px] font-extrabold text-[#2563eb] transition hover:bg-[#dcecff]"
          >
            <RefreshCcw className="h-4 w-4" />
            대기열 새로고침
          </button>
        </div>

        <div className="mt-2 grid grid-cols-[32px_minmax(0,1fr)_32px_48px] gap-1.5">
          <button
            type="button"
            onClick={() => onMoveDate(-1)}
            aria-label="이전 날짜"
            className="flex h-8 items-center justify-center rounded-lg border border-[#dfe6f1] text-[#59657a] transition hover:border-[#4a89ff] hover:text-[#2563eb]"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <input
            type="date"
            value={selectedDate}
            onChange={(event) => onChangeDate(event.target.value)}
            className="h-8 min-w-0 rounded-lg border border-[#dfe6f1] px-2 text-xs font-extrabold text-[#4d5874] outline-none focus:border-[#4a89ff] focus:ring-2 focus:ring-[#edf5ff]"
          />
          <button
            type="button"
            onClick={() => onMoveDate(1)}
            aria-label="다음 날짜"
            className="flex h-8 items-center justify-center rounded-lg border border-[#dfe6f1] text-[#59657a] transition hover:border-[#4a89ff] hover:text-[#2563eb]"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={onGoToday}
            disabled={isTodayView}
            className="h-8 rounded-lg border border-[#dfe6f1] text-xs font-extrabold text-[#59657a] transition hover:border-[#4a89ff] hover:text-[#2563eb] disabled:cursor-not-allowed disabled:bg-[#f8fafc] disabled:text-[#a8b0bf]"
          >
            오늘
          </button>
        </div>
      </div>

      {/* 탭 - 고정 */}
      <div className="grid shrink-0 grid-cols-2 border-y border-[#edf1f6] bg-[#f9fbfe] p-1">
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
          <tbody className="divide-y divide-[#edf1f6]">
            {queue.map((patient) => (
              <tr
                key={patient.schedule_id}
                onClick={() => onSelectPatient(patient.schedule_id)}
                className={`cursor-pointer text-xs text-[#5e6879] ${
                  patient.schedule_id === selectedScheduleId
                    ? "bg-[#f3f8ff]"
                    : "hover:bg-[#fafcff]"
                }`}
              >
                <td className="w-[86px] px-6 py-2 font-extrabold tabular-nums">
                  {patient.time}
                </td>
                <td className="px-4 py-2">
                  <p className="font-extrabold text-[#20283a]">
                    {patient.pet_name}
                  </p>
                  <p className="mt-0.5 truncate font-bold text-[#8a94a6]">
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
        active ? "bg-white text-[#2563eb] shadow-sm" : "text-[#697386]"
      }`}
    >
      {label}
    </button>
  );
}
