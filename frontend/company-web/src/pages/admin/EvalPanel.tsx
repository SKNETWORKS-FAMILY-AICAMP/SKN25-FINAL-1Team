import { useEffect, useState } from "react";
import { FlaskConical, Loader2, RefreshCw, Construction } from "lucide-react";
import { getAdminToken } from "../../onboarding/api";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
  LineChart, Line, CartesianGrid,
} from "recharts";

const API = (import.meta.env.VITE_API_BASE_URL as string) || "/api";

// ── Types ─────────────────────────────────────────────────────
type CheckStatus = "PASS" | "WARN" | "SKIPPED";
type OverallStatus = "OK" | "ATTENTION" | "SKIPPED";

interface AgentCheck {
  item: string;
  status: CheckStatus;
  detail: string;
}
interface CategoryStat {
  kw_hit: number;
  total: number;
}
interface MissedSample {
  message: string;
  category: string;
}
interface LowConfidenceCase {
  message: string;
  confidence: number;
  predicted: boolean;
  expected: boolean;
  correct: boolean;
}
interface AgentMetrics {
  keyword_recall?: number | null;
  keyword_precision?: number | null;
  llm_recall?: number | null;
  llm_precision?: number | null;
  urgent_recall?: string;
  total_cases?: number;
  category_stats?: Record<string, CategoryStat>;
  missed_samples?: MissedSample[];
  avg_confidence?: number | null;
  low_confidence_cases?: LowConfidenceCase[];
  [key: string]: unknown;
}
interface AgentEvalResult {
  agent: string;
  overall: CheckStatus;
  checks: AgentCheck[];
  metrics: AgentMetrics;
  ran_at?: string;
}
interface MonitoringLog {
  ts: string;
  agent: string;
  emrid?: number | null;
  scheduleid?: number | null;
  message?: string;
  category?: string;
  severity?: string;
  is_saved?: boolean;
  has_media?: boolean;
  [key: string]: unknown;
}
interface ModuleResult {
  status: CheckStatus;
  checks: AgentCheck[];
}
interface ValidationChecks {
  triage?: ModuleResult;
  schedule?: ModuleResult;
  chart?: ModuleResult;
}
interface ConversationStatus {
  item: string;
  status: CheckStatus;
  detail: string;
  scores?: Record<string, number>;
}
interface ValidationRow {
  emrid: number;
  createdAt: string | null;
  overall: OverallStatus;
  completeness: number | null;
  checks: ValidationChecks | AgentCheck[];
  summary: string;
  conversation_status?: ConversationStatus | null;
}

// ── Helpers ───────────────────────────────────────────────────
function authHeader() {
  return { Authorization: `Bearer ${getAdminToken()}` };
}

function pct(v: number | null | undefined) {
  if (v == null) return "—";
  return `${Math.round(v * 100)}%`;
}

