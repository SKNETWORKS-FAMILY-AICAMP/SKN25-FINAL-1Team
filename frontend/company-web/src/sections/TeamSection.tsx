import { Check, Github } from "lucide-react";
import SectionHeading from "../components/common/SectionHeading";
import { siteConfig } from "../config/site";
import { teamMembers } from "../data/team";

const roleClassMap: Record<string, string> = {
  Frontend: "bg-sky-50 text-sky-700 border-sky-100",
  "Backend · AI": "bg-amber-50 text-amber-700 border-amber-100",
  "AI · DevOps": "bg-slate-100 text-slate-700 border-slate-200",
};

export default function TeamSection() {
  return (
    <section id="team" className="bg-slate-50 py-20 sm:py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <SectionHeading
            eyebrow="Team"
            title={
              <>
                MediPaw를 함께 만든
                <br className="hidden sm:block" /> 팀원들입니다.
              </>
            }
            description="보호자 경험, 병원 업무 화면, API와 데이터베이스, Multi-Agent 구조까지 하나의 서비스 흐름으로 연결했습니다."
          />
          <a
            href={siteConfig.githubUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex w-fit items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-4 py-2 text-sm font-extrabold text-blue-700 transition hover:border-blue-200 hover:bg-blue-100"
          >
            <Github className="h-4 w-4" />
            Paw-o-Paw
          </a>
        </div>

        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {teamMembers.map((member) => (
            <article
              key={member.name}
              className="flex flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-blue-50 text-lg font-black text-blue-700">
                  {member.name.slice(0, 1)}
                </div>
                <div className="min-w-0">
                  <h3 className="text-lg font-black text-slate-950">{member.name}</h3>
                  <span
                    className={`mt-1 inline-flex rounded-full border px-2.5 py-0.5 text-[11px] font-black ${
                      roleClassMap[member.role] ?? "bg-slate-100 text-slate-700 border-slate-200"
                    }`}
                  >
                    {member.role}
                  </span>
                </div>
              </div>

              <ul className="mt-5 space-y-2.5">
                {member.contributions.map((item) => (
                  <li
                    key={item}
                    className="flex items-start gap-2 break-keep text-sm font-semibold leading-6 text-slate-600"
                  >
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-blue-700" />
                    {item}
                  </li>
                ))}
              </ul>

              <a
                href={member.github}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-auto inline-flex items-center justify-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 pt-2 text-xs font-black text-slate-600 transition hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"
              >
                <Github className="h-3.5 w-3.5" />
                GitHub
              </a>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
