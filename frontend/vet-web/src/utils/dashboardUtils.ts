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
    wrapper: "bg-[#f5f7f8]",
    value: "text-[#2f9b9d]",
  },
  orange: {
    wrapper: "bg-[#faf6ed]",
    value: "text-[#b3842c]",
  },
  red: {
    wrapper: "bg-[#faeded]",
    value: "text-[#e06666]",
  },
  green: {
    wrapper: "bg-[#f3f5f7]",
    value: "text-[#475569]",
  },
};

export const visitTypeStyle: Record<
  VisitType,
  { label: string; badge: string; dot: string; card: string }
> = {
  emergency: {
    label: "응급",
    badge: "border-[#f9dcdc] bg-[#fcefef] text-[#e06666]",
    dot: "bg-[#e06666]",
    card: "border-[#f9dcdc] bg-[#fdf9f9] text-[#20283a] before:bg-[#e06666]",
  },
  semiEmergency: {
    label: "준응급",
    badge: "border-[#f4e6bf] bg-[#faf3e1] text-[#cf9f38]",
    dot: "bg-[#cf9f38]",
    card: "border-[#f4e6bf] bg-[#fcf9f3] text-[#20283a] before:bg-[#cf9f38]",
  },
  normal: {
    label: "일반",
    badge: "border-[#d7e8dd] bg-[#eef5f0] text-[#437455]",
    dot: "bg-[#6ba881]",
    card: "border-[#d7e8dd] bg-[#f8fcfa] text-[#20283a] before:bg-[#6ba881]",
  },
  checkup: {
    label: "검진/일반예약",
    badge: "border-[#e2e8f0] bg-[#f9fafb] text-[#64748b]",
    dot: "bg-[#94a3b8]",
    card: "border-[#e2e8f0] bg-[#f9fafb] text-[#20283a] before:bg-[#94a3b8]",
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
