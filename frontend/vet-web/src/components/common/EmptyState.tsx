interface EmptyStateProps {
  text: string;
  className?: string;
}

export function EmptyState({ text, className = "" }: EmptyStateProps) {
  return (
    <div
      className={`flex flex-1 items-center justify-center py-24 text-sm font-extrabold text-slate-500 ${className}`}
    >
      {text}
    </div>
  );
}
