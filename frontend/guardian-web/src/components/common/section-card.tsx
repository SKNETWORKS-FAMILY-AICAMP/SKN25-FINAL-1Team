import type { ReactNode } from "react";

type SectionCardPadding = "default" | "none";

interface SectionCardProps {
  children: ReactNode;
  className?: string;
  padding?: SectionCardPadding;
}

const paddingClassName: Record<SectionCardPadding, string> = {
  default: "p-8",
  none: "p-0",
};

const SectionCard = ({
  children,
  className = "",
  padding = "default",
}: SectionCardProps) => {
  return (
    <section
      className={[
        "w-full rounded-2xl border border-slate-100 bg-white shadow-sm",
        paddingClassName[padding],
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {children}
    </section>
  );
};

export default SectionCard;
