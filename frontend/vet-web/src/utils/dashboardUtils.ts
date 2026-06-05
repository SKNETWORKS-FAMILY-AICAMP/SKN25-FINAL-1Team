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
    value: "text-[#357b70]",
  },
  orange: {
    wrapper: "bg-[#faf6ed]",
    value: "text-[#b45309]",
  },
  red: {
    wrapper: "bg-[#faeded]",
    value: "text-[#ef4444]",
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
    badge: "border-[#fee2e2] bg-[#fef2f2] text-[#ef4444]",
    dot: "bg-[#ef4444]",
    card: "border-[#fee2e2] bg-[#fef2f2] text-[#20283a] before:bg-[#ef4444]",
  },
  semiEmergency: {
    label: "준응급",
    badge: "border-[#fef3c7] bg-[#fffbeb] text-[#d97706]",
    dot: "bg-[#d97706]",
    card: "border-[#fef3c7] bg-[#fffbeb] text-[#20283a] before:bg-[#d97706]",
  },
  normal: {
    label: "일반",
    badge: "border-[#dcfce7] bg-[#f0fdf4] text-[#15803d]",
    dot: "bg-[#22c55e]",
    card: "border-[#dcfce7] bg-[#f0fdf4] text-[#20283a] before:bg-[#22c55e]",
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
