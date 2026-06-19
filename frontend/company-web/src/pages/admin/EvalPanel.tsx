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
interface AgentMetrics {
  keyword_recall?: number | null;
  keyword_precision?: number | null;
  llm_recall?: number | null;
  llm_precision?: number | null;
  urgent_recall?: string;
  total_cases?: number;
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
  scheduleid?: number | null;
  message?: string;
  category?: string;
  severity?: string;
  is_saved?: boolean;
  has_media?: boolean;
  [key: string]: unknown;
}
interface ValidationRow {
  emrid: number;
  createdAt: string | null;
  overall: OverallStatus;
  completeness: number | null;
  checks: AgentCheck[];
  summary: string;
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

// ── 벤치마크 리포트 ───────────────────────────────────────────
function BenchmarkReport({ result }: { result: AgentEvalResult }) {
  const m = result.metrics;
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 font-mono text-sm text-slate-700">
      {/* 헤더 */}
      <div className="flex items-baseline justify-between border-b border-slate-200 pb-3">
        <span className="font-sans text-base font-bold text-slate-800">
          {result.agent} 벤치마크 결과
        </span>
        <span className="text-xs text-slate-400">{result.ran_at ?? new Date().toLocaleString("ko-KR")}</span>
      </div>

      {/* 종합 판정 */}
      <div className="mt-4 text-xs text-slate-400">
        종합 판정:{" "}
        <StatusText status={result.overall} />
        {m.total_cases != null && (
          <span className="ml-4 text-slate-400">케이스 {m.total_cases}개</span>
        )}
      </div>

      {/* 체크 목록 */}
      <div className="mt-5 space-y-4">
        {result.checks.map((c, i) => (
          <div key={c.item}>
            <div className="text-xs text-slate-500">
              [{i + 1}] {c.item}
            </div>
            <div className="mt-0.5 pl-4 text-xs">
              결과: <StatusText status={c.status} />
            </div>
            <div className="mt-0.5 pl-4 text-xs text-slate-400">{c.detail}</div>
          </div>
        ))}
      </div>

      {/* 메트릭 */}
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
function MonitoringTable({
  logs,
  loading,
  onRefresh,
}: {
  logs: MonitoringLog[];
  loading: boolean;
  onRefresh: () => void;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-slate-500">실시간 운영 로그 (최근 10건)</p>
        <button
          onClick={onRefresh}
          disabled={loading}
          className="flex items-center gap-1 rounded border border-slate-200 px-2 py-1 text-xs text-slate-500 hover:bg-slate-50 disabled:opacity-40"
        >
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
          새로고침
        </button>
      </div>

      {logs.length === 0 && !loading ? (
        <p className="py-6 text-center text-xs text-slate-400">
          아직 로그가 없습니다. 채팅으로 경과 메시지를 보내면 기록됩니다.
        </p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200">
          <table className="w-full font-mono text-xs">
            <thead className="border-b border-slate-200 bg-slate-50 text-slate-400">
              <tr>
                <th className="px-3 py-2 text-left">시간</th>
                <th className="px-3 py-2 text-left">메시지</th>
                <th className="px-3 py-2 text-left">카테고리</th>
                <th className="px-3 py-2 text-left">심각도</th>
                <th className="px-3 py-2 text-left">저장</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {logs.map((log, i) => (
                <tr key={i} className="hover:bg-slate-50">
                  <td className="px-3 py-2 text-slate-400 whitespace-nowrap">
                    {log.ts?.slice(11, 16) ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-slate-600 max-w-xs truncate">
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
                      <span className="text-slate-700 font-bold">Y</span>
                    ) : (
                      <span className="text-slate-300">N</span>
                    )}
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

      {/* ── 운영 모니터링 (logsEndpoint 있을 때만) ── */}
      {logsEndpoint && (
        <div className="border-t border-slate-200 pt-6">
          <MonitoringTable logs={logs} loading={logsLoading} onRefresh={fetchLogs} />
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
                <th className="px-4 py-3 text-left">시간</th>
                <th className="px-4 py-3 text-left">요약</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((row) => {
                const checks: AgentCheck[] = Array.isArray(row.checks) ? row.checks : [];
                const trg = checks.find((c) => /^1|triage|응급/i.test(c.item));
                const sch = checks.find((c) => /^2|예약|schedule/i.test(c.item));
                const cht = checks.find((c) => /^3|차트|chart/i.test(c.item));
                return (
                  <tr key={row.emrid} className="hover:bg-slate-50">
                    <td className="px-4 py-3 font-mono font-bold text-slate-700">#{row.emrid}</td>
                    <td className="px-4 py-3">
                      <StatusText status={row.overall as CheckStatus} />
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500">
                      {trg ? <StatusText status={trg.status} /> : "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500">
                      {sch ? <StatusText status={sch.status} /> : "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500">
                      {cht ? <StatusText status={cht.status} /> : "—"}
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

      {/* 준비 중 카드 */}
      <div className="grid grid-cols-2 gap-4 pt-2">
        <ComingSoon
          label="오케스트레이터 라우팅 평가"
          desc="MCP 구현 후 활성화"
        />
        <ComingSoon
          label="MCP 안정성"
          desc="MCP 구현 후 활성화"
        />
      </div>
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
  triage:    { label: "Triage",    endpoint: null,                   desc: "슬롯 추출 F1 · 응급도 정확도 · red flag 감지율. 테스트셋 준비 후 활성화." },
  schedule:  { label: "Schedule",  endpoint: null,                   desc: "예약 타이밍 · 근무시간 · 빈슬롯 검증. MCP 구현 후 활성화." },
  chart:     { label: "Chart",     endpoint: null,                   desc: "차트 완전성 · 임상 품질 평가. judge.py 통합 후 활성화." },
  reception: { label: "Reception", endpoint: null,                   desc: "병원 안내 정확도 · 핸드오프 정확도. 테스트셋 준비 후 활성화." },
  followup:  { label: "경과 필터", endpoint: "/admin/eval/followup", logsEndpoint: "/admin/eval/followup/logs", desc: "경과 필터 에이전트 분류 성능 측정. 테스트 케이스 80개 기준." },
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
          label={AGENT_CONFIG[activeTab].label}
          endpoint={AGENT_CONFIG[activeTab].endpoint}
          logsEndpoint={AGENT_CONFIG[activeTab].logsEndpoint}
          description={AGENT_CONFIG[activeTab].desc}
        />
      )}
    </div>
  );
}
