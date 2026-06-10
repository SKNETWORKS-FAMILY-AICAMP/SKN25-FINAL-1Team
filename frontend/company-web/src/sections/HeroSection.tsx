import { CheckCircle2, Sparkles } from "lucide-react";
import CtaButtons from "../components/common/CtaButtons";
import HeroVisual from "../components/hero/HeroVisual";

export default function HeroSection() {
  return (
    <section className="relative bg-white">
      <div className="absolute inset-x-0 top-0 h-72 bg-[linear-gradient(180deg,#eef5f4_0%,rgba(238,245,244,0)_100%)]" />
      <div className="relative mx-auto grid min-h-[calc(100vh-64px)] w-full max-w-7xl grid-cols-1 items-center gap-12 px-4 py-16 sm:px-6 lg:grid-cols-[1fr_1.05fr] lg:px-8 lg:py-20">
        <div className="max-w-4xl break-keep">
          <div className="inline-flex items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-3 py-1 text-xs font-extrabold text-blue-700">
            <Sparkles className="h-3.5 w-3.5" />
            동물병원 전용 AI 업무 보조 플랫폼
          </div>
          <h1 className="mt-6 text-5xl font-black leading-[1.08] text-slate-950 sm:text-6xl lg:text-6xl xl:text-7xl">
            <span className="block">보호자 문진부터 진료 준비까지,</span>
            <span className="mt-2 block text-blue-700">AI가 미리 정리합니다.</span>
          </h1>
          <p className="mt-6 max-w-3xl text-lg font-semibold leading-8 text-slate-600">
            보호자 문진부터 예약, EMR 초안까지 한 흐름으로 이어
            <br className="hidden lg:block" /> 수의사가 진료에 더 집중하도록 돕는 동물병원 업무 보조 플랫폼입니다.
          </p>

          <div className="mt-9">
            <CtaButtons size="large" />
          </div>

          <div className="mt-10 grid max-w-2xl grid-cols-1 gap-3 sm:grid-cols-3">
            {["문진 구조화", "신호 표시", "EMR 초안"].map((item) => (
              <div key={item} className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3">
                <CheckCircle2 className="h-4 w-4 text-blue-700" />
                <p className="mt-2 text-sm font-extrabold text-slate-800">{item}</p>
              </div>
            ))}
          </div>
        </div>

        <HeroVisual />
      </div>
    </section>
  );
}
