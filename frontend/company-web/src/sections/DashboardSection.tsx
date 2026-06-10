import { useState } from "react";
import { ChevronLeft, ChevronRight, ImageIcon } from "lucide-react";
import SectionHeading from "../components/common/SectionHeading";
import { dashboardMetrics, dashboardShots } from "../data/landing";

export default function DashboardSection() {
  const [active, setActive] = useState(0);
  const total = dashboardShots.length;
  const shot = dashboardShots[active];

  const go = (delta: number) => setActive((current) => (current + delta + total) % total);

  return (
    <section id="dashboard" className="bg-slate-950 py-20 text-white sm:py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="grid gap-12 lg:grid-cols-[0.82fr_1.18fr] lg:items-center">
          <SectionHeading
            eyebrow="Dashboard Style"
            title={
              <>
                실제 서비스 화면을
                <br className="hidden sm:block" /> 넘겨보며 확인하세요.
              </>
            }
            description="보호자 문진부터 수의사 대시보드, EMR 초안까지. 하얀 업무 패널과 Pine Teal 포인트로 이어지는 실제 제품 화면을 캐러셀로 살펴보세요."
            inverse
          />

          <div>
            {/* 화면 캡쳐 캐러셀 — shot.src 가 있으면 이미지를, 없으면 준비 중 placeholder 를 보여준다. */}
            <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-white/[0.04] shadow-soft-xl">
              <div className="relative aspect-[16/10] w-full">
                {shot.src ? (
                  <img
                    src={shot.src}
                    alt={`${shot.eyebrow} — ${shot.title} 화면`}
                    className="h-full w-full object-cover object-top"
                  />
                ) : (
                  <div className="flex h-full w-full flex-col items-center justify-center gap-3 bg-[radial-gradient(circle_at_30%_20%,rgba(79,147,135,0.18),transparent_60%)] text-slate-400">
                    <ImageIcon className="h-10 w-10 text-slate-500" />
                    <p className="text-sm font-bold text-slate-300">서비스 화면 캡쳐 준비 중</p>
                    <p className="text-xs font-semibold text-slate-500">
                      assets/screenshots/ 에 이미지를 추가하면 노출됩니다
                    </p>
                  </div>
                )}

                {/* 좌우 이동 버튼 */}
                <button
                  type="button"
                  onClick={() => go(-1)}
                  aria-label="이전 화면"
                  className="absolute left-3 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full border border-white/20 bg-slate-950/60 text-white backdrop-blur transition hover:bg-slate-950/90"
                >
                  <ChevronLeft className="h-5 w-5" />
                </button>
                <button
                  type="button"
                  onClick={() => go(1)}
                  aria-label="다음 화면"
                  className="absolute right-3 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full border border-white/20 bg-slate-950/60 text-white backdrop-blur transition hover:bg-slate-950/90"
                >
                  <ChevronRight className="h-5 w-5" />
                </button>
              </div>

              {/* 캡션 바 */}
              <div className="flex items-center justify-between gap-4 border-t border-white/10 bg-white/[0.03] px-5 py-4">
                <div className="min-w-0">
                  <p className="text-[11px] font-black uppercase tracking-[0.14em] text-blue-300">
                    {shot.eyebrow}
                  </p>
                  <p className="mt-1 truncate text-sm font-black text-white">{shot.title}</p>
                  <p className="mt-1 break-keep text-xs font-semibold leading-5 text-slate-400">
                    {shot.caption}
                  </p>
                </div>
                <span className="shrink-0 rounded-full border border-white/10 bg-white/[0.06] px-3 py-1 text-xs font-black text-slate-300">
                  {active + 1} / {total}
                </span>
              </div>
            </div>

            {/* 점 인디케이터 */}
            <div className="mt-4 flex items-center justify-center gap-2">
              {dashboardShots.map((item, index) => (
                <button
                  key={item.title}
                  type="button"
                  onClick={() => setActive(index)}
                  aria-label={`${index + 1}번째 화면으로 이동`}
                  className={`h-2 rounded-full transition-all ${
                    index === active ? "w-6 bg-blue-400" : "w-2 bg-white/20 hover:bg-white/40"
                  }`}
                />
              ))}
            </div>
          </div>
        </div>

        {/* 핵심 지표 스트립 */}
        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
