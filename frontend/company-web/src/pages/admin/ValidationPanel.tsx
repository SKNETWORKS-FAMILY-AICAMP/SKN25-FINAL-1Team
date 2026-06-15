import { useEffect, useMemo, useState } from "react";

import {
  MOCK_VALIDATION,
  type CheckStatus,
  type ValidationRecord,
} from "./monitoring-mock";
import { getValidationResults } from "../../onboarding/api";

const CHECK_ITEMS = ["데이터 완전성", "문진-차트 일치도", "예약 안전성", "응급신호 정합성"];

const checkStyle: Record<CheckStatus, string> = {
  PASS: "bg-green-50 text-green-700",
  WARN: "bg-rose-50 text-rose-600",
  SKIPPED: "bg-slate-100 text-slate-400",
};

function StatCard({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-xs font-bold text-slate-400">{label}</p>
      <p className={`mt-1 text-2xl font-black ${tone ?? "text-slate-900"}`}>{value}</p>
    </div>
  );
}

function statusOf(rec: ValidationRecord, item: string): CheckStatus {
  return rec.checks.find((c) => c.item === item)?.status ?? "SKIPPED";
}

export default function ValidationPanel() {
  const [attentionOnly, setAttentionOnly] = useState(false);
  const [records, setRecords] = useState<ValidationRecord[]>(MOCK_VALIDATION);
  const [usingDemo, setUsingDemo] = useState(true);
  const [loading, setLoading] = useState(false);
  const all = records;
  const rows = attentionOnly ? all.filter((r) => r.overall === "ATTENTION") : all;

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    getValidationResults(false)
      .then((list) => {
        if (!mounted) return;
        if (list.length > 0) {
          setRecords(list);
          setUsingDemo(false);
        } else {
          setRecords(MOCK_VALIDATION);
          setUsingDemo(true);
        }
      })
      .catch(() => {
        if (!mounted) return;
        setRecords(MOCK_VALIDATION);
        setUsingDemo(true);
      })
      .finally(() => mounted && setLoading(false));
    return () => {
      mounted = false;
    };
  }, []);

  const stats = useMemo(() => {
    const attention = all.filter((r) => r.overall === "ATTENTION").length;
    const avgCompleteness =
      all.reduce((s, r) => s + r.completeness, 0) / (all.length || 1);
    return {
      total: all.length,
      attention,
      rate: all.length ? Math.round((attention / all.length) * 100) : 0,
      avgCompleteness: avgCompleteness.toFixed(1),
    };
  }, [all]);

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <h1 className="text-2xl font-black text-slate-900">Validation 모니터링</h1>
      <p className="mt-1 text-sm font-semibold text-slate-500">
        AI 산출물의 결정론적 4종 점검 (완전성·문진차트일치·예약안전·응급정합성). 판정이 아니라 검토 신호입니다.
      </p>
      <p className="mt-2 inline-block rounded-full bg-amber-50 px-3 py-1 text-xs font-bold text-amber-700">
        {usingDemo ? "데모 데이터 · validation_resultDB 결과가 없으면 표시" : "실시간 데이터 · validation_resultDB 연동"}
        {loading ? " · 불러오는 중" : ""}
      </p>

      <div className="mt-5 grid gap-4 sm:grid-cols-3">
        <StatCard label="총 검증" value={`${stats.total}건`} />
        <StatCard
          label="ATTENTION"
          value={`${stats.attention}건 (${stats.rate}%)`}
          tone="text-rose-600"
        />
        <StatCard label="평균 완전성 점수" value={`${stats.avgCompleteness} / 10`} />
      </div>

      <label className="mt-5 flex w-fit items-center gap-2 text-sm font-bold text-slate-600">
        <input
          type="checkbox"
          checked={attentionOnly}
          onChange={(e) => setAttentionOnly(e.target.checked)}
        />
        ATTENTION만 보기
      </label>

      <div className="mt-4 overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="border-b border-slate-100 bg-slate-50 text-xs font-black uppercase tracking-wide text-slate-400">
            <tr>
              <th className="px-4 py-3">EMR</th>
              <th className="px-4 py-3">종합</th>
              {CHECK_ITEMS.map((item) => (
                <th key={item} className="px-4 py-3">{item}</th>
              ))}
              <th className="px-4 py-3">요약</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((rec) => (
              <tr key={rec.emrid} className="align-top">
                <td className="px-4 py-3 font-extrabold text-slate-800">#{rec.emrid}</td>
                <td className="px-4 py-3">
                  <span
                    className={`inline-flex rounded-full px-2.5 py-1 text-xs font-black ${
                      rec.overall === "OK" ? "bg-green-50 text-green-700" : "bg-rose-50 text-rose-600"
                    }`}
                  >
                    {rec.overall}
                  </span>
                </td>
                {CHECK_ITEMS.map((item) => {
                  const st = statusOf(rec, item);
                  return (
                    <td key={item} className="px-4 py-3">
                      <span className={`inline-flex rounded-md px-2 py-0.5 text-xs font-bold ${checkStyle[st]}`}>
                        {st}
                      </span>
                    </td>
                  );
                })}
                <td className="px-4 py-3 font-semibold text-slate-500">{rec.summary}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
