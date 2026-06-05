import React from "react";
import { CalendarDays, FileText, PawPrint } from "lucide-react";
import logo from "../../../../shared/assets/logo/medipaw-symbol.png";

export function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="bg-slate-50 text-slate-900">
      <div className="mx-auto grid min-h-screen max-w-[1200px] grid-cols-1 px-6 py-10 lg:grid-cols-2 lg:items-start lg:gap-16 lg:py-[88px]">
        <section className="flex flex-col justify-start">
          <div className="mb-6">
            <img src={logo} alt="MediPaw" className="w-[300px]" />
            <p className="mt-3 pl-2 text-lg font-bold tracking-[0.1em] text-slate-500">
              동물병원 의료 보조 시스템
            </p>
          </div>

          <h1 className="mb-6 text-3xl font-bold leading-tight text-slate-900">
            AI 기반 스마트 병원 운영의 시작
            <br />
            MediPaw가 함께합니다.
          </h1>

          <div className="space-y-4">
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
    <div className="flex gap-4">
      <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
        {icon}
      </div>
      <div>
        <h3 className="mb-1 text-base font-bold text-slate-900">{title}</h3>
        <p className="max-w-lg text-sm font-semibold leading-6 text-slate-500">
          {description}
        </p>
      </div>
    </div>
  );
}
