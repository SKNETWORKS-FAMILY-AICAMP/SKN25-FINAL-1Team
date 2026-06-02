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
    wrapper: "bg-[#eef4ff]",
    value: "text-[#4a6cff]",
  },
  orange: {
    wrapper: "bg-[#fff8e8]",
    value: "text-[#e97700]",
  },
  red: {
    wrapper: "bg-[#ffe8eb]",
    value: "text-[#ef3333]",
  },
  green: {
    wrapper: "bg-[#f1f5f9]",
    value: "text-[#475569]",
  },
};

export const visitTypeStyle: Record<
  VisitType,
  { label: string; badge: string; dot: string; card: string }
> = {
  emergency: {
    label: "응급",
    badge: "border-[#fecdd3] bg-[#fff1f2] text-[#ef4444]",
    dot: "bg-[#ef4444]",
    card: "border-[#fecdd3] bg-[#fff7f8] text-[#20283a] before:bg-[#ef4444]",
  },
  semiEmergency: {
    label: "준응급",
    badge: "border-[#fed7aa] bg-[#fff7ed] text-[#f97316]",
    dot: "bg-[#f97316]",
    card: "border-[#fed7aa] bg-[#fffaf0] text-[#20283a] before:bg-[#f97316]",
  },
  normal: {
    label: "일반",
    badge: "border-[#cfe3d7] bg-[#f6fbf8] text-[#3f7f5f]",
    dot: "bg-[#6fa989]",
    card: "border-[#cfe3d7] bg-[#f8fcfa] text-[#20283a] before:bg-[#6fa989]",
  },
  checkup: {
    label: "검진/일반예약",
    badge: "border-[#e2e8f0] bg-[#f8fafc] text-[#64748b]",
    dot: "bg-[#94a3b8]",
    card: "border-[#e2e8f0] bg-[#f8fafc] text-[#20283a] before:bg-[#94a3b8]",
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
