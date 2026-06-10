import { CheckCircle2 } from "lucide-react";
import SectionHeading from "../components/common/SectionHeading";
import { moduleCards } from "../data/landing";

export default function ServiceSection() {
  return (
    <section id="service" className="bg-slate-50 py-20 sm:py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <SectionHeading
          eyebrow="Service Modules"
          title={
            <>
              보호자 경험과 병원 업무를
              <br className="hidden sm:block" /> 하나의 흐름으로 연결합니다.
            </>
          }
          description={
            <>
              MediPaw는 거창한 병원 CRM을 표방하지 않습니다.
              <br className="hidden lg:block" /> 진료 전후에 꼭 필요한 정보 수집, 예약, 차트 초안, 검토 흐름에 집중합니다.
            </>
          }
        />

        <div className="mt-12 grid gap-5 lg:grid-cols-3">
          {moduleCards.map((card) => (
            <article key={card.eyebrow} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-blue-50 text-blue-700">
                <card.Icon className="h-6 w-6" />
              </div>
              <p className="mt-6 text-xs font-black uppercase tracking-[0.14em] text-blue-700">{card.eyebrow}</p>
              <h3 className="mt-3 break-keep text-2xl font-black leading-tight text-slate-950">{card.title}</h3>
              <div className="mt-6 space-y-3">
                {card.items.map((item) => (
                  <div key={item} className="flex items-center gap-3 break-keep text-sm font-bold text-slate-600">
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-blue-700" />
                    {item}
                  </div>
                ))}
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
