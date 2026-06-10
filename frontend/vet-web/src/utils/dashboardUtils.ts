import type {
  DashboardSummaries,
  VisitType,
} from "../api/dashboardApi";

export type SummaryToneKey = "blue" | "orange" | "red" | "green";

export interface SummaryViewModel {
  id: keyof DashboardSummaries;
  label: string;
  value: number;
  tone: SummaryToneKey;
}

export const summaryToneStyle: Record<
  SummaryToneKey,
  { wrapper: string; value: string }
> = {
  blue: {
    wrapper: "bg-slate-50",
    value: "text-blue-500",
  },
  orange: {
    wrapper: "bg-amber-50",
    value: "text-amber-700",
  },
  red: {
    wrapper: "bg-red-50",
    value: "text-red-500",
  },
  green: {
    wrapper: "bg-slate-50",
    value: "text-slate-600",
  },
};

export const visitTypeStyle: Record<
  VisitType,
  { label: string; badge: string; dot: string; card: string }
> = {
  emergency: {
    label: "응급",
    badge: "border-red-100 bg-red-50 text-red-500",
    dot: "bg-red-500",
    card: "border-red-100 bg-red-50 text-slate-800 before:bg-red-500",
  },
  semiEmergency: {
    label: "준응급",
    badge: "border-amber-100 bg-amber-50 text-amber-600",
    dot: "bg-amber-600",
    card: "border-amber-100 bg-amber-50 text-slate-800 before:bg-amber-600",
  },
  normal: {
    label: "일반",
    badge: "border-green-100 bg-green-50 text-green-700",
    dot: "bg-green-500",
    card: "border-green-100 bg-green-50 text-slate-800 before:bg-green-500",
  },
  checkup: {
    label: "검진/일반예약",
    badge: "border-slate-200 bg-slate-50 text-slate-500",
    dot: "bg-slate-400",
    card: "border-slate-200 bg-slate-50 text-slate-800 before:bg-slate-400",
  },
};

const dayLabels = ["일", "월", "화", "수", "목", "금", "토"];

export function formatSelectedDate(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");

  return `${year}.${month}.${day} (${dayLabels[date.getDay()]})`;
}

export function formatApiDate(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
}

export function addDays(date: Date, amount: number) {
  const nextDate = new Date(date);
  nextDate.setDate(nextDate.getDate() + amount);
  return nextDate;
}

export function createSummaryCards(
  summaries: DashboardSummaries
): SummaryViewModel[] {
  return [
    { id: "total", label: "전체 예약", value: summaries.total, tone: "blue" },
    { id: "waiting", label: "대기 중", value: summaries.waiting, tone: "orange" },
    { id: "emergency", label: "응급", value: summaries.emergency, tone: "red" },
    { id: "completed", label: "진료 완료", value: summaries.completed, tone: "green" },
  ];
}
