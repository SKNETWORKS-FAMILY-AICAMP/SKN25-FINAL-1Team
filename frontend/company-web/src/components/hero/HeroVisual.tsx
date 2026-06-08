import { ClipboardList, MessageCircle, Stethoscope } from "lucide-react";
import heroAiWorkflow from "../../assets/hero-ai-workflow.png";

const heroLabels = [
  { label: "AI 문진", Icon: MessageCircle, className: "left-4 top-5 sm:left-6 sm:top-8" },
  { label: "EMR 초안", Icon: ClipboardList, className: "bottom-5 left-5 sm:bottom-8 sm:left-8" },
  { label: "수의사 검토", Icon: Stethoscope, className: "bottom-7 right-4 sm:bottom-10 sm:right-6" },
];

export default function HeroVisual() {
  return (
    <div className="relative">
      <div className="overflow-hidden rounded-[32px] border border-slate-200 bg-white p-3 shadow-soft-xl">
        <div className="relative aspect-[16/10] overflow-hidden rounded-[24px] bg-slate-100">
          <img
            src={heroAiWorkflow}
            alt="수의사와 보호자가 AI 업무 보조 흐름을 함께 확인하는 MediPaw 서비스 이미지"
            className="h-full w-full object-cover"
          />
          <div className="absolute inset-0 bg-[linear-gradient(120deg,rgba(15,33,31,0.24)_0%,rgba(15,33,31,0.04)_48%,rgba(255,255,255,0.14)_100%)]" />
          {heroLabels.map((item) => (
            <div
              key={item.label}
              className={`absolute ${item.className} inline-flex items-center gap-2 rounded-full border border-white/70 bg-white/88 px-3 py-2 text-xs font-black text-blue-800 shadow-lg shadow-slate-900/10 backdrop-blur`}
            >
              <item.Icon className="h-4 w-4" />
              <span className="whitespace-nowrap">{item.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
