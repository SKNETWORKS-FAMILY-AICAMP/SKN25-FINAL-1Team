import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Plus,
  RefreshCcw,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { ReservationViewMode } from "../../types/reservation";
import { TODAY } from "../../utils/reservationUtils";
import { MiniCalendar } from "./MiniCalendar";

const monthLabels = [
  "1월",
  "2월",
  "3월",
  "4월",
  "5월",
  "6월",
  "7월",
  "8월",
  "9월",
  "10월",
  "11월",
  "12월",
];

interface TopControlsProps {
  controlLabel: string;
  compactControlLabel: string;
  selectedDate: Date;
  viewMode: ReservationViewMode;
  isLoading: boolean;
  onSelectDate: (date: Date) => void;
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
  selectedDate,
  viewMode,
  isLoading,
  onSelectDate,
  onChangeViewMode,
  onAdd,
  onPrev,
  onNext,
  onToday,
  onRefresh,
}: TopControlsProps) {
  const [isCalendarOpen, setIsCalendarOpen] = useState(false);
  const [monthPickerYear, setMonthPickerYear] = useState(selectedDate.getFullYear());
  const calendarRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMonthPickerYear(selectedDate.getFullYear());
  }, [selectedDate]);

  useEffect(() => {
    if (!isCalendarOpen) return;

    const handlePointerDown = (event: MouseEvent) => {
      if (
        calendarRef.current &&
        !calendarRef.current.contains(event.target as Node)
      ) {
        setIsCalendarOpen(false);
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [isCalendarOpen]);

  return (
    <div className="mb-2 grid h-[68px] grid-cols-[1fr_auto_1fr] items-center rounded-lg border border-slate-200 bg-white px-4 shadow-sm">
      <div className="flex min-w-0 items-center gap-3">
        <div
          ref={calendarRef}
          className="relative grid h-10 w-[224px] shrink-0 grid-cols-[40px_1fr_40px] rounded-lg border border-slate-200 bg-white"
        >
          <button
            type="button"
            onClick={onPrev}
            className="flex h-10 w-10 items-center justify-center border-r border-slate-100 text-slate-600 transition hover:bg-slate-50 hover:text-blue-600"
            aria-label="이전 날짜"
          >
            <ChevronLeft className="h-5 w-5" />
          </button>
          <button
            type="button"
            onClick={() => setIsCalendarOpen((open) => !open)}
            className="flex min-w-0 items-center justify-center gap-1.5 px-2 text-sm font-extrabold tabular-nums text-slate-800 transition hover:bg-slate-50"
            title={controlLabel}
            aria-expanded={isCalendarOpen}
            aria-label="날짜 선택 달력 열기"
          >
            <CalendarDays className="h-4 w-4 shrink-0 text-slate-600" />
            <span className="truncate">{compactControlLabel}</span>
          </button>
          <button
            type="button"
            onClick={onNext}
            className="flex h-10 w-10 items-center justify-center border-l border-slate-100 text-slate-600 transition hover:bg-slate-50 hover:text-blue-600"
            aria-label="다음 날짜"
          >
            <ChevronRight className="h-5 w-5" />
          </button>

          {isCalendarOpen && (
            <div className="absolute left-0 top-[calc(100%+8px)] z-30">
              {viewMode === "month" ? (
                <section className="w-[272px] rounded-lg border border-slate-200 bg-white p-4 shadow-xl">
                  <div className="mb-3 grid grid-cols-[32px_1fr_32px] items-center">
                    <button
                      type="button"
                      onClick={() => setMonthPickerYear((year) => year - 1)}
                      className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-600 transition hover:bg-slate-50 hover:text-blue-600"
                      aria-label="이전 연도"
                    >
                      <ChevronLeft className="h-5 w-5" />
                    </button>
                    <h2 className="text-center text-base font-extrabold text-slate-900">
                      {monthPickerYear}년
                    </h2>
                    <button
                      type="button"
                      onClick={() => setMonthPickerYear((year) => year + 1)}
                      className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-600 transition hover:bg-slate-50 hover:text-blue-600"
                      aria-label="다음 연도"
                    >
                      <ChevronRight className="h-5 w-5" />
                    </button>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    {monthLabels.map((label, monthIndex) => {
                      const isSelected =
                        selectedDate.getFullYear() === monthPickerYear &&
                        selectedDate.getMonth() === monthIndex;
                      const isCurrent =
                        TODAY.getFullYear() === monthPickerYear &&
                        TODAY.getMonth() === monthIndex;

                      return (
                        <button
                          key={label}
                          type="button"
                          onClick={() => {
                            onSelectDate(new Date(monthPickerYear, monthIndex, 1));
                            setIsCalendarOpen(false);
                          }}
                          className={[
                            "h-10 rounded-lg text-sm font-extrabold transition",
                            isSelected
                              ? "bg-blue-600 text-white"
                              : isCurrent
                                ? "border border-blue-600 bg-white text-blue-600"
                                : "border border-slate-100 bg-white text-slate-600 hover:bg-blue-50 hover:text-blue-600",
                          ].join(" ")}
                        >
                          {label}
                        </button>
                      );
                    })}
                  </div>
                </section>
              ) : (
                <div className="w-[272px]">
                  <MiniCalendar
                    selectedDate={selectedDate}
                    onSelectDate={(date) => {
                      onSelectDate(date);
                      setIsCalendarOpen(false);
                    }}
                  />
                </div>
              )}
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={() => {
            onToday();
            setIsCalendarOpen(false);
          }}
          className="h-10 w-[72px] rounded-lg border border-slate-200 bg-white text-sm font-extrabold text-slate-600"
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
                ? "bg-blue-600 text-white shadow-sm"
                : "border border-slate-200 bg-white text-slate-600",
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
          className="flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-extrabold text-slate-600 disabled:cursor-wait disabled:opacity-60"
        >
          <RefreshCcw className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
          새로고침
        </button>
        <button
          type="button"
          onClick={onAdd}
          className="flex h-10 items-center gap-2 rounded-lg bg-blue-600 px-5 text-sm font-extrabold text-white shadow-sm"
        >
          <Plus className="h-4 w-4" />
          예약 추가
        </button>
      </div>
    </div>
  );
}
