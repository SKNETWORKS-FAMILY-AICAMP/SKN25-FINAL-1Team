import { normalizeGender } from "../../utils/genderUtils";

const styles = {
  female:  { symbol: "♀", label: "암컷",      colorClass: "text-[#e06666]" },
  male:    { symbol: "♂", label: "수컷",      colorClass: "text-[#2f9b9d]" },
  unknown: { symbol: "-", label: "성별 모름",  colorClass: "text-[#a8b0bf]" },
};

export function GenderBadge({
  gender,
  className,
}: {
  gender?: string;
  className?: string;
}) {
  const { symbol, label, colorClass } = styles[normalizeGender(gender)];
  return (
    <span className={`font-extrabold ${colorClass} ${className ?? ""}`} aria-label={label}>
      {symbol}
    </span>
  );
}
