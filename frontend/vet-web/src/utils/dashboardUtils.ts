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
    wrapper: "bg-[#FFEFEF]",
    value: "text-[#E11D48]",
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
    badge: "border-[#FECDD3] bg-[#FFEFEF] text-[#E11D48]",
    dot: "bg-[#E11D48]",
    card: "border-[#FECDD3] bg-white text-slate-800 before:bg-[#E11D48]",
  },
  semiEmergency: {
    label: "준응급",
    badge: "border-[#FDE68A] bg-[#FFFBEB] text-[#D97706]",
    dot: "bg-[#D97706]",
    card: "border-[#FDE68A] bg-white text-slate-800 before:bg-[#D97706]",
  },
  normal: {
    label: "일반",
    badge: "border-[#CBD5E1] bg-[#F1F5F9] text-[#475569]",
    dot: "bg-teal-500",
    card: "border-slate-200 bg-white text-slate-800 before:bg-teal-500",
  },
  checkup: {
    label: "검진/일반예약",
    badge: "border-[#CEEAD6] bg-[#E6F4EA] text-[#137333]",
    dot: "bg-teal-500",
    card: "border-slate-200 bg-white text-slate-800 before:bg-teal-500",
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
