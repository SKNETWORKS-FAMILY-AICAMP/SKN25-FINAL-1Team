import type { ReactNode } from "react";

interface IconButtonProps {
  label: string;
  onClick: () => void;
  children: ReactNode;
}

export function IconButton({ label, onClick, children }: IconButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="flex h-11 w-11 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600"
    >
      {children}
    </button>
  );
}
