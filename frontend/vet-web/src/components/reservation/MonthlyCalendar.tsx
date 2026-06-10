import { useMemo } from "react";
import type { ReservationItem } from "../../types/reservation";
import {
  TODAY,
  getDateKey,
  getHolidayName,
  getMonthGrid,
  isSameDate,
} from "../../utils/reservationUtils";

interface MonthlyCalendarProps {
  selectedDate: Date;
  reservations: ReservationItem[];
  onSelectDate: (date: Date) => void;
}

export function MonthlyCalendar({
  selectedDate,
  reservations,
  onSelectDate,
}: MonthlyCalendarProps) {
  const monthDays = getMonthGrid(selectedDate);

  const countByDate = useMemo(() => {
    const map: Record<string, number> = {};
    for (const reservation of reservations) {
      map[reservation.date] = (map[reservation.date] ?? 0) + 1;
    }
    return map;
  }, [reservations]);

  return (
    <div className="flex h-full flex-col">
      <section className="flex h-full flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="grid shrink-0 grid-cols-7 border-b border-slate-200">
          {["일", "월", "화", "수", "목", "금", "토"].map((day) => (
            <div
              key={day}
              className="flex h-10 items-center justify-center border-r border-slate-200 text-sm font-extrabold text-slate-800 last:border-r-0"
            >
              {day}
            </div>
          ))}
        </div>

        <div className="grid flex-1 grid-cols-7 grid-rows-6">
          {monthDays.map((day) => {
            const isCurrentMonth = day.getMonth() === selectedDate.getMonth();
            const isToday = isSameDate(day, TODAY);
            const isSunday = day.getDay() === 0;
            const isSaturday = day.getDay() === 6;
            const holidayName = getHolidayName(day);

            return (
              <button
                key={day.toISOString()}
                type="button"
                onClick={() => onSelectDate(day)}
                className={[
                  "h-full border-r border-b border-slate-100 p-4 text-left transition hover:bg-slate-50",
                  isToday ? "border-blue-600 ring-1 ring-blue-600" : "",
                ].join(" ")}
              >
                <div className="flex items-center gap-3">
                  <span
                    className={[
                      "text-base font-extrabold",
                      !isCurrentMonth
                        ? "text-slate-300"
                        : isSunday || holidayName
                          ? "text-red-500"
                          : isSaturday
                            ? "text-blue-600"
                            : "text-slate-800",
                    ].join(" ")}
                  >
                    {day.getDate()}
                  </span>
                  {holidayName && (
                    <span className="text-xs font-extrabold text-red-500">
                      {holidayName}
                    </span>
                  )}
                  {isToday && (
                    <span className="ml-auto rounded-full bg-blue-600 px-2 py-0.5 text-xs font-extrabold text-white">
                      오늘
                    </span>
                  )}
                </div>
                <span
                  className={[
                    "mt-4 inline-flex rounded-lg px-3 py-1.5 text-sm font-extrabold",
                    isCurrentMonth
                      ? "bg-slate-50 text-slate-800"
                      : "bg-slate-50 text-slate-400",
                  ].join(" ")}
                >
                  총 {countByDate[getDateKey(day)] ?? 0}건
                </span>
              </button>
            );
          })}
        </div>
      </section>
    </div>
  );
}
