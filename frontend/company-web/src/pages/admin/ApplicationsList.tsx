import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { listApplications } from "../../onboarding/store";
import type { ApplicationStatus } from "../../onboarding/types";
import StatusBadge from "./StatusBadge";

const FILTERS: (ApplicationStatus | "전체")[] = [
  "전체",
  "접수",
  "검토중",
  "승인발행",
  "반려",
];

export default function ApplicationsList() {
  const [filter, setFilter] = useState<ApplicationStatus | "전체">("전체");
  const all = useMemo(() => listApplications(), []);
  const rows = filter === "전체" ? all : all.filter((a) => a.status === filter);

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <h1 className="text-2xl font-black text-slate-900">입점 신청</h1>
      <p className="mt-1 text-sm font-semibold text-slate-500">
        병원이 제출한 신청을 검토하고 보호자 페이지로 발행합니다.
      </p>

      <div className="mt-5 flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setFilter(f)}
            className={[
              "rounded-full px-3.5 py-1.5 text-sm font-bold transition",
              filter === f
                ? "bg-blue-600 text-white"
                : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50",
            ].join(" ")}
          >
            {f}
          </button>
        ))}
      </div>

      {rows.length === 0 ? (
        <div className="mt-6 rounded-2xl border border-slate-200 bg-white py-16 text-center text-sm font-semibold text-slate-400 shadow-sm">
          {all.length === 0
            ? "아직 접수된 신청이 없습니다. (/apply 에서 신청하면 여기에 표시됩니다)"
            : "해당 상태의 신청이 없습니다."}
        </div>
      ) : (
        <div className="mt-6 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-100 bg-slate-50 text-xs font-black uppercase tracking-wide text-slate-400">
              <tr>
                <th className="px-5 py-3">병원명</th>
                <th className="px-5 py-3">원장</th>
                <th className="px-5 py-3">신청일</th>
                <th className="px-5 py-3">상태</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((app) => (
                <tr key={app.id} className="transition hover:bg-slate-50">
                  <td className="px-5 py-4 font-extrabold text-slate-900">{app.hospitalName}</td>
                  <td className="px-5 py-4 font-semibold text-slate-500">
                    {app.doctors.map((d) => d.name).filter(Boolean).join(", ") || "-"}
                  </td>
                  <td className="px-5 py-4 font-semibold text-slate-500">
                    {new Date(app.createdAt).toLocaleDateString("ko-KR")}
                  </td>
                  <td className="px-5 py-4">
                    <StatusBadge status={app.status} />
                  </td>
                  <td className="px-5 py-4 text-right">
                    <Link
                      to={`/admin/applications/${app.id}`}
                      className="text-sm font-bold text-blue-600 hover:text-blue-700"
                    >
                      검토 →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
