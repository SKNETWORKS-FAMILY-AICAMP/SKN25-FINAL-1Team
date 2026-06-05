import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Plus,
  RefreshCcw,
} from "lucide-react";
import type { ReservationViewMode } from "../../types/reservation";

interface TopControlsProps {
  controlLabel: string;
  compactControlLabel: string;
  viewMode: ReservationViewMode;
  isLoading: boolean;
  onChangeViewMode: (mode: ReservationViewMode) => void;
  onAdd: () => void;
  onPrev: () => void;
  onNext: () => void;
  onToday: () => void;
  onRefresh: () => void;
}

export function TopControls({
  controlLabel,
  compactControlLabel,
  viewMode,
  isLoading,
  onChangeViewMode,
  onAdd,
  onPrev,
  onNext,
  onToday,
  onRefresh,
}: TopControlsProps) {
  return (
    <div className="mb-2 grid h-[68px] grid-cols-[1fr_auto_1fr] items-center rounded-lg border border-[#e5eaf2] bg-white px-4 shadow-sm">
      <div className="flex min-w-0 items-center gap-3">
        <div className="grid h-10 w-[224px] shrink-0 grid-cols-[40px_1fr_40px] overflow-hidden rounded-lg border border-[#dfe6f1] bg-white">
          <button
            type="button"
            onClick={onPrev}
            className="flex h-10 w-10 items-center justify-center border-r border-[#edf1f6] text-[#53617c] transition hover:bg-[#f3f6fb] hover:text-[#2563eb]"
            aria-label="이전 날짜"
          >
            <ChevronLeft className="h-5 w-5" />
          </button>
          <div
            className="flex min-w-0 items-center justify-center gap-1.5 px-2 text-sm font-extrabold tabular-nums text-[#20283a]"
            title={controlLabel}
          >
            <CalendarDays className="h-4 w-4 shrink-0 text-[#53617c]" />
            <span className="truncate">{compactControlLabel}</span>
          </div>
          <button
            type="button"
            onClick={onNext}
            className="flex h-10 w-10 items-center justify-center border-l border-[#edf1f6] text-[#53617c] transition hover:bg-[#f3f6fb] hover:text-[#2563eb]"
            aria-label="다음 날짜"
          >
            <ChevronRight className="h-5 w-5" />
          </button>
        </div>
        <button
          type="button"
          onClick={onToday}
          className="h-10 w-[72px] rounded-lg border border-[#dfe6f1] bg-white text-sm font-extrabold text-[#4d5874]"
        >
          오늘
        </button>
      </div>

      <div className="flex items-center justify-center gap-3">
        {[
          ["day", "일간"],
          ["week", "주간"],
          ["month", "월간"],
        ].map(([mode, label]) => (
          <button
            key={label}
            type="button"
            onClick={() => onChangeViewMode(mode as ReservationViewMode)}
            className={[
              "h-10 rounded-lg px-5 text-sm font-extrabold transition",
              viewMode === mode
                ? "bg-[#2563eb] text-white shadow-sm"
                : "border border-[#dfe6f1] bg-white text-[#4d5874]",
            ].join(" ")}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="flex items-center justify-end gap-3">
        <button
          type="button"
          onClick={onRefresh}
          disabled={isLoading}
          className="flex h-10 items-center gap-2 rounded-lg border border-[#dfe6f1] bg-white px-4 text-sm font-extrabold text-[#4d5874] disabled:cursor-wait disabled:opacity-60"
        >
          <RefreshCcw className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
          새로고침
        </button>
        <button
          type="button"
          onClick={onAdd}
          className="flex h-10 items-center gap-2 rounded-lg bg-[#2563eb] px-5 text-sm font-extrabold text-white shadow-sm"
        >
          <Plus className="h-4 w-4" />
          예약 추가
        </button>
      </div>
    </div>
  );
}
