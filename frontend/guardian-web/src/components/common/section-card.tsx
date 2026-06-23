import type { HTMLAttributes, ReactNode } from "react";

type SectionCardPadding = "default" | "none";

interface SectionCardProps extends HTMLAttributes<HTMLElement> {
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
  ...sectionProps
}: SectionCardProps) => {
  return (
    <section
      {...sectionProps}
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
