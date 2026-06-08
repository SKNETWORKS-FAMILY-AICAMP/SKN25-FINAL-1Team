import { ShieldCheck } from "lucide-react";
import { safetyPrinciples } from "../data/landing";

export default function SafetySection() {
  return (
    <section id="safety" className="bg-white py-20 sm:py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="grid gap-10 rounded-[28px] border border-slate-200 bg-slate-50 p-6 sm:p-10 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="break-keep">
            <div className="inline-flex h-12 w-12 items-center justify-center rounded-lg bg-blue-600 text-white">
              <ShieldCheck className="h-6 w-6" />
            </div>
            <h2 className="mt-6 text-4xl font-black leading-tight text-slate-950">
              AI는 판단하지 않고, 수의사가 최종 결정합니다.
            </h2>
            <p className="mt-5 text-base font-semibold leading-8 text-slate-600">
              MediPaw의 AI는 보호자 표현을 구조화하고 위험 신호를 표시하며 차트 초안을 준비합니다. 진단, 처방, 최종 응급 판단은 시스템이 아니라 의료진의 검토 안에서 이뤄집니다.
            </p>
          </div>

          <div className="grid gap-4">
            {safetyPrinciples.map(([title, text]) => (
              <div key={title} className="rounded-2xl border border-slate-200 bg-white p-5">
                <p className="text-lg font-black text-blue-700">{title}</p>
                <p className="mt-2 break-keep text-sm font-semibold leading-6 text-slate-600">{text}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
