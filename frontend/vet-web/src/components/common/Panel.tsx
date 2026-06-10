import type { ReactNode } from "react";

interface PanelProps {
  children: ReactNode;
  className?: string;
}

export function Panel({ children, className = "" }: PanelProps) {
  return (
    <section
      className={`rounded-lg border border-slate-200 bg-white shadow-sm ${className}`}
    >
      {children}
    </section>
  );
}
