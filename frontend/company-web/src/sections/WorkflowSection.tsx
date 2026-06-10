import { ChevronRight } from "lucide-react";
import SectionHeading from "../components/common/SectionHeading";
import { workflowSteps } from "../data/landing";

export default function WorkflowSection() {
  return (
    <section id="workflow" className="bg-white py-20 sm:py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <SectionHeading
          eyebrow="Workflow"
          title={
            <>
              문진이 사라지지 않고,
              <br className="hidden sm:block" /> 진료 기록으로 이어집니다.
            </>
          }
          description="보호자가 남긴 정보가 병원 대시보드와 EMR 초안까지 연결되도록 설계했습니다."
        />

        <div className="mt-12 grid gap-4 lg:grid-cols-4">
          {workflowSteps.map((step, index) => (
            <article key={step.title} className="relative rounded-2xl border border-slate-200 bg-slate-50 p-6">
              <div className="flex items-center justify-between">
                <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-white text-blue-700 shadow-sm">
                  <step.Icon className="h-6 w-6" />
                </div>
                <span className="text-sm font-black text-slate-300">0{index + 1}</span>
              </div>
              <h3 className="mt-7 break-keep text-xl font-black text-slate-950">{step.title}</h3>
              <p className="mt-3 break-keep text-sm font-semibold leading-6 text-slate-600">{step.text}</p>
              {index < workflowSteps.length - 1 && (
                <ChevronRight className="absolute -right-4 top-1/2 hidden h-7 w-7 -translate-y-1/2 rounded-full bg-blue-600 p-1 text-white lg:block" />
              )}
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
