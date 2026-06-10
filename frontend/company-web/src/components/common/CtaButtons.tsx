import { ArrowRight, Stethoscope, UserRound } from "lucide-react";
import { siteConfig } from "../../config/site";

interface CtaButtonsProps {
  size?: "default" | "large";
  align?: "left" | "center";
}

export default function CtaButtons({ size = "default", align = "left" }: CtaButtonsProps) {
  const heightClass = size === "large" ? "h-12 px-6" : "";

  return (
    <div className={["flex flex-col gap-3 sm:flex-row", align === "center" ? "justify-center" : ""].join(" ")}>
      <a
        href={siteConfig.guardianWebUrl}
        target="_blank"
        rel="noopener noreferrer"
        className={`mp-btn-secondary ${heightClass}`}
      >
        <UserRound className="mr-2 h-4 w-4" />
        보호자 웹 보기
      </a>
      <a
        href={siteConfig.vetWebUrl}
        target="_blank"
        rel="noopener noreferrer"
        className={`mp-btn-primary ${heightClass}`}
      >
        <Stethoscope className="mr-2 h-4 w-4" />
        수의사 웹 보기
        {size !== "large" && <ArrowRight className="ml-2 h-4 w-4" />}
      </a>
    </div>
  );
}
