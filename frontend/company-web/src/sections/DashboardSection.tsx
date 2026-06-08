import SectionHeading from "../components/common/SectionHeading";
import { dashboardMetrics } from "../data/landing";

export default function DashboardSection() {
  return (
    <section className="bg-slate-950 py-20 text-white sm:py-24">
      <div className="mx-auto grid max-w-7xl gap-12 px-4 sm:px-6 lg:grid-cols-[0.9fr_1.1fr] lg:px-8">
        <SectionHeading
          eyebrow="Dashboard Style"
          title="기존 대시보드의 톤을 살린 전문적인 제품 화면."
          description="하얀 업무 패널, 얇은 경계선, Pine Teal 포인트를 유지해 보호자 웹과 수의사 웹 사이의 브랜드 일관성을 이어갑니다."
          inverse
        />

        <div className="grid gap-4 sm:grid-cols-2">
          {dashboardMetrics.map((item) => (
            <div key={item.label} className="rounded-2xl border border-white/10 bg-white/[0.06] p-5">
              <item.Icon className="h-6 w-6 text-blue-200" />
              <p className="mt-6 text-sm font-bold text-slate-300">{item.label}</p>
              <p className="mt-2 text-4xl font-black text-white">{item.value}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
