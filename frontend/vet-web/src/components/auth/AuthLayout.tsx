import React from "react";
import { CalendarDays, FileText, PawPrint } from "lucide-react";
import logo from "../../../../shared/assets/logo/medipaw-symbol.png";

export function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="bg-slate-50 text-slate-900">
      <div className="mx-auto grid min-h-screen max-w-[1200px] grid-cols-1 px-6 py-8 lg:grid-cols-2 lg:items-start lg:gap-16 lg:pb-10 lg:pt-20">
        <section className="flex flex-col">
          <div className="mb-6">
            <img src={logo} alt="MediPaw" className="w-[300px]" />
          </div>

          <h1 className="mb-4 text-3xl font-bold leading-tight text-slate-900">
            AI 기반 스마트 병원 운영의 시작
            <br />
            MediPaw가 함께합니다.
          </h1>

          <div className="mt-6 flex flex-1 flex-col justify-between gap-3">
            <FeatureItem
              icon={<PawPrint size={24} />}
              title="AI 사전 문진 & 응급 분류"
              description="보호자 사전 문진 데이터를 기반으로 AI가 응급도를 분류하여 진료를 지원합니다."
            />
            <FeatureItem
              icon={<CalendarDays size={24} />}
              title="예약 & 스케줄 관리"
              description="예약 현황을 한눈에 확인하고 효율적인 진료 스케줄을 관리합니다."
            />
            <FeatureItem
              icon={<FileText size={24} />}
              title="EMR 연동 & 환자 관리"
              description="진료 기록과 환자 정보를 통합 관리하여 업무 효율을 높여드립니다."
            />
          </div>
        </section>

        <section className="flex flex-col justify-start">
          {children}
        </section>
      </div>
    </main>
  );
}

interface FeatureItemProps {
  icon: React.ReactNode;
  title: string;
  description: string;
}

function FeatureItem({ icon, title, description }: FeatureItemProps) {
  return (
    <div className="flex items-center gap-4 rounded-2xl border border-blue-100 bg-white/80 p-4">
      <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-[#2a8587] text-white">
        {icon}
      </span>
      <div>
        <h3 className="text-base font-bold text-slate-900">{title}</h3>
        <p className="mt-1 text-[13px] leading-snug text-slate-600">{description}</p>
      </div>
    </div>
  );
}
