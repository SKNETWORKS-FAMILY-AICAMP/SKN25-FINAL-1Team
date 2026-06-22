import { useEffect, useState } from "react";
import { FlaskConical, Loader2, RefreshCw, Construction } from "lucide-react";
import { getAdminToken } from "../../onboarding/api";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

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
      : "text-slate-400 font-medium";
  return <span className={cls}>{status}</span>;
}

// ── 준비 중 ────────────────────────────────────────────────────
function ComingSoon({ label, desc }: { label: string; desc: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-slate-200 py-12 text-center">
      <Construction className="h-7 w-7 text-slate-300" />
      <p className="text-sm font-semibold text-slate-400">{label}</p>
      <p className="max-w-xs text-xs text-slate-300">{desc}</p>
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
          <span className="ml-2 text-sm font-normal text-slate-400">(케이스: {m.total_cases}개)</span>
        )}
      </span>
      <span className="text-xs text-slate-400">{result.ran_at ?? new Date().toLocaleString("ko-KR")}</span>
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
        <p className="mb-4 text-xs font-semibold uppercase tracking-wide text-slate-400">분류 정확도</p>
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-100 text-slate-400">
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
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            악화 신호 감지 <span className="normal-case font-normal text-slate-400">(urgent, 100% 필수)</span>
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
          <p className="mb-4 text-xs font-semibold uppercase tracking-wide text-slate-400">LLM 판단 확신도</p>
          <div className="flex items-center gap-6">
            <div>
              <p className="text-xs text-slate-400">평균 confidence</p>
              <p className={`mt-1 text-2xl font-black ${m.avg_confidence < 0.7 ? "text-amber-600" : "text-slate-800"}`}>
                {Math.round(m.avg_confidence * 100)}%
              </p>
            </div>
            {m.low_confidence_cases && m.low_confidence_cases.length > 0 && (
              <div>
                <p className="text-xs text-slate-400">저신뢰 케이스 <span className="text-slate-300">(&lt; 70%)</span></p>
                <p className="mt-1 text-2xl font-black text-amber-600">{m.low_confidence_cases.length}건</p>
              </div>
            )}
          </div>

          {m.low_confidence_cases && m.low_confidence_cases.length > 0 && (
            <table className="mt-4 w-full text-xs">
              <thead>
                <tr className="border-b border-slate-100 text-slate-400">
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
          <p className="mb-4 text-xs font-semibold uppercase tracking-wide text-slate-400">카테고리별 Keyword recall</p>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-100 text-slate-400">
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
                    <td className="py-2.5 text-center text-slate-400">{stat.total}</td>
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
        <p className="mb-4 text-xs font-semibold uppercase tracking-wide text-slate-400">결정론 체크 (엔진)</p>
        <div className="flex gap-12">
          <div>
            <p className="text-xs text-slate-400">응급도 정확도</p>
            <p className={`mt-1 text-3xl font-black ${urgAcc != null && urgAcc < 0.95 ? "text-amber-600" : "text-slate-800"}`}>
              {urgAcc != null ? `${Math.round(urgAcc * 100)}%` : "—"}
            </p>
            {m.urgency_cases != null && (
              <p className="mt-0.5 text-xs text-slate-400">{m.urgency_cases}개 케이스 · 기준 95%</p>
            )}
          </div>
          <div>
            <p className="text-xs text-slate-400">Red flag 감지율</p>
            <p className={`mt-1 text-3xl font-black ${!rfOk && rfRaw !== "N/A" ? "text-amber-600" : "text-slate-800"}`}>
              {rfRaw}
            </p>
            <p className="mt-0.5 text-xs text-slate-400">100% 필수</p>
          </div>
        </div>
      </div>

      {/* 응급도 오분류 */}
      {m.urgency_errors && m.urgency_errors.length > 0 && (
        <div className="mt-6 border-t border-slate-100 pt-4">
          <p className="mb-3 text-xs font-semibold text-slate-400">응급도 오분류</p>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-100 text-slate-400">
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
        <p className="mb-4 text-xs font-semibold uppercase tracking-wide text-slate-400">LLM 체크</p>
        <div className="flex gap-12">
          <div>
            <p className="text-xs text-slate-400">슬롯 추출 F1</p>
            <p className={`mt-1 text-3xl font-black ${m.slot_f1 != null && m.slot_f1 < 0.8 ? "text-amber-600" : "text-slate-800"}`}>
              {m.slot_f1 != null ? m.slot_f1.toFixed(2) : "—"}
            </p>
            {m.slot_precision != null && m.slot_recall != null && (
              <p className="mt-0.5 text-xs text-slate-400">P={m.slot_precision.toFixed(2)} R={m.slot_recall.toFixed(2)} · 기준 0.80</p>
            )}
          </div>
          <div>
            <p className="text-xs text-slate-400">환각 의심</p>
            <p className={`mt-1 text-3xl font-black ${(m.hallucination_count ?? 0) > 0 ? "text-amber-600" : "text-slate-800"}`}>
              {m.hallucination_count ?? "—"}건
            </p>
            <p className="mt-0.5 text-xs text-slate-400">예상 외 변수 추출</p>
          </div>
          <div>
            <p className="text-xs text-slate-400">요약 완전성</p>
            <p className={`mt-1 text-3xl font-black ${m.summary_score != null && m.summary_score < 0.8 ? "text-amber-600" : "text-slate-800"}`}>
              {m.summary_score != null ? `${Math.round(m.summary_score * 100)}%` : "—"}
            </p>
            <p className="mt-0.5 text-xs text-slate-400">키워드 포함율 · 기준 80%</p>
          </div>
        </div>
        {m.llm_errors != null && m.llm_errors > 0 && (
          <p className="mt-3 text-xs text-amber-500">LLM 오류 {m.llm_errors}건</p>
        )}
      </div>

      {/* 체크 목록 */}
      <div className="mt-10 border-t border-slate-100 pt-6">
        <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">체크 목록</p>
        <div className="space-y-3">
          {result.checks.map((c, i) => (
            <div key={c.item}>
              <div className="text-xs text-slate-500">[{i + 1}] {c.item}</div>
              <div className="mt-0.5 pl-4 text-xs">결과: <StatusText status={c.status} /></div>
              <div className="mt-0.5 pl-4 text-xs text-slate-400">{c.detail}</div>
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
            <div className="text-xs text-slate-500">[{i + 1}] {c.item}</div>
            <div className="mt-0.5 pl-4 text-xs">결과: <StatusText status={c.status} /></div>
            <div className="mt-0.5 pl-4 text-xs text-slate-400">{c.detail}</div>
          </div>
        ))}
      </div>

      <div className="mt-6 border-t border-slate-200 pt-3 text-xs text-slate-400">
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
          <span className="ml-2 text-sm font-normal text-slate-400">
            ({logs.length}건 / 최대 200건)
          </span>
        </span>
        <button
          onClick={() => { setPage(0); onRefresh(); }}
          disabled={loading}
          className="flex items-center gap-1 rounded border border-slate-200 px-2 py-1 text-xs text-slate-500 hover:bg-slate-50 disabled:opacity-40"
        >
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
          새로고침
        </button>
      </div>

      {logs.length === 0 && !loading ? (
        <p className="py-8 text-center text-xs text-slate-400">
          아직 로그가 없습니다. 채팅으로 경과 메시지를 보내면 기록됩니다.
        </p>
      ) : (
        <>
          <div className="mt-5 overflow-hidden rounded-lg border border-slate-100">
            <table className="w-full text-xs">
              <thead className="border-b border-slate-100 bg-slate-50 text-slate-400">
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
                    <td className="px-3 py-2 text-slate-400 whitespace-nowrap">
                      {log.ts?.slice(11, 16) ?? "—"}
                    </td>
                    <td className="px-3 py-2 text-slate-600 max-w-[200px] truncate">
                      {log.message ?? "—"}
                    </td>
                    <td className="px-3 py-2 text-slate-500">{log.category ?? "—"}</td>
                    <td className="px-3 py-2">
                      <span className={log.severity === "urgent_possible" ? "text-amber-600 font-bold" : "text-slate-500"}>
                        {log.severity ?? "—"}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      {log.is_saved ? (
                        <span className="font-bold text-slate-700">Y</span>
                      ) : (
                        <span className="text-slate-300">N</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="mt-3 flex items-center justify-between text-xs text-slate-400">
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

// ── 에이전트 벤치마크 탭 ─────────────────────────────────────
function AgentBenchmarkTab({
  label,
  endpoint,
  description,
  logsEndpoint,
}: {
  label: string;
  endpoint: string | null;
  description: string;
  logsEndpoint?: string | null;
}) {
  const [result, setResult] = useState<AgentEvalResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [logs, setLogs] = useState<MonitoringLog[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);

  // 탭 전환 시(endpoint 변경) 이전 탭의 결과/에러 초기화
  useEffect(() => {
    setResult(null);
    setError(null);
  }, [endpoint]);

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

  async function runEval() {
    if (!endpoint) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}${endpoint}`, {
        method: "POST",
        headers: authHeader(),
      });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const data = await res.json();
      setResult({ ...data, ran_at: new Date().toLocaleString("ko-KR") });
    } catch (e) {
      setError(e instanceof Error ? e.message : "오류");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-8">
      {/* ── 운영 모니터링 (logsEndpoint 있을 때만) ── */}
      {logsEndpoint && (
        <MonitoringTable logs={logs} loading={logsLoading} onRefresh={fetchLogs} />
      )}

      {/* ── 벤치마크 ── */}
      <div className="space-y-4">
        <p className="text-xs font-semibold text-slate-500">벤치마크 (테스트셋)</p>

        {!endpoint ? (
          <ComingSoon label={`${label} 벤치마크`} desc={description} />
        ) : (
          <>
            <div className="flex items-center justify-between">
              <p className="text-sm text-slate-400">{description}</p>
              <button
                onClick={runEval}
                disabled={loading}
                className="flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:opacity-40"
              >
                {loading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4" />
                )}
                {loading ? "평가 중..." : "평가 실행"}
              </button>
            </div>

            {error && <p className="text-xs text-red-400">오류: {error}</p>}

            {!result && !loading && (
              <div className="rounded-xl border border-dashed border-slate-200 py-16 text-center">
                <FlaskConical className="mx-auto mb-2 h-8 w-8 text-slate-200" />
                <p className="text-sm text-slate-400">평가 실행 버튼을 눌러 시작하세요.</p>
              </div>
            )}

            {result && <BenchmarkReport result={result} />}
          </>
        )}
      </div>
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
  };
  critical_reasons: string[];
}

const MODULE_LABEL: Record<string, string> = {
  triage:       "Triage",
  mcp_health:   "MCP",
  orchestrator: "라우터",
  reception:    "Reception",
  followup:     "경과 필터",
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
  return "—";
}

function AgentFullReportSection() {
  const [report, setReport] = useState<FullReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedKey, setExpandedKey] = useState<string | null>(null);

  async function runAll() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/admin/eval/full-report`, {
        method: "POST",
        headers: authHeader(),
      });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      setReport(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "오류");
    } finally {
      setLoading(false);
    }
  }

  const verdictColor = !report ? "" :
    report.overall_verdict === "CRITICAL_FAIL" ? "text-red-600" :
    report.overall_verdict === "PARTIAL_FAIL"  ? "text-amber-600" :
    "text-slate-800";

  return (
    <div className="space-y-4 border-t border-slate-200 pt-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-slate-700">에이전트 성능 벤치마크</p>
          <p className="text-xs text-slate-400">Triage · 경과필터 · 라우터 · Reception · MCP 일괄 평가</p>
        </div>
        <button
          onClick={runAll}
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
            <span className="text-xs font-semibold text-slate-400">종합 판정</span>
            <span className={`text-base font-black ${verdictColor}`}>{report.overall_verdict}</span>
            {report.critical_reasons.length > 0 && (
              <span className="text-xs text-red-500">{report.critical_reasons.join(" / ")}</span>
            )}
          </div>

          {/* 모듈별 요약 테이블 */}
          <table className="w-full text-xs">
            <thead className="border-b border-slate-100 bg-slate-50 text-slate-400">
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
                  <td className="px-5 py-3 text-slate-500">{moduleKeyMetric(key, mod)}</td>
                  <td className="px-5 py-3 text-center">
                    <button
                      onClick={() => setExpandedKey(expandedKey === key ? null : key)}
                      className="text-slate-400 underline hover:text-slate-600"
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
              <p className="text-xs font-semibold text-slate-500">{MODULE_LABEL[expandedKey] ?? expandedKey} 체크 상세</p>
              {(report.modules[expandedKey as keyof typeof report.modules]!.checks).map((c, i) => (
                <div key={i} className="text-xs">
                  <span className="text-slate-400">[{i+1}] {c.item}</span>
                  {" "}<StatusText status={c.status} />
                  <span className="ml-2 text-slate-400">{c.detail}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {!report && !loading && (
        <div className="rounded-xl border border-dashed border-slate-200 py-8 text-center">
          <p className="text-xs text-slate-400">버튼을 눌러 모든 에이전트를 한 번에 평가하세요.</p>
        </div>
      )}
    </div>
  );
}

// ── 전체 성능 탭 ──────────────────────────────────────────────
function OverallTab() {
  const [rows, setRows] = useState<ValidationRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [runLoading, setRunLoading] = useState(false);
  const [scheduleId, setScheduleId] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchResults();
  }, []);

  async function fetchResults() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/admin/validation/results`, {
        headers: authHeader(),
      });
      const json = await res.json();
      setRows(json.result ?? []);
    } catch {
      setError("결과를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }

  async function runValidation() {
    if (!scheduleId) return;
    setRunLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${API}/admin/validation/run?schedule_id=${scheduleId}`,
        { method: "POST", headers: authHeader() }
      );
      if (!res.ok) throw new Error(`${res.status}`);
      await fetchResults();
      setScheduleId("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "오류");
    } finally {
      setRunLoading(false);
    }
  }

  const total = rows?.length ?? 0;
  const attentionCount = rows?.filter((r) => r.overall === "ATTENTION").length ?? 0;

  return (
    <div className="space-y-6">
      {/* 요약 수치 */}
      <div className="flex gap-8 border-b border-slate-200 pb-5 text-sm">
        <div>
          <p className="text-xs text-slate-400">총 검증</p>
          <p className="mt-1 text-2xl font-black text-slate-800">{loading ? "—" : `${total}건`}</p>
        </div>
        <div>
          <p className="text-xs text-slate-400">ATTENTION</p>
          <p className={`mt-1 text-2xl font-black ${attentionCount > 0 ? "text-amber-600" : "text-slate-800"}`}>
            {loading ? "—" : `${attentionCount}건`}
            {total > 0 && !loading && (
              <span className="ml-1 text-sm font-semibold text-slate-400">
                ({Math.round((attentionCount / total) * 100)}%)
              </span>
            )}
          </p>
        </div>
        <div>
          <p className="text-xs text-slate-400">평균 완전성</p>
          <p className="mt-1 text-2xl font-black text-slate-800">
            {rows && rows.some((r) => r.completeness != null)
              ? `${(
                  rows.reduce((s, r) => s + (r.completeness ?? 0), 0) /
                  rows.filter((r) => r.completeness != null).length
                ).toFixed(1)} / 10`
              : "—"}
          </p>
        </div>
      </div>

      {/* 케이스 실행 */}
      <div className="flex items-center gap-2">
        <input
          type="number"
          placeholder="Schedule ID"
          value={scheduleId}
          onChange={(e) => setScheduleId(e.target.value)}
          className="w-36 rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
        />
        <button
          onClick={runValidation}
          disabled={runLoading || !scheduleId}
          className="flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:opacity-40"
        >
          {runLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          케이스 검증 실행
        </button>
      </div>

      {error && <p className="text-xs text-red-400">{error}</p>}

      {/* EMR 테이블 */}
      {loading && (
        <div className="flex items-center gap-2 py-8 text-sm text-slate-400">
          <Loader2 className="h-4 w-4 animate-spin" /> 불러오는 중...
        </div>
      )}

      {!loading && rows && rows.length === 0 && (
        <p className="py-8 text-center text-sm text-slate-400">
          검증 결과가 없습니다. Schedule ID를 입력해 케이스 검증을 실행해보세요.
        </p>
      )}

      {!loading && rows && rows.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-slate-200">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs text-slate-500">
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
                    <td className="px-4 py-3 text-xs text-slate-500">
                      {trgStatus ? <StatusText status={trgStatus} /> : "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500">
                      {schStatus ? <StatusText status={schStatus} /> : "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500">
                      {chtStatus ? <StatusText status={chtStatus} /> : "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500" title={convTitle}>
                      {convStatus ? <StatusText status={convStatus} /> : "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-400">{fmtTime(row.createdAt)}</td>
                    <td className="px-4 py-3 text-xs text-slate-500">{row.summary}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <AgentFullReportSection />
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
  schedule:  { label: "Schedule",  endpoint: null,                    desc: "예약 타이밍 · 근무시간 · 빈슬롯 검증. 테스트셋 준비 후 활성화." },
  chart:     { label: "Chart",     endpoint: null,                    desc: "차트 완전성 · 임상 품질 평가. judge.py 통합 후 활성화." },
  reception: { label: "Reception", endpoint: "/admin/eval/reception", desc: "MCP 도구 선택 정확도 (병원정보·운영시간·슬롯·무관질문 4케이스). MCP 서버 가동 필요." },
  followup:  { label: "경과 필터", endpoint: "/admin/eval/followup",  logsEndpoint: "/admin/eval/followup/logs", desc: "경과 필터 에이전트 분류 성능 측정. 테스트 케이스 100개 기준." },
};

// ── Main ──────────────────────────────────────────────────────
export default function EvalPanel() {
  const [activeTab, setActiveTab] = useState<TabId>("overall");

  return (
    <div className="mx-auto max-w-5xl p-8">
      {/* 헤더 */}
      <div className="mb-6">
        <h1 className="flex items-center gap-2 text-xl font-black text-slate-800">
          <FlaskConical className="h-5 w-5 text-slate-500" /> AI 에이전트 평가
        </h1>
        <p className="mt-1 text-sm text-slate-400">
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
                : "border-transparent text-slate-400 hover:text-slate-600",
            ].join(" ")}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* 콘텐츠 */}
      {activeTab === "overall" ? (
        <OverallTab />
      ) : (
        <AgentBenchmarkTab
          label={AGENT_CONFIG[activeTab as Exclude<TabId, "overall">].label}
          endpoint={AGENT_CONFIG[activeTab as Exclude<TabId, "overall">].endpoint}
          logsEndpoint={AGENT_CONFIG[activeTab as Exclude<TabId, "overall">].logsEndpoint}
          description={AGENT_CONFIG[activeTab as Exclude<TabId, "overall">].desc}
        />
      )}
    </div>
  );
}
