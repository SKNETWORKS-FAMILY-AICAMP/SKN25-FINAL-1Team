import type { VisitType } from "../../api/dashboardApi";

const styles: Record<VisitType, { label: string; className: string }> = {
  emergency: {
    label: "응급",
    className: "bg-[#FEE2E2] text-[#DC2626] border-[#FEE2E2]",
  },
  semiEmergency: {
    label: "준응급",
    className: "bg-[#FEF9C3] text-[#CA8A04] border-[#FEF9C3]",
  },
  normal: {
    label: "일반",
    className: "bg-[#E2E8F0] text-[#475569] border-[#E2E8F0]",
  },
  checkup: {
    label: "검진",
    className: "bg-[#E2E8F0] text-[#475569] border-[#E2E8F0]",
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
