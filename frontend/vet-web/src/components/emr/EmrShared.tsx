import type { ReactNode } from "react";
import type { TriageStatus } from "../../types/emr";
import { TriageBadge } from "../common/TriageBadge";

export function Panel({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-md border border-slate-200 bg-white shadow-sm ${className}`}
    >
      {children}
    </section>
  );
}

export function StatusBadge({ status }: { status: TriageStatus }) {
  return <TriageBadge level={status} />;
}
