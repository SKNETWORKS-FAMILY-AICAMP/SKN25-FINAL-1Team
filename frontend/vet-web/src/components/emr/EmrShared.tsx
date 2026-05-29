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
      className={`rounded-lg border border-[#e4e9f1] bg-white shadow-sm ${className}`}
    >
      {children}
    </section>
  );
}

export function StatusBadge({ status }: { status: TriageStatus }) {
  return <TriageBadge level={status} />;
}
