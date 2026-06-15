import type { DaySchedule } from "../../api/settingsApi";

export const DAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"];

export const timeOptions = [
  "08:00", "08:30", "09:00", "09:30", "10:00", "10:30",
  "11:00", "11:30", "12:00", "12:30", "13:00", "13:30",
  "14:00", "14:30", "15:00", "15:30", "16:00", "16:30",
  "17:00", "17:30", "18:00", "18:30", "19:00", "19:30",
  "20:00", "20:30", "21:00", "21:30", "22:00", "22:30", "23:00",
];

export const defaultWeek: DaySchedule[] = Array.from({ length: 7 }, (_, i) => ({
  day_of_week: i,
  is_open: i < 5,
  start_time: i < 5 ? "09:00" : null,
  end_time: i < 5 ? "18:00" : null,
  lunch_start: i < 5 ? "12:00" : null,
  lunch_end: i < 5 ? "13:00" : null,
}));

export function Toggle({ checked, onChange }: { checked: boolean; onChange: () => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={onChange}
      className={`relative inline-flex h-6 w-11 shrink-0 rounded-full transition-colors duration-200 ${
        checked ? "bg-blue-600" : "bg-slate-200"
      }`}
    >
      <span
        className={`inline-block h-5 w-5 rounded-full bg-white shadow transition-transform duration-200 m-0.5 ${
          checked ? "translate-x-5" : "translate-x-0"
        }`}
      />
    </button>
  );
}

export function InlineTimeSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="h-8 rounded-lg border border-slate-200 bg-white px-2 text-xs font-extrabold text-slate-800 outline-none transition focus:border-blue-300 focus:ring-2 focus:ring-blue-50"
    >
      {timeOptions.map((t) => (
        <option key={t} value={t}>{t}</option>
      ))}
    </select>
  );
}
