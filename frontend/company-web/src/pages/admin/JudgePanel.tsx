import { useEffect, useMemo, useState } from "react";

import { MOCK_JUDGE, type JudgeRecord } from "./monitoring-mock";
import { getJudgeResults } from "../../onboarding/api";

/* ── 점수 축 레이블 ── */
const SCORE_KEYS: { key: keyof JudgeRecord["scores"]; label: string }[] = [
  { key: "completeness", label: "완전성" },
  { key: "question_efficiency", label: "질문 효율" },
  { key: "response_consistency", label: "응답 일관성" },
  { key: "structuring_quality", label: "구조화 품질" },
];

/* ── 공통 StatCard (ValidationPanel과 동일 스타일) ── */
function StatCard({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-xs font-bold text-slate-400">{label}</p>
      <p className={`mt-1 text-2xl font-black ${tone ?? "text-slate-900"}`}>{value}</p>
    </div>
  );
}

/* ── 인라인 스코어 바 (0~10) ── */
function ScoreBar({ value }: { value: number }) {
  const pct = Math.min(value * 10, 100);
  const color =
    value >= 8 ? "bg-emerald-500" : value >= 6 ? "bg-amber-400" : "bg-rose-500";
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-20 overflow-hidden rounded-full bg-slate-100">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-extrabold text-slate-700">{value.toFixed(1)}</span>
    </div>
  );
}

/* ── 평균 계산 헬퍼 ── */
function avgScore(records: JudgeRecord[], key: keyof JudgeRecord["scores"]): number {
  if (records.length === 0) return 0;
  return records.reduce((s, r) => s + r.scores[key], 0) / records.length;
}

export default function JudgePanel() {
  const [reviewOnly, setReviewOnly] = useState(false);
  const [records, setRecords] = useState<JudgeRecord[]>(MOCK_JUDGE);
  const [usingDemo, setUsingDemo] = useState(true);
  const [loading, setLoading] = useState(false);
  const all = records;
  const rows = reviewOnly ? all.filter((r) => r.verdict === "NEEDS_REVIEW") : all;

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    getJudgeResults(false)
      .then((list) => {
        if (!mounted) return;
        if (list.length > 0) {
          setRecords(list);
          setUsingDemo(false);
        } else {
          setRecords(MOCK_JUDGE);
          setUsingDemo(true);
        }
      })
      .catch(() => {
        if (!mounted) return;
        setRecords(MOCK_JUDGE);
        setUsingDemo(true);
      })
      .finally(() => mounted && setLoading(false));
    return () => {
      mounted = false;
    };
  }, []);

  const stats = useMemo(() => {
    const needsReview = all.filter((r) => r.verdict === "NEEDS_REVIEW").length;
    const avgTurns =
      all.reduce((s, r) => s + r.turnCount, 0) / (all.length || 1);

    return {
      total: all.length,
      needsReview,
      rate: all.length ? Math.round((needsReview / all.length) * 100) : 0,
      avgTurns: avgTurns.toFixed(1),
      avgCompleteness: avgScore(all, "completeness").toFixed(1),
      avgEfficiency: avgScore(all, "question_efficiency").toFixed(1),
      avgConsistency: avgScore(all, "response_consistency").toFixed(1),
      avgStructuring: avgScore(all, "structuring_quality").toFixed(1),
    };
  }, [all]);

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <h1 className="text-2xl font-black text-slate-900">Judge 모니터링</h1>
      <p className="mt-1 text-sm font-semibold text-slate-500">
        LLM 운영 품질 모니터링 — 4축 점수(완전성·질문효율·응답일관성·구조화품질). 문제 세션을 조기 감지합니다.
      </p>
      <p className="mt-2 inline-block rounded-full bg-violet-50 px-3 py-1 text-xs font-bold text-violet-700">
        {usingDemo ? "데모 데이터 · judge 결과가 없으면 표시" : "실시간 데이터 · judge 결과 연동"}
        {loading ? " · 불러오는 중" : ""}
      </p>

      {/* ── 통계 카드 ── */}
      <div className="mt-5 grid gap-4 sm:grid-cols-4">
        <StatCard label="총 심사" value={`${stats.total}건`} />
        <StatCard
          label="NEEDS_REVIEW"
          value={`${stats.needsReview}건 (${stats.rate}%)`}
          tone="text-rose-600"
        />
        <StatCard label="평균 턴 수" value={`${stats.avgTurns} turns`} />
        <StatCard label="평균 완전성" value={`${stats.avgCompleteness} / 10`} />
      </div>

      {/* ── 4축 평균 미니 카드 ── */}
      <div className="mt-4 grid gap-3 sm:grid-cols-4">
        {SCORE_KEYS.map(({ key, label }) => {
          const avg = avgScore(all, key);
          return (
            <div
              key={key}
              className="flex items-center justify-between rounded-xl border border-slate-100 bg-white px-4 py-3"
            >
              <span className="text-xs font-bold text-slate-500">{label}</span>
              <ScoreBar value={avg} />
            </div>
          );
        })}
      </div>

      {/* ── 필터 ── */}
      <label className="mt-5 flex w-fit items-center gap-2 text-sm font-bold text-slate-600">
        <input
          type="checkbox"
          checked={reviewOnly}
          onChange={(e) => setReviewOnly(e.target.checked)}
        />
        NEEDS_REVIEW만 보기
      </label>

      {/* ── 테이블 ── */}
      <div className="mt-4 overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full min-w-[860px] text-left text-sm">
          <thead className="border-b border-slate-100 bg-slate-50 text-xs font-black uppercase tracking-wide text-slate-400">
            <tr>
              <th className="px-4 py-3">EMR</th>
              <th className="px-4 py-3">판정</th>
              {SCORE_KEYS.map(({ key, label }) => (
                <th key={key} className="px-4 py-3">{label}</th>
              ))}
              <th className="px-4 py-3">턴</th>
              <th className="px-4 py-3">비고</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((rec) => (
              <tr key={rec.emrid} className="align-top">
                <td className="px-4 py-3 font-extrabold text-slate-800">
                  #{rec.emrid}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`inline-flex rounded-full px-2.5 py-1 text-xs font-black ${
                      rec.verdict === "HEALTHY"
                        ? "bg-green-50 text-green-700"
                        : "bg-rose-50 text-rose-600"
                    }`}
                  >
                    {rec.verdict === "HEALTHY" ? "HEALTHY" : "REVIEW"}
                  </span>
                </td>
                {SCORE_KEYS.map(({ key }) => (
                  <td key={key} className="px-4 py-3">
                    <ScoreBar value={rec.scores[key]} />
                  </td>
                ))}
                <td className="px-4 py-3 text-center font-extrabold text-slate-700">
                  {rec.turnCount}
                </td>
                <td className="max-w-[220px] px-4 py-3 font-semibold text-slate-500">
                  {rec.notes}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
