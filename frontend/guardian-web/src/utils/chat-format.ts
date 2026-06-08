import type { Language } from "../i18n/translations";

export const localeForLang = (lang: Language) =>
  ({ ko: "ko-KR", en: "en-US", ja: "ja-JP", zh: "zh-CN" })[lang];

export const weekdayOf = (dateStr: string, lang: Language) =>
  new Intl.DateTimeFormat(localeForLang(lang), { weekday: "short" }).format(
    new Date(dateStr),
  );

export const formatChatTime = (
  hhmm: string,
  t: (key: string, vars?: Record<string, string | number>) => string,
): string => {
  const [h, m] = hhmm.split(":").map(Number);
  const period = h < 12 ? t("chatbot.am") : t("chatbot.pm");
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return `${period} ${h12}:${String(m).padStart(2, "0")}`;
};

export const formatChatDuration = (
  min: number,
  t: (key: string, vars?: Record<string, string | number>) => string,
): string => {
  const h = Math.floor(min / 60);
  const m = min % 60;
  if (h && m) return t("chatbot.durationHourMin", { h, m });
  if (h) return t("chatbot.durationHour", { h });
  return t("chatbot.durationMin", { m });
};

export const formatChatMonthDay = (
  dateStr: string,
  t: (key: string, vars?: Record<string, string | number>) => string,
) => {
  const [, month, day] = dateStr.split("-");
  return t("chatbot.monthDay", { month: Number(month), day: Number(day) });
};

export const formatChatDateTimeFull = (
  dateStr: string,
  time: string,
  lang: Language,
  t: (key: string, vars?: Record<string, string | number>) => string,
) => {
  const [year, month, day] = dateStr.split("-");
  return t("chatbot.dateTextFull", {
    year,
    month: Number(month),
    day: Number(day),
    weekday: weekdayOf(dateStr, lang),
    time: formatChatTime(time, t),
  });
};
