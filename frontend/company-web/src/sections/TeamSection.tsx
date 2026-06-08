import { UsersRound } from "lucide-react";
import SectionHeading from "../components/common/SectionHeading";
import { teamMembers } from "../data/team";

const roleClassMap: Record<string, string> = {
  Frontend: "bg-sky-50 text-sky-700 border-sky-100",
  "Backend / DB": "bg-amber-50 text-amber-700 border-amber-100",
  "AI Agent": "bg-slate-100 text-slate-700 border-slate-200",
};

export default function TeamSection() {
  return (
    <section id="team" className="bg-slate-50 py-20 sm:py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <SectionHeading
            eyebrow="Team"
            title="MediPaw를 함께 만든 팀원들입니다."
            description="보호자 경험, 병원 업무 화면, API와 데이터베이스, Multi-Agent 구조까지 하나의 서비스 흐름으로 연결했습니다."
          />
          <div className="flex w-fit items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-4 py-2 text-sm font-extrabold text-blue-700">
            <UsersRound className="h-4 w-4" />
            SKN25 Final 1Team
          </div>
        </div>

        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {teamMembers.map((member) => (
            <article key={member.name} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-blue-50 text-lg font-black text-blue-700">
                {member.name.slice(0, 1)}
              </div>
              <h3 className="mt-5 text-xl font-black text-slate-950">{member.name}</h3>
              <span className={`mt-3 inline-flex rounded-full border px-3 py-1 text-xs font-black ${roleClassMap[member.role] ?? "bg-slate-100 text-slate-700 border-slate-200"}`}>
                {member.role}
              </span>
              <p className="mt-4 break-keep text-sm font-semibold leading-6 text-slate-600">{member.responsibility}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
