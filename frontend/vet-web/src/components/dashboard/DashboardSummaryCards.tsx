import type { SummaryViewModel } from "../../utils/dashboardUtils";
import { summaryToneStyle } from "../../utils/dashboardUtils";

interface DashboardSummaryCardsProps {
  summaries: SummaryViewModel[];
  className?: string;
}

export function DashboardSummaryCards({
  summaries,
  className = "",
}: DashboardSummaryCardsProps) {
  return (
    <div className={`grid w-fit grid-cols-4 gap-3 ${className}`}>
      {summaries.map((summary) => (
        <SummaryCard key={summary.id} summary={summary} />
      ))}
    </div>
  );
}

function SummaryCard({ summary }: { summary: SummaryViewModel }) {
  const tone = summaryToneStyle[summary.tone];

  return (
    <article className={`flex h-20 w-36 flex-col justify-center rounded-lg px-4 ${tone.wrapper}`}>
      <p className={`text-2xl font-extrabold leading-none tabular-nums ${tone.value}`}>
        {summary.value}
      </p>
      <p className="mt-2 text-xs font-extrabold text-[#717b8d]">
        {summary.label}
      </p>
    </article>
  );
}
