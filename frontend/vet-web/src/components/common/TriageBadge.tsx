import type { VisitType } from "../../api/dashboardApi";

const styles: Record<VisitType, { label: string; className: string }> = {
  emergency: {
    label: "응급",
    className: "bg-[#FFEFEF] text-[#E11D48] border-[#FECDD3]",
  },
  semiEmergency: {
    label: "준응급",
    className: "bg-[#FFFBEB] text-[#D97706] border-[#FDE68A]",
  },
  normal: {
    label: "일반",
    className: "bg-[#F1F5F9] text-[#475569] border-[#CBD5E1]",
  },
  checkup: {
    label: "검진",
    className: "bg-[#E6F4EA] text-[#137333] border-[#CEEAD6]",
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
