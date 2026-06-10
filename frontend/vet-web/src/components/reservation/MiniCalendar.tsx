import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import {
  TODAY,
  addMonths,
  formatMonthTitle,
  getHolidayName,
  getMonthGrid,
  isSameDate,
} from "../../utils/reservationUtils";

interface MiniCalendarProps {
  selectedDate: Date;
  onSelectDate: (date: Date) => void;
}

export function MiniCalendar({
  selectedDate,
  onSelectDate,
}: MiniCalendarProps) {
  const [visibleMonth, setVisibleMonth] = useState(
    new Date(selectedDate.getFullYear(), selectedDate.getMonth(), 1)
  );
  const days = getMonthGrid(visibleMonth);

  useEffect(() => {
    setVisibleMonth(new Date(selectedDate.getFullYear(), selectedDate.getMonth(), 1));
  }, [selectedDate]);

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 grid grid-cols-[32px_1fr_32px] items-center">
        <button
          type="button"
          onClick={() => setVisibleMonth((month) => addMonths(month, -1))}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-600 transition hover:bg-slate-50 hover:text-blue-600"
          aria-label="이전 달"
        >
          <ChevronLeft className="h-5 w-5" />
        </button>
        <h2 className="text-center text-base font-extrabold text-slate-900">
          {formatMonthTitle(visibleMonth)}
        </h2>
        <button
          type="button"
          onClick={() => setVisibleMonth((month) => addMonths(month, 1))}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-600 transition hover:bg-slate-50 hover:text-blue-600"
          aria-label="다음 달"
        >
          <ChevronRight className="h-5 w-5" />
        </button>
      </div>
      <div className="grid grid-cols-7 gap-y-1.5 text-center text-xs font-extrabold text-slate-600">
        {["일", "월", "화", "수", "목", "금", "토"].map((day) => (
          <span key={day}>{day}</span>
        ))}
        {days.map((day) => {
          const isToday = isSameDate(day, TODAY);
          const isSelected = isSameDate(day, selectedDate);
          const holidayName = getHolidayName(day);
          const isRed = day.getDay() === 0;
          const isMuted = day.getMonth() !== visibleMonth.getMonth();

          return (
            <button
              key={day.toISOString()}
              type="button"
              title={holidayName}
              onClick={() => {
                onSelectDate(day);
                setVisibleMonth(new Date(day.getFullYear(), day.getMonth(), 1));
              }}
              className={[
                "mx-auto flex h-7 w-7 items-center justify-center rounded-full text-xs font-extrabold",
                isToday
                  ? "bg-blue-600 text-white"
                  : isSelected
                    ? "bg-blue-50 text-blue-600"
                    : isRed || holidayName
                      ? "text-red-500"
                      : isMuted
                        ? "text-slate-400"
                        : "text-slate-800 hover:bg-blue-50",
              ].join(" ")}
            >
              {day.getDate()}
            </button>
          );
        })}
      </div>
    </section>
  );
}
