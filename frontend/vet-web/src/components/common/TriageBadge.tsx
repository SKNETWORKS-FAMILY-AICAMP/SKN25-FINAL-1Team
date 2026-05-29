import type { VisitType } from "../../api/dashboardApi";

const styles: Record<VisitType, { label: string; className: string }> = {
  emergency: {
    label: "응급",
    className: "bg-[#fff1f2] text-[#ef4444] border-[#fecdd3]",
  },
  semiEmergency: {
    label: "준응급",
    className: "bg-[#fff7ed] text-[#f97316] border-[#fed7aa]",
  },
  normal: {
    label: "일반",
    className: "bg-[#eff6ff] text-[#2563eb] border-[#bfdbfe]",
  },
  checkup: {
    label: "검진",
    className: "bg-[#f8fafc] text-[#64748b] border-[#e2e8f0]",
  },
};

export function TriageBadge({ level }: { level: VisitType }) {
  const { label, className } = styles[level];
  return (
    <span
      className={`inline-flex h-5 items-center rounded-md border px-2 text-[11px] font-extrabold ${className}`}
    >
      {label}
    </span>
  );
}
