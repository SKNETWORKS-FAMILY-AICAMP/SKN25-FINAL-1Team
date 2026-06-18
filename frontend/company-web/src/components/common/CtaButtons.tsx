import { ArrowRight, Stethoscope, UserRound } from "lucide-react";

interface CtaButtonsProps {
  size?: "default" | "large";
  align?: "left" | "center";
  onGuardianClick?: () => void;
  onVetClick?: () => void;
}

export default function CtaButtons({ size = "default", align = "left", onGuardianClick, onVetClick }: CtaButtonsProps) {
  const heightClass = size === "large" ? "h-12 px-6" : "";

  return (
    <div className={["flex flex-col gap-3 sm:flex-row", align === "center" ? "justify-center" : ""].join(" ")}>
      <button
        type="button"
        onClick={onGuardianClick}
        className={`mp-btn-secondary ${heightClass}`}
      >
        <UserRound className="mr-2 h-4 w-4" />
        보호자 웹 보기
      </button>
      <button
        type="button"
        onClick={onVetClick}
        className={`mp-btn-primary ${heightClass}`}
      >
        <Stethoscope className="mr-2 h-4 w-4" />
        수의사 웹 보기
        {size !== "large" && <ArrowRight className="ml-2 h-4 w-4" />}
      </button>
    </div>
  );
}