function fmtTime(iso: string | null | undefined) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("ko-KR", {
    month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

// 상태 텍스트 — 색은 최소화 (WARN만 amber, 나머지 slate)
function StatusText({ status }: { status: CheckStatus | OverallStatus }) {
  const cls =
    status === "WARN" || status === "ATTENTION"
      ? "text-amber-600 font-bold"
      : status === "PASS" || status === "OK"
      ? "text-slate-800 font-bold"
      : "text-slate-600 font-medium";
  return <span className={cls}>{status}</span>;
}

// ── 준비 중 ────────────────────────────────────────────────────
function ComingSoon({ label, desc }: { label: string; desc: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-slate-200 py-12 text-center">
      <Construction className="h-7 w-7 text-slate-600" />
      <p className="text-sm font-semibold text-slate-600">{label}</p>
      <p className="max-w-xs text-xs text-slate-600">{desc}</p>
    </div>
  );
}

// ── 리포트 공통 헤더 ─────────────────────────────────────────
function ReportHeader({ result }: { result: AgentEvalResult }) {
  const m = result.metrics;
  return (
    <div className="flex items-baseline justify-between border-b border-slate-100 pb-3">
      <span className="font-sans text-base font-bold text-slate-800">
        {result.agent} 벤치마크 결과
        {m.total_cases != null && (
          <span className="ml-2 text-sm font-normal text-slate-600">(케이스: {m.total_cases}개)</span>
        )}
      </span>
      <span className="text-xs text-slate-600">{result.ran_at ?? new Date().toLocaleString("ko-KR")}</span>
    </div>
  );
}

// ── followup_filter 전용 리포트 ───────────────────────────────
function FollowupBenchmarkReport({ result }: { result: AgentEvalResult }) {
  const m = result.metrics;
  const kwRecall = m.keyword_recall as number | null;
  const kwPrec   = m.keyword_precision as number | null;
  const llmRecall = m.llm_recall as number | null;
  const llmPrec   = m.llm_precision as number | null;
  const urgentRaw = m.urgent_recall as string | undefined;

  const kwRecallWarn  = kwRecall  != null && kwRecall  < 0.9;
  const kwPrecWarn    = kwPrec    != null && kwPrec    < 0.8;
  const llmRecallWarn = llmRecall != null && llmRecall < 0.9;
  const llmPrecWarn   = llmPrec   != null && llmPrec   < 0.8;

  let urgentDetected = 0, urgentTotal = 0;
  if (urgentRaw && urgentRaw !== "N/A") {
    const parts = urgentRaw.split("/");
    urgentDetected = parseInt(parts[0]);
    urgentTotal    = parseInt(parts[1]);
  }
  const urgentWarn = urgentTotal > 0 && urgentDetected < urgentTotal;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-800">
      <ReportHeader result={result} />

      {/* 분류 정확도 비교표 */}
      <div className="mt-10">
        <p className="mb-4 text-xs font-semibold uppercase tracking-wide text-slate-600">분류 정확도</p>
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-100 text-slate-600">
              <th className="pb-2 text-left font-medium w-40"></th>
              <th className="pb-2 text-center font-medium">Recall</th>
              <th className="pb-2 text-center font-medium">Precision</th>
              <th className="pb-2 text-center font-medium">판정</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-slate-50">
              <td className="py-3 font-semibold text-slate-800">Keyword (fallback)</td>
              <td className={`py-3 text-center text-base font-bold ${kwRecallWarn ? "text-amber-600" : "text-slate-800"}`}>
                {pct(kwRecall)}
              </td>
              <td className={`py-3 text-center text-base font-bold ${kwPrecWarn ? "text-amber-600" : "text-slate-800"}`}>
                {pct(kwPrec)}
              </td>
              <td className="py-3 text-center">
                <StatusText status={kwRecallWarn || kwPrecWarn ? "WARN" : "PASS"} />
              </td>
            </tr>
            <tr>
              <td className="py-3 font-semibold text-slate-800">LLM (classify)</td>
              <td className={`py-3 text-center text-base font-bold ${llmRecallWarn ? "text-amber-600" : "text-slate-800"}`}>
                {pct(llmRecall)}
              </td>
              <td className={`py-3 text-center text-base font-bold ${llmPrecWarn ? "text-amber-600" : "text-slate-800"}`}>
                {pct(llmPrec)}
              </td>
              <td className="py-3 text-center">
                <StatusText status={llmRecallWarn || llmPrecWarn ? "WARN" : "PASS"} />
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* 악화 신호 감지 */}
      {urgentTotal > 0 && (
        <div className="mt-10 flex items-center gap-4 border-t border-slate-100 pt-6">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-600">
            악화 신호 감지 <span className="normal-case font-normal text-slate-600">(urgent, 100% 필수)</span>
          </span>
          <span className={`text-base font-bold ${urgentWarn ? "text-amber-600" : "text-slate-800"}`}>
            {urgentDetected} / {urgentTotal}
          </span>
          <StatusText status={urgentWarn ? "WARN" : "PASS"} />
        </div>
      )}

      {/* LLM 판단 확신도 */}
      {m.avg_confidence != null && (
        <div className="mt-10 border-t border-slate-100 pt-6">
          <p className="mb-4 text-xs font-semibold uppercase tracking-wide text-slate-600">LLM 판단 확신도</p>
          <div className="flex items-center gap-6">
            <div>
              <p className="text-xs text-slate-600">평균 confidence</p>
              <p className={`mt-1 text-2xl font-black ${m.avg_confidence < 0.7 ? "text-amber-600" : "text-slate-800"}`}>
                {Math.round(m.avg_confidence * 100)}%
              </p>
            </div>
            {m.low_confidence_cases && m.low_confidence_cases.length > 0 && (
              <div>
                <p className="text-xs text-slate-600">저신뢰 케이스 <span className="text-slate-600">(&lt; 70%)</span></p>
                <p className="mt-1 text-2xl font-black text-amber-600">{m.low_confidence_cases.length}건</p>
              </div>
            )}
          </div>

          {m.low_confidence_cases && m.low_confidence_cases.length > 0 && (
            <table className="mt-4 w-full text-xs">
              <thead>
                <tr className="border-b border-slate-100 text-slate-600">
                  <th className="pb-2 text-left font-medium">메시지</th>
                  <th className="pb-2 text-center font-medium">확신도</th>
                  <th className="pb-2 text-center font-medium">정답</th>
                </tr>
              </thead>
              <tbody>
                {(m.low_confidence_cases as LowConfidenceCase[]).map((c, i) => (
                  <tr key={i} className="border-b border-slate-50">
                    <td className="py-2 text-slate-600 max-w-xs truncate">{c.message}</td>
                    <td className="py-2 text-center font-bold text-amber-600">{Math.round(c.confidence * 100)}%</td>
                    <td className="py-2 text-center">
                      {c.correct
                        ? <span className="font-bold text-slate-800">O</span>
                        : <span className="font-bold text-amber-600">X</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* 카테고리별 Keyword recall */}
      {m.category_stats && Object.keys(m.category_stats).length > 0 && (
        <div className="mt-10 border-t border-slate-100 pt-6">
          <p className="mb-4 text-xs font-semibold uppercase tracking-wide text-slate-600">카테고리별 Keyword recall</p>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-100 text-slate-600">
                <th className="pb-2 text-left font-medium">카테고리</th>
                <th className="pb-2 text-center font-medium">감지</th>
                <th className="pb-2 text-center font-medium">전체</th>
                <th className="pb-2 text-center font-medium">Recall</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(m.category_stats as Record<string, CategoryStat>).map(([cat, stat]) => {
                const r = stat.total > 0 ? stat.kw_hit / stat.total : 0;
                const warn = r < 0.9;
                return (
                  <tr key={cat} className="border-b border-slate-100">
                    <td className="py-2.5 font-semibold text-slate-700">{cat}</td>
                    <td className="py-2.5 text-center text-slate-800 font-semibold">{stat.kw_hit}</td>
                    <td className="py-2.5 text-center text-slate-600">{stat.total}</td>
                    <td className={`py-2.5 text-center font-bold ${warn ? "text-amber-600" : "text-slate-800"}`}>
                      {Math.round(r * 100)}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

    </div>
  );
}

// ── triage 전용 리포트 ────────────────────────────────────────
interface TriageMetrics {
  urgency_accuracy?: number | null;
  urgency_cases?: number;
  urgency_errors?: { name: string; expected: string; got: string }[];
  red_flag_recall?: string;
  slot_f1?: number | null;
  extra_grounded?: number;
  extra_ungrounded?: number;
  slot_precision?: number | null;
  slot_recall?: number | null;
  hallucination_count?: number;
  summary_score?: number | null;
  llm_errors?: number;
  total_cases?: number;
}

function TriageBenchmarkReport({ result }: { result: AgentEvalResult }) {
  const m = result.metrics as TriageMetrics;
  const urgAcc = m.urgency_accuracy;
  const rfRaw  = m.red_flag_recall ?? "N/A";
  let rfOk = rfRaw === "N/A";
  if (!rfOk) {
    const [tp, total] = rfRaw.split("/").map(Number);
    rfOk = tp === total;
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-800">
      <ReportHeader result={result} />

      {/* 응급도 + Red flag */}
      <div className="mt-10">
        <p className="mb-4 text-xs font-semibold uppercase tracking-wide text-slate-600">결정론 체크 (엔진)</p>
        <div className="flex gap-12">
          <div>
            <p className="text-xs text-slate-600">응급도 정확도</p>
            <p className={`mt-1 text-3xl font-black ${urgAcc != null && urgAcc < 0.95 ? "text-amber-600" : "text-slate-800"}`}>
              {urgAcc != null ? `${Math.round(urgAcc * 100)}%` : "—"}
            </p>
            {m.urgency_cases != null && (
              <p className="mt-0.5 text-xs text-slate-600">{m.urgency_cases}개 케이스 · 기준 95%</p>
            )}
          </div>
          <div>
            <p className="text-xs text-slate-600">Red flag 감지율</p>
            <p className={`mt-1 text-3xl font-black ${!rfOk && rfRaw !== "N/A" ? "text-amber-600" : "text-slate-800"}`}>
              {rfRaw}
            </p>
            <p className="mt-0.5 text-xs text-slate-600">100% 필수</p>
          </div>
        </div>
      </div>

      {/* 응급도 오분류 */}
      {m.urgency_errors && m.urgency_errors.length > 0 && (
        <div className="mt-6 border-t border-slate-100 pt-4">
          <p className="mb-3 text-xs font-semibold text-slate-600">응급도 오분류</p>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-100 text-slate-600">
                <th className="pb-2 text-left font-medium">케이스</th>
                <th className="pb-2 text-center font-medium">예상</th>
                <th className="pb-2 text-center font-medium">결과</th>
              </tr>
            </thead>
            <tbody>
              {m.urgency_errors.map((e, i) => (
                <tr key={i} className="border-b border-slate-50">
                  <td className="py-2 text-slate-600 max-w-xs truncate">{e.name}</td>
                  <td className="py-2 text-center font-bold text-slate-700">{e.expected}</td>
                  <td className="py-2 text-center font-bold text-amber-600">{e.got}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* LLM 체크 */}
      <div className="mt-10 border-t border-slate-100 pt-6">
        <p className="mb-4 text-xs font-semibold uppercase tracking-wide text-slate-600">LLM 체크</p>
        <div className="flex gap-12">
          <div>
            <p className="text-xs text-slate-600">슬롯 추출 F1</p>
            <p className={`mt-1 text-3xl font-black ${m.slot_f1 != null && m.slot_f1 < 0.8 ? "text-amber-600" : "text-slate-800"}`}>
              {m.slot_f1 != null ? m.slot_f1.toFixed(2) : "—"}
            </p>
            {m.slot_precision != null && m.slot_recall != null && (
              <p className="mt-0.5 text-xs text-slate-600">P={m.slot_precision.toFixed(2)} R={m.slot_recall.toFixed(2)} · 기준 0.80</p>
            )}
          </div>
          <div>
            <p className="text-xs text-slate-600">환각 의심</p>
            <p className={`mt-1 text-3xl font-black ${(m.extra_ungrounded ?? 0) > 0 ? "text-amber-600" : "text-slate-800"}`}>
              {m.extra_ungrounded ?? 0}건
            </p>
            <p className="mt-0.5 text-xs text-slate-600">발화 근거 없는 추출 · 근거 있음 {m.extra_grounded ?? 0}건</p>
          </div>
          <div>
            <p className="text-xs text-slate-600">요약 완전성</p>
            <p className={`mt-1 text-3xl font-black ${m.summary_score != null && m.summary_score < 0.8 ? "text-amber-600" : "text-slate-800"}`}>
              {m.summary_score != null ? `${Math.round(m.summary_score * 100)}%` : "—"}
            </p>
            <p className="mt-0.5 text-xs text-slate-600">키워드 포함율 · 기준 80%</p>
          </div>
        </div>
        {m.llm_errors != null && m.llm_errors > 0 && (
          <p className="mt-3 text-xs text-amber-500">LLM 오류 {m.llm_errors}건</p>
        )}
      </div>

      {/* 체크 목록 */}
      <div className="mt-10 border-t border-slate-100 pt-6">
        <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-600">체크 목록</p>
        <div className="space-y-3">
          {result.checks.map((c, i) => (
            <div key={c.item}>
              <div className="text-xs text-slate-600">[{i + 1}] {c.item}</div>
              <div className="mt-0.5 pl-4 text-xs">결과: <StatusText status={c.status} /></div>
              <div className="mt-0.5 pl-4 text-xs text-slate-600">{c.detail}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── 벤치마크 리포트 (범용) ────────────────────────────────────
function BenchmarkReport({ result }: { result: AgentEvalResult }) {
  if (result.agent === "followup_filter") {
    return <FollowupBenchmarkReport result={result} />;
  }
  if (result.agent === "triage") {
    return <TriageBenchmarkReport result={result} />;
  }

  const m = result.metrics;
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 font-mono text-sm text-slate-700">
      <ReportHeader result={result} />

      <div className="mt-5 space-y-4">
        {result.checks.map((c, i) => (
          <div key={c.item}>
            <div className="text-xs text-slate-600">[{i + 1}] {c.item}</div>
            <div className="mt-0.5 pl-4 text-xs">결과: <StatusText status={c.status} /></div>
            <div className="mt-0.5 pl-4 text-xs text-slate-600">{c.detail}</div>
          </div>
        ))}
      </div>

      <div className="mt-6 border-t border-slate-200 pt-3 text-xs text-slate-600">
        {[
          m.keyword_recall != null && `keyword_recall ${pct(m.keyword_recall)}`,
          m.keyword_precision != null && `keyword_precision ${pct(m.keyword_precision)}`,
          m.llm_recall != null && `llm_recall ${pct(m.llm_recall)}`,
          m.llm_precision != null && `llm_precision ${pct(m.llm_precision)}`,
          m.urgent_recall && `urgent ${m.urgent_recall}`,
        ]
          .filter(Boolean)
          .join("  |  ")}
      </div>
    </div>
  );
}

// ── 운영 모니터링 테이블 ─────────────────────────────────────
const PAGE_SIZE = 20;

function MonitoringTable({
  logs,
  loading,
  onRefresh,
}: {
  logs: MonitoringLog[];
  loading: boolean;
  onRefresh: () => void;
}) {
  const [page, setPage] = useState(0);
  const totalPages = Math.ceil(logs.length / PAGE_SIZE);
  const pageLogs = logs.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-800">
      <div className="flex items-baseline justify-between border-b border-slate-100 pb-3">
        <span className="font-sans text-base font-bold text-slate-800">
          실시간 운영 로그
          <span className="ml-2 text-sm font-normal text-slate-600">
            ({logs.length}건 / 최대 200건)
          </span>
        </span>
        <button
          onClick={() => { setPage(0); onRefresh(); }}
          disabled={loading}
          className="flex items-center gap-1 rounded border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-40"
        >
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
          새로고침
        </button>
      </div>

      {logs.length === 0 && !loading ? (
        <p className="py-8 text-center text-xs text-slate-600">
          아직 로그가 없습니다. 채팅으로 경과 메시지를 보내면 기록됩니다.
        </p>
      ) : (
        <>
          <div className="mt-5 overflow-hidden rounded-lg border border-slate-100">
            <table className="w-full text-xs">
              <thead className="border-b border-slate-100 bg-slate-50 text-slate-600">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">EMR</th>
                  <th className="px-3 py-2 text-left font-medium">시간</th>
                  <th className="px-3 py-2 text-left font-medium">메시지</th>
                  <th className="px-3 py-2 text-left font-medium">카테고리</th>
                  <th className="px-3 py-2 text-left font-medium">심각도</th>
                  <th className="px-3 py-2 text-left font-medium">저장</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {pageLogs.map((log, i) => (
                  <tr key={i} className="hover:bg-slate-50">
                    <td className="px-3 py-2 font-mono font-bold text-slate-700">
                      {log.emrid != null ? `#${log.emrid}` : "—"}
                    </td>
                    <td className="px-3 py-2 text-slate-600 whitespace-nowrap">
                      {log.ts?.slice(11, 16) ?? "—"}
                    </td>
                    <td className="px-3 py-2 text-slate-600 max-w-[200px] truncate">
                      {log.message ?? "—"}
                    </td>
                    <td className="px-3 py-2 text-slate-600">{log.category ?? "—"}</td>
                    <td className="px-3 py-2">
                      <span className={log.severity === "urgent_possible" ? "text-amber-600 font-bold" : "text-slate-600"}>
                        {log.severity ?? "—"}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      {log.is_saved ? (
                        <span className="font-bold text-slate-700">Y</span>
                      ) : (
                        <span className="text-slate-600">N</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="mt-3 flex items-center justify-between text-xs text-slate-600">
              <span>{page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, logs.length)} / {logs.length}건</span>
              <div className="flex gap-1">
                <button
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="rounded border border-slate-200 px-2 py-1 hover:bg-slate-50 disabled:opacity-30"
                >
                  이전
                </button>
                <span className="px-2 py-1 font-semibold text-slate-600">{page + 1} / {totalPages}</span>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                  disabled={page === totalPages - 1}
                  className="rounded border border-slate-200 px-2 py-1 hover:bg-slate-50 disabled:opacity-30"
                >
                  다음
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── 실운영 케이스 집계 ─────────────────────────────────────────
const LIVE_CHECKS: Record<"triage" | "schedule" | "chart", string[]> = {
  triage:   ["완료 신호", "응급도 정합성", "응급도 판단", "컨텍스트 연속성"],
  schedule: ["예약 타이밍", "근무시간", "빈 슬롯", "핸드오프 수신"],
  chart:    ["SOAP 섹션 완전성", "임상 품질"],
};

function SoapBreakdown({ rows }: { rows: ValidationRow[] }) {
  const PATTERNS = [
    { key: "S(주증상·경과 미흡)",         label: "S", desc: "주증상·경과" },
    { key: "O(신체검사 항목 미언급)",       label: "O", desc: "신체검사" },
    { key: "A(추정·감별 표현 없음)",        label: "A", desc: "감별·추정" },
    { key: "P(다음 단계 계획 없음)",        label: "P", desc: "처치 계획" },
  ];

  const failCounts: Record<string, number> = {};
  let total = 0;

  for (const row of rows) {
    const cd = (!Array.isArray(row.checks) && row.checks && typeof row.checks === "object")
      ? (row.checks as ValidationChecks)
      : {};
    const soap = cd.chart?.checks.find((c) => c.item === "SOAP 섹션 완전성");
    if (!soap || soap.status === "SKIPPED") continue;
    total++;
    for (const p of PATTERNS) {
      if (soap.detail.includes(p.key)) {
        failCounts[p.key] = (failCounts[p.key] ?? 0) + 1;
      }
    }
  }

  if (total === 0) return null;

  return (
    <div className="mt-4 border-t border-slate-100 pt-4">
      <p className="mb-2 text-xs text-slate-600">SOAP 섹션별 미흡 빈도 ({total}건 평가)</p>
      <div className="flex gap-2">
        {PATTERNS.map(({ key, label, desc }) => {
          const n = failCounts[key] ?? 0;
          return (
            <div key={key} className={`flex flex-1 flex-col items-center rounded-lg border px-3 py-2 ${
              n > 0 ? "border-amber-200 bg-amber-50" : "border-slate-100 bg-slate-50"
            }`}>
              <span className="text-sm font-black text-slate-700">{label}</span>
              <span className="text-xs text-slate-600">{desc}</span>
              <span className={`mt-1 text-xs font-semibold ${n > 0 ? "text-amber-600" : "text-slate-600"}`}>
                {n > 0 ? `${n}건 미흡` : "이슈 없음"}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function LiveMetricsSection({
  rows,
  agentKey,
}: {
  rows: ValidationRow[];
  agentKey: "triage" | "schedule" | "chart";
}) {
  const checkItems = LIVE_CHECKS[agentKey];
  const LABEL = { triage: "문진", schedule: "예약", chart: "차트" };

  const stats: Record<string, { pass: number; total: number }> = {};
  checkItems.forEach((item) => { stats[item] = { pass: 0, total: 0 }; });

  for (const row of rows) {
    const cd = (!Array.isArray(row.checks) && row.checks && typeof row.checks === "object")
      ? (row.checks as ValidationChecks)
      : {};
    const mod = cd[agentKey];
    if (!mod) continue;
    for (const c of mod.checks) {
      if (!stats[c.item] || c.status === "SKIPPED") continue;
      stats[c.item].total++;
      if (c.status === "PASS") stats[c.item].pass++;
    }
  }

  const visible = checkItems.filter((item) => stats[item].total > 0);
  if (visible.length === 0) return null;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="mb-4 flex items-baseline justify-between">
        <p className="text-xs font-semibold text-slate-600">
          {LABEL[agentKey]} 에이전트 · 실운영 케이스 집계
        </p>
        <span className="text-xs text-slate-600">{rows.length}건 기준</span>
      </div>

      <div className="space-y-4">
        {visible.map((item, i) => {
          const { pass, total } = stats[item];
          const rate = total > 0 ? pass / total : 0;
          const warn = rate < 0.85;
          return (
            <div key={item}>
              <div className="mb-1.5 flex items-center justify-between">
                <span className="text-xs text-slate-600">
                  <span className="mr-1.5 text-slate-600">[{i + 1}]</span>
                  {item}
                </span>
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-bold ${warn ? "text-amber-600" : "text-slate-700"}`}>
                    {pass}/{total} ({Math.round(rate * 100)}%)
                  </span>
                  <span className={`rounded px-1.5 py-0.5 text-xs font-bold ${
                    warn ? "bg-amber-50 text-amber-600" : "bg-slate-100 text-slate-600"
                  }`}>
                    {warn ? "주의" : "PASS"}
                  </span>
                </div>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
                <div
                  className={`h-full rounded-full ${warn ? "bg-amber-400" : "bg-slate-700"}`}
                  style={{ width: `${rate * 100}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      {agentKey === "chart" && <SoapBreakdown rows={rows} />}
    </div>
  );
}

// ── 에이전트 벤치마크 탭 ─────────────────────────────────────
function AgentBenchmarkTab({
  logsEndpoint,
  recentRow,
  agentKey,
}: {
  logsEndpoint?: string | null;
  recentRow?: ValidationRow | null;
  agentKey?: "triage" | "schedule" | "chart";
}) {
  const [logs, setLogs] = useState<MonitoringLog[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);

  useEffect(() => {
    if (logsEndpoint) fetchLogs();
  }, [logsEndpoint]);

  async function fetchLogs() {
    if (!logsEndpoint) return;
    setLogsLoading(true);
    try {
      const res = await fetch(`${API}${logsEndpoint}`, { headers: authHeader() });
      const json = await res.json();
      setLogs(json.result ?? []);
    } finally {
      setLogsLoading(false);
    }
  }

  return (
    <div className="space-y-8">
      {/* ── 최근 케이스 결과 (triage/schedule/chart 탭만) ── */}
      {recentRow && agentKey && (
        <RecentAgentResult row={recentRow} agentKey={agentKey} />
      )}

      {/* ── 운영 모니터링 (logsEndpoint 있을 때만) ── */}
      {logsEndpoint && (
        <MonitoringTable logs={logs} loading={logsLoading} onRefresh={fetchLogs} />
      )}
    </div>
  );
}

// ── 전체 에이전트 벤치마크 섹션 ──────────────────────────────
interface FullReportModule {
  agent: string;
  overall: CheckStatus;
  checks: AgentCheck[];
  metrics: AgentMetrics;
}
interface FullReport {
  agent: "full_report";
  overall_verdict: "PASS" | "PARTIAL_FAIL" | "CRITICAL_FAIL";
  modules: {
    triage?: FullReportModule;
    mcp_health?: FullReportModule;
    orchestrator?: FullReportModule;
    reception?: FullReportModule;
    followup?: FullReportModule;
    schedule?: FullReportModule;
    chart?: FullReportModule;
  };
  critical_reasons: string[];
}

const MODULE_LABEL: Record<string, string> = {
  triage:       "Triage",
  mcp_health:   "MCP",
  orchestrator: "라우터",
  reception:    "Reception",
  followup:     "경과 필터",
  schedule:     "Schedule",
  chart:        "Chart",
};

function moduleKeyMetric(key: string, mod: FullReportModule): string {
  // AgentMetrics 인덱스 시그니처가 unknown이라 모두 as로 강제 캐스팅
  const m = mod.metrics as Record<string, unknown>;
  if (key === "triage") {
    const urg = m["urgency_accuracy"] != null ? `응급도 ${pct(m["urgency_accuracy"] as number)}` : null;
    const rf  = m["red_flag_recall"]  != null ? `Red flag ${m["red_flag_recall"]}` : null;
    return [urg, rf].filter(Boolean).join(" · ") || "—";
  }
  if (key === "orchestrator") {
    const acc  = m["routing_accuracy"] != null ? `라우팅 ${pct(m["routing_accuracy"] as number)}` : null;
    const leak = m["triage_leak_count"] != null ? `유출 ${m["triage_leak_count"]}건` : null;
    return [acc, leak].filter(Boolean).join(" · ") || "—";
  }
  if (key === "mcp_health") {
    const cnt = m["tool_count"]      != null ? `도구 ${m["tool_count"]}개` : null;
    const ms  = m["avg_latency_ms"]  != null ? `${m["avg_latency_ms"]}ms` : null;
    return [cnt, ms].filter(Boolean).join(" · ") || "—";
  }
  if (key === "reception") {
    return m["tool_accuracy"] != null ? `도구 선택 ${pct(m["tool_accuracy"] as number)}` : "—";
  }
  if (key === "followup") {
    const kw  = m["keyword_recall"] != null ? `KW ${pct(m["keyword_recall"] as number)}` : null;
    const llm = m["llm_recall"]     != null ? `LLM ${pct(m["llm_recall"] as number)}` : null;
    const urg = m["urgent_recall"]  != null ? `악화 ${m["urgent_recall"]}` : null;
    return [kw, llm, urg].filter(Boolean).join(" · ") || "—";
  }
  if (key === "schedule") {
    const total = m["total_cases"] != null ? `${m["total_cases"]}케이스` : null;
    return total ?? "—";
  }
  if (key === "chart") {
    const total = m["total_cases"] != null ? `${m["total_cases"]}케이스` : null;
    return total ?? "—";
  }
  return "—";
}

// 모듈별 WARN 항목 추출
function buildWarnSummary(report: FullReport) {
  const warn: { module: string; items: string[] }[] = [];
  const pass: string[] = [];
  for (const [key, mod] of Object.entries(report.modules)) {
    const warnItems = mod.checks.filter((c) => c.status === "WARN").map((c) => c.item);
    if (warnItems.length > 0) {
      warn.push({ module: MODULE_LABEL[key] ?? key, items: warnItems });
    } else if (mod.overall === "PASS") {
      pass.push(MODULE_LABEL[key] ?? key);
    }
  }
  return { warn, pass };
}

function AgentFullReportSection({
  report,
  loading,
  error,
  onRunAll,
}: {
  report: FullReport | null;
  loading: boolean;
  error: string | null;
  onRunAll: () => void;
}) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null);

  const verdictColor = !report ? "" :
    report.overall_verdict === "CRITICAL_FAIL" ? "text-red-600" :
    report.overall_verdict === "PARTIAL_FAIL"  ? "text-amber-600" :
    "text-slate-800";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-slate-700">에이전트 성능 벤치마크</p>
          <p className="text-xs text-slate-600">Triage · 경과필터 · 라우터 · Reception · MCP 일괄 평가</p>
        </div>
        <button
          onClick={onRunAll}
          disabled={loading}
          className="flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:opacity-40"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          {loading ? "평가 중..." : "전체 에이전트 평가 실행"}
        </button>
      </div>

      {error && <p className="text-xs text-red-400">오류: {error}</p>}

      {report && (
        <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
          {/* 판정 헤더 */}
          <div className="flex items-center gap-3 border-b border-slate-100 px-5 py-3">
            <span className="text-xs font-semibold text-slate-600">종합 판정</span>
            <span className={`text-base font-black ${verdictColor}`}>{report.overall_verdict}</span>
            {report.critical_reasons.length > 0 && (
              <span className="text-xs text-red-500">{report.critical_reasons.join(" / ")}</span>
            )}
          </div>

          {/* 지금 문제 요약 */}
          {(() => {
            const { warn: warnMods, pass: passMods } = buildWarnSummary(report);
            if (warnMods.length === 0) return null;
            return (
              <div className="border-b border-amber-100 bg-amber-50 px-5 py-4 space-y-1.5">
                <p className="text-xs font-semibold text-amber-700 mb-2">해결이 필요한 항목</p>
                {warnMods.map(({ module, items }) => (
                  <div key={module} className="flex gap-2 text-xs">
                    <span className="font-semibold text-slate-700 w-20 shrink-0">{module}</span>
                    <span className="text-slate-600">{items.join(", ")}</span>
                  </div>
                ))}
                {passMods.length > 0 && (
                  <p className="pt-1 text-xs text-slate-600">
                    정상 동작 중: {passMods.join(" · ")}
                  </p>
                )}
              </div>
            );
          })()}

          {/* 모듈별 요약 테이블 */}
          <table className="w-full text-xs">
            <thead className="border-b border-slate-100 bg-slate-50 text-slate-600">
              <tr>
                <th className="px-5 py-2 text-left font-medium">에이전트</th>
                <th className="px-5 py-2 text-center font-medium w-20">결과</th>
                <th className="px-5 py-2 text-left font-medium">주요 지표</th>
                <th className="px-5 py-2 text-center font-medium w-16">상세</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {Object.entries(report.modules).map(([key, mod]) => (
                <tr key={key} className="hover:bg-slate-50">
                  <td className="px-5 py-3 font-semibold text-slate-700">{MODULE_LABEL[key] ?? key}</td>
                  <td className="px-5 py-3 text-center">
                    <StatusText status={mod.overall} />
                  </td>
                  <td className="px-5 py-3 text-slate-600">{moduleKeyMetric(key, mod)}</td>
                  <td className="px-5 py-3 text-center">
                    <button
                      onClick={() => setExpandedKey(expandedKey === key ? null : key)}
                      className="text-slate-600 underline hover:text-slate-600"
                    >
                      {expandedKey === key ? "닫기" : "보기"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* 상세 체크 (토글) */}
          {expandedKey && report.modules[expandedKey as keyof typeof report.modules] && (
            <div className="border-t border-slate-100 bg-slate-50 px-5 py-4 space-y-2">
              <p className="text-xs font-semibold text-slate-600">{MODULE_LABEL[expandedKey] ?? expandedKey} 체크 상세</p>
              {(report.modules[expandedKey as keyof typeof report.modules]!.checks).map((c, i) => (
                <div key={i} className="text-xs">
                  <span className="text-slate-600">[{i+1}] {c.item}</span>
                  {" "}<StatusText status={c.status} />
                  <span className="ml-2 text-slate-600">{c.detail}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {!report && !loading && (
        <div className="rounded-xl border border-dashed border-slate-200 py-8 text-center">
          <p className="text-xs text-slate-600">버튼을 눌러 모든 에이전트를 한 번에 평가하세요.</p>
        </div>
      )}
    </div>
  );
}

// ── WARN 패턴 집계 바 ─────────────────────────────────────────
function WarnPatternBar({ rows }: { rows: ValidationRow[] }) {
  const counts: Record<string, { warn: number; total: number }> = {};

  for (const row of rows) {
    const checksDict = (!Array.isArray(row.checks) && row.checks && typeof row.checks === "object")
      ? (row.checks as ValidationChecks)
      : {};
    for (const mod of [checksDict.triage, checksDict.schedule, checksDict.chart]) {
      if (!mod) continue;
      for (const check of mod.checks ?? []) {
        if (check.status === "SKIPPED") continue;
        if (!counts[check.item]) counts[check.item] = { warn: 0, total: 0 };
        counts[check.item].total++;
        if (check.status === "WARN") counts[check.item].warn++;
      }
    }
  }

  const sorted = Object.entries(counts)
    .filter(([, v]) => v.warn > 0)
    .sort((a, b) => b[1].warn / b[1].total - a[1].warn / a[1].total);

  if (sorted.length === 0) return null;

  return (
    <div className="rounded-xl border border-slate-200 bg-white px-5 py-4">
      <p className="mb-4 text-xs font-semibold text-slate-600">
        최근 {rows.length}건 WARN 패턴
      </p>
      <div className="space-y-3">
        {sorted.map(([item, { warn, total }]) => {
          const ratio = warn / total;
          const isHigh = ratio >= 0.6;
          return (
            <div key={item} className="flex items-center gap-3">
              <span className="w-32 shrink-0 text-xs text-slate-700">{item}</span>
              <div className="flex-1 h-1.5 rounded-full bg-slate-100 overflow-hidden">
                <div
                  className={`h-full rounded-full ${isHigh ? "bg-amber-400" : "bg-slate-300"}`}
                  style={{ width: `${ratio * 100}%` }}
                />
              </div>
              <span className="w-24 shrink-0 text-right text-xs text-slate-600">
                {warn}/{total} ({Math.round(ratio * 100)}%)
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── 최근 케이스 end-to-end 카드 ──────────────────────────────
function RecentCaseCard({ row }: { row: ValidationRow }) {
  const checksDict = (!Array.isArray(row.checks) && row.checks && typeof row.checks === "object")
    ? (row.checks as ValidationChecks)
    : {};
  const trgMod = checksDict.triage;
  const schMod = checksDict.schedule;
  const chtMod = checksDict.chart;

  // 각 단계 핵심 요약
  const trgSub = (() => {
    const signal = trgMod?.checks.find((c) => c.item === "완료 신호");
    if (!signal) return "";
    const um = signal.detail.match(/urgency=([A-Z]+)\((\d)\)/);
    const cm = signal.detail.match(/chief_complaint='([^']+)'/);
    return [um ? `${um[1]}(${um[2]})` : null, cm ? cm[1] : null].filter(Boolean).join(" · ");
  })();

  const schSub = (() => {
    const timing = schMod?.checks.find((c) => c.item === "예약 타이밍");
    if (!timing) return "";
    if (timing.status === "WARN") return "기준 초과 ⚠";
    const m = timing.detail.match(/(\d+일 후 예약)/);
    return m ? m[1] : "";
  })();

  const chtSub = (() => {
    const soap = chtMod?.checks.find((c) => c.item === "SOAP 섹션 완전성");
    if (!soap) return "";
    return soap.status === "PASS" ? "SOAP 완전" : "SOAP 미흡 ⚠";
  })();

  const steps = [
    { label: "챗봇 진입", status: "OK" as const, sub: "접수 완료" },
    { label: "문진 (Triage)", status: trgMod?.status ?? null, sub: trgSub },
    { label: "예약 (Schedule)", status: schMod?.status ?? null, sub: schSub },
    { label: "차트 (Chart)", status: chtMod?.status ?? null, sub: chtSub },
  ];

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <span className="text-xs font-semibold text-slate-600 uppercase tracking-wide">최근 케이스 흐름</span>
          <span className="ml-2 font-mono text-sm font-bold text-slate-700">#{row.emrid}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-600">{fmtTime(row.createdAt)}</span>
          <span className={`text-xs font-bold ${row.overall === "ATTENTION" ? "text-amber-600" : "text-slate-700"}`}>
            {row.overall}
          </span>
        </div>
      </div>

      {/* 흐름 */}
      <div className="flex items-center gap-4 flex-wrap">
        {steps.map((step, i) => (
          <div key={step.label} className="flex items-center gap-4">
            <div className={`rounded-lg border px-4 py-3 text-center min-w-[108px] ${
              step.status === "WARN"
                ? "border-amber-200 bg-amber-50"
                : "border-slate-100 bg-slate-50"
            }`}>
              <p className="text-xs text-slate-600">{step.label}</p>
              <p className={`mt-1 text-sm font-bold ${
                step.status === "WARN"
                  ? "text-amber-600"
                  : step.status === "PASS" || step.status === "OK"
                  ? "text-slate-800"
                  : "text-slate-600"
              }`}>
                {step.status === "OK" ? "PASS" : step.status ?? "—"}
              </p>
              {step.sub && (
                <p className="mt-1 text-xs text-slate-600 leading-tight">{step.sub}</p>
              )}
            </div>
            {i < steps.length - 1 && (
              <span className="text-slate-600 text-base">→</span>
            )}
          </div>
        ))}
      </div>

      {row.summary && (
        <p className="mt-3 text-xs text-slate-600">{row.summary}</p>
      )}
    </div>
  );
}

// ── 에이전트 탭용 최근 케이스 결과 ───────────────────────────
function RecentAgentResult({ row, agentKey }: { row: ValidationRow; agentKey: "triage" | "schedule" | "chart" }) {
  const checksDict = (!Array.isArray(row.checks) && row.checks && typeof row.checks === "object")
    ? (row.checks as ValidationChecks)
    : {};
  const mod = checksDict[agentKey];

  if (!mod) return null;

  // ── Triage 핵심 지표 파싱
  let triageHighlight: { urgency: string | null; level: string | null; complaint: string | null } | null = null;
  if (agentKey === "triage") {
    const signal = mod.checks.find((c) => c.item === "완료 신호");
    const um = signal?.detail.match(/urgency=([A-Z]+)\((\d)\)/);
    const cm = signal?.detail.match(/chief_complaint='([^']+)'/);
    triageHighlight = {
      urgency: um ? um[1] : null,
      level: um ? um[2] : null,
      complaint: cm ? cm[1] : null,
    };
  }

  // ── Schedule 핵심 지표 파싱
  let scheduleHighlight: { days: string | null; warn: boolean } | null = null;
  if (agentKey === "schedule") {
    const timing = mod.checks.find((c) => c.item === "예약 타이밍");
    const dm = timing?.detail.match(/(\d+)일 후 예약/);
    scheduleHighlight = { days: dm ? dm[1] : null, warn: timing?.status === "WARN" };
  }

  // ── Chart 핵심 지표 파싱
  const SOAP_CRITERIA: Record<string, string> = {
    S: "30자↑ · 주증상·경과",
    O: "'내원' 표현 포함",
    A: "의심/감별/추정/가능성",
    P: "검사/처치/재진/모니터링",
  };
  let chartHighlight: {
    soap: AgentCheck | null;
    quality: AgentCheck | null;
    soapSections: { label: string; pass: boolean; desc: string; criteria: string }[];
  } | null = null;
  if (agentKey === "chart") {
    const soap    = mod.checks.find((c) => c.item === "SOAP 섹션 완전성") ?? null;
    const quality = mod.checks.find((c) => c.item === "임상 품질") ?? null;
    const detail  = soap?.detail ?? "";
    const soapSections = [
      { label: "S", pass: !detail.includes("S("), desc: "주증상·경과", criteria: SOAP_CRITERIA.S },
      { label: "O", pass: !detail.includes("O("), desc: "신체검사",    criteria: SOAP_CRITERIA.O },
      { label: "A", pass: !detail.includes("A("), desc: "감별·추정",   criteria: SOAP_CRITERIA.A },
      { label: "P", pass: !detail.includes("P("), desc: "처치 계획",   criteria: SOAP_CRITERIA.P },
    ];
    if (soap?.status === "PASS") soapSections.forEach((s) => (s.pass = true));
    chartHighlight = { soap, quality, soapSections };
  }

  const AGENT_LABEL: Record<string, string> = { triage: "문진", schedule: "예약", chart: "차트" };

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-slate-600 uppercase tracking-wide">
            {AGENT_LABEL[agentKey]} 에이전트 · 최근 케이스 자동 평가
          </span>
          <span className="font-mono text-xs text-slate-600">#{row.emrid}</span>
        </div>
        <span className={`rounded px-2 py-0.5 text-xs font-bold ${
          mod.status === "WARN" ? "bg-amber-50 text-amber-600" : "bg-slate-100 text-slate-600"
        }`}>
          {mod.status === "PASS" ? "정상" : mod.status === "WARN" ? "주의" : mod.status}
        </span>
      </div>

      {/* ── Triage 핵심 요약 */}
      {triageHighlight && (triageHighlight.urgency || triageHighlight.complaint) && (
        <div className="mb-5 flex items-center gap-6 rounded-lg bg-slate-50 px-4 py-3">
          {triageHighlight.urgency && (
            <div className="text-center">
              <p className="text-xs text-slate-600 mb-1">응급도</p>
              <p className="text-base font-black text-slate-800">{triageHighlight.urgency}</p>
              {triageHighlight.level && (
                <p className="text-xs text-slate-600">Lv.{triageHighlight.level}</p>
              )}
            </div>
          )}
          {triageHighlight.complaint && (
            <div className="border-l border-slate-200 pl-5">
              <p className="text-xs text-slate-600 mb-1">주증상</p>
              <p className="text-sm font-semibold text-slate-800">{triageHighlight.complaint}</p>
            </div>
          )}
        </div>
      )}

      {/* ── Schedule 핵심 요약 */}
      {scheduleHighlight && (
        <div className="mb-5 flex items-center gap-3 rounded-lg bg-slate-50 px-4 py-3">
          {scheduleHighlight.warn ? (
            <p className="text-sm font-semibold text-amber-600">예약 타이밍 기준 초과</p>
          ) : scheduleHighlight.days ? (
            <>
              <span className="text-2xl font-black text-slate-800">{scheduleHighlight.days}일 후</span>
              <span className="text-sm text-slate-600">예약 확정</span>
            </>
          ) : (
            <p className="text-xs text-slate-600">예약 타이밍 정보 없음</p>
          )}
        </div>
      )}

      {/* ── Chart 핵심 요약 */}
      {chartHighlight && (
        <div className="mb-5 space-y-3">
          {/* SOAP 섹션별 — 규칙 기반 */}
          <div className="rounded-lg bg-slate-50 px-4 py-3">
            <p className="text-xs text-slate-600 mb-2">
              SOAP 섹션 완전성
              <span className="ml-1 text-slate-600">· 규칙 기반</span>
            </p>
            <div className="flex gap-2">
              {chartHighlight.soapSections.map(({ label, pass, desc, criteria }) => (
                <div key={label} className={`flex flex-col items-center rounded-lg border px-3 py-2.5 flex-1 ${
                  pass
                    ? "border-blue-200 bg-blue-50"
                    : "border-amber-200 bg-amber-50"
                }`}>
                  <span className={`text-sm font-black ${pass ? "text-blue-700" : "text-amber-700"}`}>{label}</span>
                  <span className="text-xs font-semibold text-slate-600 mt-0.5">{desc}</span>
                  <span className="mt-1 text-xs text-slate-600 text-center leading-tight">{criteria}</span>
                  <span className={`mt-1.5 text-xs font-bold ${pass ? "text-blue-600" : "text-amber-600"}`}>
                    {pass ? "✓ 충족" : "✗ 미흡"}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* 임상 품질 — LLM 판정 */}
          {chartHighlight.quality && chartHighlight.quality.status !== "SKIPPED" && (
            <div className={`rounded-lg px-4 py-3 ${
              chartHighlight.quality.status === "WARN" ? "bg-amber-50" : "bg-slate-50"
            }`}>
              <p className="text-xs text-slate-600 mb-1">
                임상 품질
                <span className="ml-1 text-slate-600">· LLM 판정</span>
              </p>
              <div className="flex items-start gap-2">
                <span className={`shrink-0 text-xs font-bold ${
                  chartHighlight.quality.status === "WARN" ? "text-amber-600" : "text-slate-700"
                }`}>
                  {chartHighlight.quality.status === "PASS" ? "통과" : "주의"}
                </span>
                {chartHighlight.quality.detail && (
                  <span className="text-xs text-slate-600 leading-relaxed">
                    — {chartHighlight.quality.detail}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 체크 항목 목록 */}
      <div className="space-y-1.5 border-t border-slate-100 pt-4">
        <p className="text-xs font-semibold text-slate-600 mb-2">항목별 평가 결과</p>
        {mod.checks.map((c, i) => (
          <div key={i} className={`flex items-start gap-3 rounded-lg px-3 py-2.5 ${
            c.status === "WARN" ? "bg-amber-50" : "bg-slate-50"
          }`}>
            <span className={`mt-0.5 shrink-0 text-xs font-bold ${
              c.status === "WARN" ? "text-amber-500" : "text-slate-600"
            }`}>
              {c.status === "WARN" ? "⚠" : "✓"}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold text-slate-700">{c.item}</span>
                <span className={`shrink-0 text-xs font-bold ${
                  c.status === "WARN" ? "text-amber-600" : "text-slate-600"
                }`}>
                  {c.status === "PASS" ? "통과" : c.status === "WARN" ? "주의" : c.status}
                </span>
              </div>
              {c.detail && (
                <p className="mt-1 text-xs text-slate-600 leading-relaxed">{c.detail}</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── 대시보드 데이터 계산 ──────────────────────────────────────
const WARN_DESC: Record<string, string> = {
  "컨텍스트 연속성":   "슬롯 추출 정확도 낮음",
  "완료 신호":         "문진 필드 미완성",
  "응급도 정합성":     "응급도 불일치",
  "응급도 판단":       "응급도 내부 모순",
  "SOAP 섹션 완전성":  "SOAP 항목 누락",
  "임상 품질":         "임상 품질 주의",
  "예약 타이밍":       "예약 타이밍 초과",
  "근무시간":          "근무시간 외 예약",
  "빈 슬롯":           "슬롯 충돌",
  "핸드오프 수신":     "에이전트 연결 이상",
};

interface DashData {
  overallScore: number | null;
  scoreDiff: number | null;
  passCount: number;
  warnCount: number;
  total: number;
  agentScores: { name: string; score: number }[];
  scoreTrend: { date: string; score: number }[];
  topWarns: { agent: string; item: string; count: number; desc: string }[];
}

function computeDashboardData(rows: ValidationRow[]): DashData {
  const now = Date.now();
  const oneWeekMs = 7 * 24 * 60 * 60 * 1000;

  const extractChecks = (row: ValidationRow) => {
    const cd = (!Array.isArray(row.checks) && row.checks && typeof row.checks === "object")
      ? (row.checks as ValidationChecks) : {};
    return [cd.triage, cd.schedule, cd.chart] as const;
  };

  const computeScore = (subset: ValidationRow[]): number | null => {
    let total = 0, pass = 0;
    for (const row of subset) {
      for (const mod of extractChecks(row)) {
        if (!mod) continue;
        for (const c of mod.checks) {
          if (c.status === "SKIPPED") continue;
          total++;
          if (c.status === "PASS") pass++;
        }
      }
    }
    return total > 0 ? Math.round((pass / total) * 1000) / 10 : null;
  };

  const overallScore = computeScore(rows);
  const thisWeek = rows.filter(r => r.createdAt && now - new Date(r.createdAt).getTime() < oneWeekMs);
  const lastWeek  = rows.filter(r => {
    if (!r.createdAt) return false;
    const age = now - new Date(r.createdAt).getTime();
    return age >= oneWeekMs && age < 2 * oneWeekMs;
  });
  const twScore = computeScore(thisWeek);
  const lwScore = computeScore(lastWeek);
  const scoreDiff = twScore != null && lwScore != null
    ? Math.round((twScore - lwScore) * 10) / 10 : null;

  const passCount = rows.filter(r => r.overall === "OK").length;
  const warnCount = rows.filter(r => r.overall === "ATTENTION").length;

  // 에이전트별 점수
  const agentStats: Record<string, { pass: number; total: number }> = {
    triage: { pass: 0, total: 0 },
    schedule: { pass: 0, total: 0 },
    chart: { pass: 0, total: 0 },
  };
  for (const row of rows) {
    const cd = (!Array.isArray(row.checks) && row.checks && typeof row.checks === "object")
      ? (row.checks as ValidationChecks) : {};
    for (const key of ["triage", "schedule", "chart"] as const) {
      const mod = cd[key];
      if (!mod) continue;
      for (const c of mod.checks) {
        if (c.status === "SKIPPED") continue;
        agentStats[key].total++;
        if (c.status === "PASS") agentStats[key].pass++;
      }
    }
  }
  const agentScores = [
    { key: "triage",   name: "Triage"   },
    { key: "schedule", name: "Schedule" },
    { key: "chart",    name: "Chart"    },
  ].map(({ key, name }) => {
    const s = agentStats[key as keyof typeof agentStats];
    return { name, score: s.total > 0 ? Math.round(s.pass / s.total * 100) : 0 };
  });

  // 날짜별 점수 추이
  const dateMap: Record<string, { pass: number; total: number }> = {};
  for (const row of rows) {
    if (!row.createdAt) continue;
    const date = row.createdAt.slice(0, 10);
    if (!dateMap[date]) dateMap[date] = { pass: 0, total: 0 };
    for (const mod of extractChecks(row)) {
      if (!mod) continue;
      for (const c of mod.checks) {
        if (c.status === "SKIPPED") continue;
        dateMap[date].total++;
        if (c.status === "PASS") dateMap[date].pass++;
      }
    }
  }
  const scoreTrend = Object.entries(dateMap)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, { pass, total }]) => ({
      date: date.slice(5),
      score: total > 0 ? Math.round(pass / total * 100) : 0,
    }));

  // Top WARN 항목
  const warnMap: Record<string, { agent: string; item: string; count: number }> = {};
  for (const row of rows) {
    const cd = (!Array.isArray(row.checks) && row.checks && typeof row.checks === "object")
      ? (row.checks as ValidationChecks) : {};
    for (const [agentKey, mod] of [
      ["triage",   cd.triage  ] as const,
      ["schedule", cd.schedule] as const,
      ["chart",    cd.chart   ] as const,
    ]) {
      if (!mod) continue;
      for (const c of mod.checks) {
        if (c.status !== "WARN") continue;
        const k = `${agentKey}|${c.item}`;
        if (!warnMap[k]) warnMap[k] = { agent: agentKey, item: c.item, count: 0 };
        warnMap[k].count++;
      }
    }
  }
  const topWarns = Object.values(warnMap)
    .sort((a, b) => b.count - a.count)
    .slice(0, 5)
    .map(({ agent, item, count }) => ({
      agent: agent === "triage" ? "Triage" : agent === "schedule" ? "Schedule" : "Chart",
      item,
      count,
      desc: WARN_DESC[item] ?? item,
    }));

  return { overallScore, scoreDiff, passCount, warnCount, total: rows.length, agentScores, scoreTrend, topWarns };
}

// ── 대시보드 카드 컴포넌트 ─────────────────────────────────────
function DashScoreCard({ score, diff, total }: { score: number | null; diff: number | null; total: number }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <p className="text-xs font-semibold text-slate-600">Overall Score</p>
      <p className="mt-3 text-5xl font-black text-slate-800">
        {score != null ? `${score}%` : "—"}
      </p>
      {diff != null ? (
        <p className={`mt-1.5 text-xs font-semibold ${diff >= 0 ? "text-slate-600" : "text-amber-600"}`}>
          {diff >= 0 ? "▲" : "▼"} {Math.abs(diff)}% vs. last week
        </p>
      ) : (
        <p className="mt-1.5 text-xs text-slate-600">지난 주 데이터 없음</p>
      )}
      <p className="mt-4 text-xs text-slate-600">총 {total}건 기반</p>
    </div>
  );
}

function DashDonutCard({ pass, warn, total }: { pass: number; warn: number; total: number }) {
  const data = [
    { name: "PASS", value: pass, color: "#2f6f67" },
    { name: "WARN", value: warn, color: "#fbbf24" },
  ].filter(d => d.value > 0);
  const passRate = total > 0 ? Math.round(pass / total * 100) : 0;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <p className="text-xs font-semibold text-slate-600">판정 분포</p>
      <div className="relative mt-1">
        <ResponsiveContainer width="100%" height={140}>
          <PieChart>
            <Pie data={data} cx="50%" cy="50%" innerRadius={42} outerRadius={58} dataKey="value" strokeWidth={0}>
              {data.map((entry, i) => <Cell key={i} fill={entry.color} />)}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <span className="text-lg font-black text-slate-800">{passRate}%</span>
        </div>
      </div>
      <div className="mt-1 flex justify-center gap-5 text-xs">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: "#2f6f67" }} />
          PASS {pass}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-full bg-amber-400" />
          WARN {warn}
        </span>
      </div>
    </div>
  );
}

function DashBarCard({ agents }: { agents: { name: string; score: number }[] }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <p className="mb-2 text-xs font-semibold text-slate-600">에이전트 평균 점수</p>
      <ResponsiveContainer width="100%" height={155}>
        <BarChart data={agents} margin={{ top: 4, right: 4, bottom: 0, left: -22 }}>
          <XAxis dataKey="name" tick={{ fontSize: 10, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
          <YAxis domain={[0, 100]} tick={{ fontSize: 9, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
          <Tooltip
            formatter={(v) => [`${Number(v)}%`, "점수"]}
            contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #e2e8f0", boxShadow: "none" }}
          />
          <Bar dataKey="score" fill="#2f6f67" radius={[4, 4, 0, 0]} maxBarSize={40} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function DashTrendCard({ trend }: { trend: { date: string; score: number }[] }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <p className="mb-2 text-xs font-semibold text-slate-600">종합 점수 추이</p>
      <ResponsiveContainer width="100%" height={170}>
        <LineChart data={trend} margin={{ top: 4, right: 8, bottom: 0, left: -22 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
          <YAxis domain={[0, 100]} tick={{ fontSize: 9, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
          <Tooltip
            formatter={(v) => [`${Number(v)}%`, "점수"]}
            contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #e2e8f0", boxShadow: "none" }}
          />
          <Line type="monotone" dataKey="score" stroke="#2f6f67" strokeWidth={2} dot={{ r: 2, fill: "#2f6f67" }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function DashWarnCard({ warns }: { warns: { agent: string; item: string; count: number; desc: string }[] }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <p className="mb-3 text-xs font-semibold text-slate-600">주요 경고 항목 (Top WARN)</p>
      {warns.length === 0 ? (
        <p className="py-6 text-center text-xs text-slate-600">경고 항목 없음</p>
      ) : (
        <div className="space-y-3.5">
          {warns.map(({ agent, desc, count }, i) => (
            <div key={i} className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-bold text-slate-700">{agent}</p>
                <p className="mt-0.5 text-xs leading-tight text-slate-600">{desc}</p>
              </div>
              <span className="mt-0.5 shrink-0 rounded bg-amber-50 px-2 py-0.5 text-xs font-bold text-amber-600">
                {count}건
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── 전체 성능 탭 ──────────────────────────────────────────────
function OverallTab({
  rows,
  loading,
  batchLoading,
  error,
  onRunRecent,
}: {
  rows: ValidationRow[] | null;
  loading: boolean;
  batchLoading: boolean;
  error: string | null;
  onRunRecent: () => void;
}) {
  const dash = rows && rows.length > 0 ? computeDashboardData(rows) : null;

  return (
    <div className="space-y-6">
      {/* ── 로딩 */}
      {loading && (
        <div className="flex items-center gap-2 py-8 text-sm text-slate-600">
          <Loader2 className="h-4 w-4 animate-spin" /> 불러오는 중...
        </div>
      )}

      {/* ── 대시보드 (데이터 있을 때) */}
      {dash && (
        <>
          {/* 행 1: Overall Score | 판정 분포 | 에이전트 점수 */}
          <div className="grid grid-cols-3 gap-4">
            <DashScoreCard score={dash.overallScore} diff={dash.scoreDiff} total={dash.total} />
            <DashDonutCard pass={dash.passCount} warn={dash.warnCount} total={dash.total} />
            <DashBarCard agents={dash.agentScores} />
          </div>

          {/* 행 2: 점수 추이 (2/3) | Top WARN (1/3) */}
          <div className="grid grid-cols-3 gap-4">
            <div className="col-span-2">
              <DashTrendCard trend={dash.scoreTrend} />
            </div>
            <DashWarnCard warns={dash.topWarns} />
          </div>
        </>
      )}

      {/* ── 재검증 버튼 */}
      <div className="flex items-center gap-2">
        <button
          onClick={onRunRecent}
          disabled={batchLoading}
          className="flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:opacity-40"
        >
          {batchLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          {batchLoading ? "재검증 중..." : "최근 10건 재검증"}
        </button>
      </div>

      {error && <p className="text-xs text-red-400">{error}</p>}

      {/* ── EMR 별 케이스 테이블 */}
      {!loading && rows && rows.length === 0 && (
        <p className="py-8 text-center text-sm text-slate-600">
          검증 결과가 없습니다. 최근 10건 재검증을 실행해보세요.
        </p>
      )}

      {!loading && rows && rows.length > 0 && (
        <div>
          <p className="mb-3 text-xs font-semibold text-slate-600">
            케이스별 상세 <span className="font-normal text-slate-600">({rows.length}건)</span>
          </p>
          <div className="overflow-hidden rounded-xl border border-slate-200">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs text-slate-600">
              <tr>
                <th className="px-4 py-3 text-left">EMR</th>
                <th className="px-4 py-3 text-left">종합</th>
                <th className="px-4 py-3 text-left">Triage</th>
                <th className="px-4 py-3 text-left">Schedule</th>
                <th className="px-4 py-3 text-left">Chart</th>
                <th className="px-4 py-3 text-left">대화</th>
                <th className="px-4 py-3 text-left">시간</th>
                <th className="px-4 py-3 text-left">요약</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((row) => {
                const checksDict = (!Array.isArray(row.checks) && row.checks && typeof row.checks === "object")
                  ? (row.checks as ValidationChecks)
                  : {};
                const trgStatus = checksDict.triage?.status ?? null;
                const schStatus = checksDict.schedule?.status ?? null;
                const chtStatus = checksDict.chart?.status ?? null;
                const convStatus = row.conversation_status?.status ?? null;
                const convTitle = row.conversation_status?.detail ?? "";
                return (
                  <tr key={row.emrid} className="hover:bg-slate-50">
                    <td className="px-4 py-3 font-mono font-bold text-slate-700">#{row.emrid}</td>
                    <td className="px-4 py-3">
                      <StatusText status={row.overall} />
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-600">
                      {trgStatus ? <StatusText status={trgStatus} /> : "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-600">
                      {schStatus ? <StatusText status={schStatus} /> : "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-600">
                      {chtStatus ? <StatusText status={chtStatus} /> : "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-600" title={convTitle}>
                      {convStatus ? <StatusText status={convStatus} /> : "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-600">{fmtTime(row.createdAt)}</td>
                    <td className="px-4 py-3 text-xs text-slate-600">{row.summary}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          </div>
        </div>
      )}

    </div>
  );
}

// ── 탭 정의 ───────────────────────────────────────────────────
const TABS = [
  { id: "overall",   label: "전체 성능" },
  { id: "triage",    label: "Triage" },
  { id: "schedule",  label: "Schedule" },
  { id: "chart",     label: "Chart" },
  { id: "reception", label: "Reception" },
  { id: "followup",  label: "경과 필터" },
] as const;

type TabId = (typeof TABS)[number]["id"];

const AGENT_CONFIG: Record<Exclude<TabId, "overall">, {
  label: string;
  endpoint: string | null;
  logsEndpoint?: string | null;
  desc: string;
}> = {
  triage:    { label: "Triage",    endpoint: "/admin/eval/triage",    desc: "응급도 정확도 · Red flag 감지율 (결정론) + 슬롯 추출 F1 · 환각 · 요약 완전성 (LLM). 15개 케이스 기준." },
  schedule:  { label: "Schedule",  endpoint: "/admin/eval/schedule",  desc: "소요시간 범위 · 응급도 순서 · 형식 유효성 (20 케이스 기준)." },
  chart:     { label: "Chart",     endpoint: "/admin/eval/chart",     desc: "SOAP 구조 완전성 · 키워드 포함율 · 단정 표현 없음 (19 케이스 기준)." },
  reception: { label: "Reception", endpoint: "/admin/eval/reception", logsEndpoint: "/admin/eval/reception/logs", desc: "MCP 도구 선택 정확도 (병원정보·운영시간·슬롯·무관질문 10케이스). MCP 서버 가동 필요." },
  followup:  { label: "경과 필터", endpoint: "/admin/eval/followup",  logsEndpoint: "/admin/eval/followup/logs", desc: "경과 필터 에이전트 분류 성능 측정. 테스트 케이스 100개 기준." },
};

// ── Main ──────────────────────────────────────────────────────
export default function EvalPanel() {
  const [activeTab, setActiveTab] = useState<TabId>("overall");
  const [fullReport, setFullReport] = useState<FullReport | null>(null);
  const [fullLoading, setFullLoading] = useState(false);
  const [fullError, setFullError] = useState<string | null>(null);

  // 케이스 검증 결과 (OverallTab + 각 에이전트 탭 공유)
  const [rows, setRows] = useState<ValidationRow[] | null>(null);
  const [rowsLoading, setRowsLoading] = useState(false);
  const [batchLoading, setBatchLoading] = useState(false);
  const [rowsError, setRowsError] = useState<string | null>(null);

  useEffect(() => {
    fetchResults();
  }, []);

  async function fetchResults() {
    setRowsLoading(true);
    setRowsError(null);
    try {
      const res = await fetch(`${API}/admin/validation/results`, { headers: authHeader() });
      const json = await res.json();
      setRows(json.result ?? []);
    } catch {
      setRowsError("결과를 불러오지 못했습니다.");
    } finally {
      setRowsLoading(false);
    }
  }

  async function runRecentValidation() {
    setBatchLoading(true);
    setRowsError(null);
    try {
      const res = await fetch(`${API}/admin/validation/run-recent?limit=10`, {
        method: "POST",
        headers: authHeader(),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      await fetchResults();
    } catch (e) {
      setRowsError(e instanceof Error ? e.message : "오류");
    } finally {
      setBatchLoading(false);
    }
  }

  async function runFullEval() {
    setFullLoading(true);
    setFullError(null);
    try {
      const res = await fetch(`${API}/admin/eval/full-report`, {
        method: "POST",
        headers: authHeader(),
      });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      setFullReport(await res.json());
    } catch (e) {
      setFullError(e instanceof Error ? e.message : "오류");
    } finally {
      setFullLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl p-8">
      {/* 헤더 */}
      <div className="mb-6">
        <h1 className="flex items-center gap-2 text-xl font-black text-slate-800">
          <FlaskConical className="h-5 w-5 text-slate-600" /> AI 에이전트 평가
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          에이전트별 성능 벤치마크 및 케이스 단위 전체 흐름 검증.
        </p>
      </div>

      {/* 탭 */}
      <div className="mb-8 flex gap-0 border-b border-slate-200">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={[
              "px-4 py-2.5 text-sm font-semibold transition border-b-2 -mb-px",
              activeTab === tab.id
                ? "border-slate-800 text-slate-800"
                : "border-transparent text-slate-600 hover:text-slate-600",
            ].join(" ")}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* 콘텐츠 */}
      {activeTab === "overall" ? (
        <OverallTab
          rows={rows}
          loading={rowsLoading}
          batchLoading={batchLoading}
          error={rowsError}
          onRunRecent={runRecentValidation}
        />
      ) : (
        <AgentBenchmarkTab
          logsEndpoint={AGENT_CONFIG[activeTab as Exclude<TabId, "overall">].logsEndpoint}
          recentRow={rows?.[0] ?? null}
          agentKey={
            (activeTab === "triage" || activeTab === "schedule" || activeTab === "chart")
              ? activeTab
              : undefined
          }
        />
      )}
    </div>
  );
}
