import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { listHospitals, type AdminHospitalListItem } from "../../onboarding/api";

export default function HospitalsList() {
  const [all, setAll] = useState<AdminHospitalListItem[]>([]);
  const [query, setQuery] = useState("");

  useEffect(() => {
    let mounted = true;
    listHospitals()
      .then((list) => mounted && setAll(list))
      .catch(() => mounted && setAll([]));
    return () => {
      mounted = false;
    };
  }, []);

  const rows = useMemo(() => {
    const q = query.trim();
    if (!q) return all;
    return all.filter((h) => h.name.includes(q) || (h.address || "").includes(q));
  }, [all, query]);

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <h1 className="text-2xl font-black text-slate-900">병원 관리</h1>
      <p className="mt-1 text-sm font-semibold text-slate-500">
        발행된 병원의 소개·원장 프로필·진료시간을 수정합니다. (보호자 화면에 바로 반영)
      </p>

      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="병원 이름 / 주소 검색"
        className="mt-5 h-11 w-full max-w-sm rounded-xl border border-slate-200 bg-white px-4 text-sm font-semibold outline-none transition focus:border-blue-400 focus:ring-4 focus:ring-blue-100"
      />

      {rows.length === 0 ? (
        <div className="mt-6 rounded-2xl border border-slate-200 bg-white py-16 text-center text-sm font-semibold text-slate-400 shadow-sm">
          {all.length === 0 ? "발행된 병원이 없습니다." : "검색 결과가 없습니다."}
        </div>
      ) : (
        <div className="mt-6 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-100 bg-slate-50 text-xs font-black uppercase tracking-wide text-slate-400">
              <tr>
                <th className="px-5 py-3">병원명</th>
                <th className="px-5 py-3">주소</th>
                <th className="px-5 py-3">원장 수</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((h) => (
                <tr key={h.hospitalid} className="transition hover:bg-slate-50">
                  <td className="px-5 py-4 font-extrabold text-slate-900">{h.name}</td>
                  <td className="px-5 py-4 font-semibold text-slate-500">{h.address || "-"}</td>
                  <td className="px-5 py-4 font-semibold text-slate-500">{h.doctorCount}명</td>
                  <td className="px-5 py-4 text-right">
                    <Link
                      to={`/admin/hospitals/${h.hospitalid}`}
                      className="text-sm font-bold text-blue-600 hover:text-blue-700"
                    >
                      관리 →
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
