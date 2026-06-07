import { isAxiosError } from "axios";

import type {
  ApiErrorResponse,
  ScheduleFilter,
  ScheduleListItem,
  ScheduleStatus,
} from "../../types/schedule";

export const pageSize = 10;
const kstOffset = "+09:00";

const defaultProfileImages = [
  "/assets/profile1.png",
  "/assets/profile2.png",
  "/assets/profile3.png",
  "/assets/profile4.png",
  "/assets/profile5.png",
  "/assets/profile6.png",
];

export const scheduleTabs: Array<{ filter: ScheduleFilter; labelKey: string }> = [
  { filter: "all", labelKey: "schedule.tabAll" },
  { filter: "upcoming", labelKey: "schedule.tabUpcoming" },
  { filter: "past", labelKey: "schedule.tabPast" },
  { filter: "cancelled", labelKey: "schedule.tabCancelled" },
];

export const scheduleStatusKey: Record<ScheduleStatus, string> = {
  PENDING: "schedule.statusPending",
  CONFIRMED: "schedule.statusConfirmed",
  COMPLETED: "schedule.statusCompleted",
  CANCELLED: "schedule.statusCancelled",
};

export const normalizeScheduleStatus = (
  status?: string | null,
): ScheduleStatus => {
  if (status === "예약대기" || status === "대기") return "PENDING";
  if (status === "예약확정") return "CONFIRMED";
  if (status === "진료완료") return "COMPLETED";
  if (status === "예약취소" || status === "취소") return "CANCELLED";
  if (
    status === "PENDING" ||
    status === "CONFIRMED" ||
    status === "COMPLETED" ||
    status === "CANCELLED"
  ) {
    return status;
  }
  return "PENDING";
};

export const getScheduleStatusLabelKey = (status?: string | null) =>
  scheduleStatusKey[normalizeScheduleStatus(status)];

// i18n 언어 코드 → Intl 로케일 (날짜·시간 포맷용)
export const localeForLang = (lang: string): string =>
  ({ ko: "ko-KR", en: "en-US", ja: "ja-JP", zh: "zh-CN" })[lang] || "ko-KR";

export const getErrorMessage = (
  error: unknown,
  fallbackMessage: string,
) => {
  if (isAxiosError<ApiErrorResponse | string>(error)) {
    const responseData = error.response?.data;

    if (typeof responseData === "string") {
      try {
        return (
          (JSON.parse(responseData) as ApiErrorResponse).message ||
          fallbackMessage
        );
      } catch {
        return fallbackMessage;
      }
    }

    return responseData?.message || fallbackMessage;
  }

  return fallbackMessage;
};

export const formatDateInput = (date: Date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
};

export const formatScheduleDateTime = (isoDate?: string | null, locale = "ko-KR") => {
  if (!isoDate) return "";

  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) return "";

  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
};

export const formatScheduleTimeRange = (
  startTime: string,
  endTime: string,
  locale = "ko-KR",
) => {
  const end = new Date(endTime);

  return `${formatScheduleDateTime(startTime, locale)} - ${String(
    end.getHours(),
  ).padStart(2, "0")}:${String(end.getMinutes()).padStart(2, "0")}`;
};

export const getProfileImage = (schedule: ScheduleListItem) =>
  schedule.pet_profile_image ||
  defaultProfileImages[Math.abs(schedule.pet_id) % defaultProfileImages.length];

export const canManageSchedule = (schedule: ScheduleListItem) =>
  normalizeScheduleStatus(schedule.status) === "CONFIRMED" &&
  new Date(schedule.confirmed_time) > new Date();

export const buildKstDateTime = (date: string, time: string) =>
  `${date}T${time}:00${kstOffset}`;
