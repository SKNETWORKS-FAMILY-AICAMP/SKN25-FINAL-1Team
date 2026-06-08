import type { VisitType } from "../../api/dashboardApi";

const styles: Record<VisitType, { label: string; className: string }> = {
  emergency: {
    label: "응급",
    className: "bg-[#fef2f2] text-[#ef4444] border-[#fee2e2]",
  },
  semiEmergency: {
    label: "준응급",
    className: "bg-[#fffbeb] text-[#d97706] border-[#fef3c7]",
  },
  normal: {
    label: "일반",
    className: "bg-[#f0fdf4] text-[#15803d] border-[#dcfce7]",
  },
  checkup: {
    label: "검진",
    className: "bg-[#f9fafb] text-[#64748b] border-[#e2e8f0]",
  },
};

export function TriageBadge({ level }: { level: VisitType }) {
  const { label, className } = styles[level];
  return (
    <span
      className={`inline-flex h-6 shrink-0 items-center whitespace-nowrap rounded-md border px-2 text-xs font-extrabold ${className}`}
    >
      {label}
    </span>
  );
}
