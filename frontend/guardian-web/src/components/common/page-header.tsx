import type { ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  description?: string;
  note?: ReactNode;
  rightAction?: ReactNode;
}

const PageHeader = ({
  title,
  description,
  note,
  rightAction,
}: PageHeaderProps) => {
  return (
    <section className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">{title}</h1>

        {description ? (
          <p className="mt-1 text-sm text-slate-500">
            {description}
          </p>
        ) : null}

        {note ? (
          <p className="mt-1 text-[11px] font-medium text-slate-400">
            {note}
          </p>
        ) : null}
      </div>

      {rightAction}
    </section>
  );
};

export default PageHeader;