interface SectionHeadingProps {
  eyebrow: string;
  title: string;
  description: string;
  align?: "left" | "center";
  inverse?: boolean;
}

export default function SectionHeading({
  eyebrow,
  title,
  description,
  align = "left",
  inverse = false,
}: SectionHeadingProps) {
  const isCenter = align === "center";

  return (
    <div className={["max-w-3xl break-keep", isCenter ? "mx-auto text-center" : ""].join(" ")}>
      <p className={["text-xs font-black uppercase tracking-[0.18em]", inverse ? "text-blue-200" : "text-blue-700"].join(" ")}>
        {eyebrow}
      </p>
      <h2 className={["mt-4 text-4xl font-black leading-tight sm:text-5xl", inverse ? "text-white" : "text-slate-950"].join(" ")}>
        {title}
      </h2>
      <p className={["mt-5 text-base font-semibold leading-8", inverse ? "text-slate-300" : "text-slate-600"].join(" ")}>
        {description}
      </p>
    </div>
  );
}
