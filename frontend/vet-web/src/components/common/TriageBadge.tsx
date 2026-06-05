import type { VisitType } from "../../api/dashboardApi";

const styles: Record<VisitType, { label: string; className: string }> = {
  emergency: {
    label: "응급",
    className: "bg-[#fcefef] text-[#e06666] border-[#f9dcdc]",
  },
  semiEmergency: {
    label: "준응급",
    className: "bg-[#faf3e1] text-[#cf9f38] border-[#f4e6bf]",
  },
  normal: {
    label: "일반",
    className: "bg-[#eef5f0] text-[#437455] border-[#d7e8dd]",
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
      className={`inline-flex h-5 items-center rounded-md border px-2 text-[11px] font-extrabold ${className}`}
    >
      {label}
    </span>
  );
}
