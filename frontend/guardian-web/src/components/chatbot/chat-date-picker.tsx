import { useEffect, useState } from "react";
import { getAvailableScheduleSlots } from "../../api/schedule-api";
import { useTranslation } from "../../i18n/language-context";
import type { Language } from "../../i18n/translations";

interface ChatDatePickerProps {
  onSelectSlot: (date: string, time: string, doctorid: number, label: string) => void;
  onCancel: () => void;
  /** 진료 소요시간(분). 추천 슬롯이 실제 예약 소요시간과 어긋나지 않도록 확정과 동일한 값을 받는다. */
  durationMin: number;
}

const fmt2 = (n: number) => String(n).padStart(2, "0");

const localeForLang = (lang: Language) =>
  ({ ko: "ko-KR", en: "en-US", ja: "ja-JP", zh: "zh-CN" })[lang];

const toDateStr = (d: Date) =>
  `${d.getFullYear()}-${fmt2(d.getMonth() + 1)}-${fmt2(d.getDate())}`;

const ChatDatePicker = ({ onSelectSlot, onCancel, durationMin }: ChatDatePickerProps) => {
  const { lang, t } = useTranslation();
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const [viewYear, setViewYear] = useState(today.getFullYear());
  const [viewMonth, setViewMonth] = useState(today.getMonth());
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);
  const [slots, setSlots] = useState<{ start_time: string; doctorid?: number }[]>([]);
  const [loadingSlots, setLoadingSlots] = useState(false);

  // 달력 셀 생성
  const firstDay = new Date(viewYear, viewMonth, 1).getDay();
  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
  const cells: (Date | null)[] = [
    ...Array(firstDay).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => new Date(viewYear, viewMonth, i + 1)),
  ];

  const prevMonth = () => {
    if (viewMonth === 0) { setViewYear(y => y - 1); setViewMonth(11); }
    else setViewMonth(m => m - 1);
  };
  const nextMonth = () => {
    if (viewMonth === 11) { setViewYear(y => y + 1); setViewMonth(0); }
    else setViewMonth(m => m + 1);
  };

  // 날짜 선택 시 슬롯 조회
  useEffect(() => {
    if (!selectedDate) return;
    setSlots([]);
    setLoadingSlots(true);
    getAvailableScheduleSlots({ date: toDateStr(selectedDate), duration_min: durationMin })
      .then(resp => { if (resp.code === 200) setSlots(resp.result); })
      .catch(() => {})
      .finally(() => setLoadingSlots(false));
  }, [selectedDate, durationMin]);

  const isSelectable = (d: Date | null) => {
    if (!d) return false;
    const diff = (d.getTime() - today.getTime()) / 86400000;
    return diff >= 0 && diff <= 30;
  };

  const isSelected = (d: Date | null) =>
    d && selectedDate && toDateStr(d) === toDateStr(selectedDate);

  const weekdays = Array.from({ length: 7 }, (_, index) =>
    new Intl.DateTimeFormat(localeForLang(lang), { weekday: "short" }).format(
      new Date(2026, 1, index + 1),
    ),
  );

  return (
    <div className="w-80 rounded-2xl border border-blue-100 bg-white px-4 py-3 shadow-xl">
      {/* 달력 헤더 */}
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-sm font-extrabold text-slate-800">
          {t("chatbot.pickerMonth", { year: viewYear, month: viewMonth + 1 })}
        </span>
        <div className="flex gap-0.5">
          <button
            type="button"
            onClick={prevMonth}
            className="rounded px-2 py-0.5 text-xs font-extrabold text-slate-500 hover:bg-blue-50"
          >
            ◀
          </button>
          <button
            type="button"
            onClick={nextMonth}
            className="rounded px-2 py-0.5 text-xs font-extrabold text-slate-500 hover:bg-blue-50"
          >
            ▶
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="ml-1 rounded px-1.5 py-0.5 text-[10px] font-extrabold text-slate-400 hover:bg-white hover:text-rose-500"
          >
            {t("chatbot.pickerClose")}
          </button>
        </div>
      </div>

      {/* 요일 헤더 */}
      <div className="mb-0.5 grid grid-cols-7 text-center">
        {weekdays.map((d, i) => (
          <span
            key={d}
            className={`text-[11px] font-extrabold ${i === 0 ? "text-rose-400" : i === 6 ? "text-blue-500" : "text-slate-400"}`}
          >
            {d}
          </span>
        ))}
      </div>

      {/* 날짜 셀 */}
      <div className="grid grid-cols-7 gap-px">
        {cells.map((d, idx) => {
          const selectable = isSelectable(d);
          const selected = isSelected(d);
          const isPast = d && d.getTime() < today.getTime();
          return (
            <button
              key={idx}
              type="button"
              disabled={!selectable}
              onClick={() => d && selectable && setSelectedDate(d)}
              className={[
                "h-8 w-full rounded-lg text-xs font-bold transition",
                !d ? "invisible" : "",
                selected ? "bg-blue-600 text-white shadow-sm" : "",
                !selected && selectable ? "hover:bg-white text-slate-700" : "",
                !selected && isPast ? "text-slate-300 cursor-not-allowed" : "",
                !selected && !selectable && !isPast ? "text-slate-300 cursor-not-allowed" : "",
              ].join(" ")}
            >
              {d?.getDate()}
            </button>
          );
        })}
      </div>

      {/* 선택된 날짜의 슬롯 */}
      {selectedDate && (
        <div className="mt-2">
          <p className="mb-1.5 text-[10px] font-extrabold text-slate-600">
            {t("chatbot.pickerAvailableTime", {
              month: selectedDate.getMonth() + 1,
              day: selectedDate.getDate(),
            })}
          </p>
          {loadingSlots ? (
            <p className="text-[10px] text-slate-400">
              {t("chatbot.pickerLoadingSlots")}
            </p>
          ) : slots.length === 0 ? (
            <p className="text-[10px] text-slate-400">
              {t("chatbot.pickerNoSlots")}
            </p>
          ) : (
            <div className="flex flex-wrap gap-1">
              {slots.map(s => {
                const time = s.start_time.slice(0, 5);
                const [, m, dd] = toDateStr(selectedDate).split("-");
                const label = t("chatbot.slotLabel", {
                  month: Number(m),
                  day: Number(dd),
                  time,
                });
                return (
                  <button
                    key={s.start_time}
                    type="button"
                    onClick={() =>
                      onSelectSlot(toDateStr(selectedDate), time, s.doctorid ?? 1, label)
                    }
                    className="rounded-full bg-blue-600 px-2.5 py-1 text-[10px] font-extrabold text-white shadow-sm transition hover:bg-blue-700"
                  >
                    {time}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ChatDatePicker;
