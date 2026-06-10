import type { VisitType } from "../../api/dashboardApi";

const styles: Record<VisitType, { label: string; className: string }> = {
  emergency: {
    label: "응급",
    className: "bg-red-50 text-red-500 border-red-100",
  },
  semiEmergency: {
    label: "준응급",
    className: "bg-amber-50 text-amber-600 border-amber-100",
  },
  normal: {
    label: "일반",
    className: "bg-green-50 text-green-700 border-green-100",
  },
  checkup: {
    label: "검진",
    className: "bg-slate-50 text-slate-500 border-slate-200",
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
