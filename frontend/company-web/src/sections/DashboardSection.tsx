import { useState } from "react";
import { ChevronLeft, ChevronRight, ImageIcon } from "lucide-react";
import SectionHeading from "../components/common/SectionHeading";
import { dashboardMetrics, dashboardShots } from "../data/landing";

// assets/screenshots/ 안의 이미지를 파일명 기준으로 자동 수집한다.
// dashboardShots[].file 과 같은 이름의 파일을 넣으면 코드 수정 없이 캐러셀에 뜬다.
const shotUrls = import.meta.glob("../assets/screenshots/*.{png,jpg,jpeg,webp}", {
  eager: true,
  import: "default",
  query: "?url",
}) as Record<string, string>;

function resolveShot(file: string): string | undefined {
  const entry = Object.entries(shotUrls).find(([path]) => path.endsWith(`/${file}`));
  return entry?.[1];
}

export default function DashboardSection() {
  const [active, setActive] = useState(0);
  const total = dashboardShots.length;
  const shot = dashboardShots[active];
  const shotSrc = resolveShot(shot.file);

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
            {/* 화면 캡쳐 캐러셀 — 브라우저 창처럼 띄워 실제 제품 화면을 강조한다. */}
            <div className="relative">
              {/* 뒤쪽 Pine Teal 글로우 */}
              <div
                aria-hidden
                className="pointer-events-none absolute -inset-6 -z-10 rounded-[40px] bg-[radial-gradient(circle_at_50%_35%,rgba(79,147,135,0.5),transparent_70%)] blur-2xl"
              />

              {/* 라이트 브라우저 윈도우 */}
              <div className="overflow-hidden rounded-2xl border border-white/15 bg-white shadow-soft-xl ring-1 ring-black/5">
                {/* 크롬 바 */}
                <div className="flex items-center gap-2 border-b border-slate-200 bg-slate-100 px-4 py-3">
                  <span className="h-3 w-3 rounded-full bg-[#ff5f57]" />
                  <span className="h-3 w-3 rounded-full bg-[#febc2e]" />
                  <span className="h-3 w-3 rounded-full bg-[#28c840]" />
                  <div className="ml-3 hidden flex-1 truncate rounded-md bg-white px-3 py-1 text-center text-[11px] font-bold text-slate-400 sm:block">
                    medipaw · {shot.eyebrow}
                  </div>
                </div>

                {/* 이미지 영역 — 캡쳐 비율(≈1.93:1)에 맞춰 흰 여백 최소화 */}
                <div className="relative aspect-[1.93] w-full bg-white">
                  {shotSrc ? (
                    <img
                      src={shotSrc}
                      alt={`${shot.eyebrow} — ${shot.title} 화면`}
                      className="h-full w-full bg-white object-contain"
                    />
                  ) : (
                    <div className="flex h-full w-full flex-col items-center justify-center gap-3 bg-slate-50 text-slate-400">
                      <ImageIcon className="h-10 w-10 text-slate-300" />
                      <p className="text-sm font-bold text-slate-500">서비스 화면 캡쳐 준비 중</p>
                      <p className="text-xs font-semibold text-slate-400">
                        assets/screenshots/ 에 이미지를 추가하면 노출됩니다
                      </p>
                    </div>
                  )}

                  {/* 좌우 이동 버튼 */}
                  <button
                    type="button"
                    onClick={() => go(-1)}
                    aria-label="이전 화면"
                    className="absolute left-3 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full bg-slate-900/55 text-white shadow-lg backdrop-blur transition hover:bg-slate-900/80"
                  >
                    <ChevronLeft className="h-5 w-5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => go(1)}
                    aria-label="다음 화면"
                    className="absolute right-3 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full bg-slate-900/55 text-white shadow-lg backdrop-blur transition hover:bg-slate-900/80"
                  >
                    <ChevronRight className="h-5 w-5" />
                  </button>
                </div>
              </div>

              {/* 캡션 + 카운터 (어두운 배경 위) */}
              <div className="mt-5 flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-[11px] font-black uppercase tracking-[0.14em] text-blue-300">
                    {shot.eyebrow}
                  </p>
                  <p className="mt-1 truncate text-base font-black text-white">{shot.title}</p>
                  <p className="mt-1 break-keep text-sm font-semibold leading-6 text-slate-400">
                    {shot.caption}
                  </p>
                </div>
                <span className="shrink-0 rounded-full border border-white/10 bg-white/[0.06] px-3 py-1 text-xs font-black text-slate-300">
                  {active + 1} / {total}
                </span>
              </div>

              {/* 점 인디케이터 */}
              <div className="mt-4 flex items-center gap-2">
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
