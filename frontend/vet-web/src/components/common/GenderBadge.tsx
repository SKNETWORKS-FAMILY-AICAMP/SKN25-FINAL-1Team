import { normalizeGender } from "../../utils/genderUtils";

const styles = {
  female:  { symbol: "♀", label: "암컷",      colorClass: "text-[#f43f7c]" },
  male:    { symbol: "♂", label: "수컷",      colorClass: "text-[#4a89ff]" },
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
