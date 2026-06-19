import { useState } from "react";
import { FlaskConical, Loader2, RefreshCw, Construction } from "lucide-react";
import { getAdminToken } from "../../onboarding/api";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

// ── Types ────────────────────────────────────────────────────
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
}
interface ValidationRow {
  emrid: number;
  createdAt: string | null;
  overall: OverallStatus;
  completeness: number | null;
  checks: AgentCheck[];
  summary: string;
}

// ── Helpers ──────────────────────────────────────────────────
const CHECK_STYLE: Record<CheckStatus, string> = {
  PASS: "bg-green-100 text-green-700",
  WARN: "bg-yellow-100 text-yellow-700",
  SKIPPED: "bg-slate-100 text-slate-400",
};
const OVERALL_AGENT_STYLE: Record<CheckStatus, string> = {
  PASS: "border-green-300 bg-green-50 text-green-700",
  WARN: "border-yellow-300 bg-yellow-50 text-yellow-700",
  SKIPPED: "border-slate-200 bg-slate-50 text-slate-500",
};
const OVERALL_ROW_STYLE: Record<OverallStatus, string> = {
  OK: "bg-green-100 text-green-700",
  ATTENTION: "bg-red-100 text-red-600",
  SKIPPED: "bg-slate-100 text-slate-400",
};

function pct(v: number | null | undefined) {
  if (v == null) return "—";
  return `${Math.round(v * 100)}%`;
}

function authHeader() {
  return { Authorization: `Bearer ${getAdminToken()}` };
}

// ── StatusBadge ───────────────────────────────────────────────
function CheckBadge({ status }: { status: CheckStatus }) {
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${CHECK_STYLE[status]}`}>
      {status}
    </span>
  );
}

// ── 준비 중 카드 ──────────────────────────────────────────────
function ComingSoon({ label, desc }: { label: string; desc: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-10 text-center">
      <Construction className="h-8 w-8 text-slate-300" />
      <p className="text-sm font-bold text-slate-400">{label}</p>
      <p className="max-w-xs text-xs text-slate-400">{desc}</p>
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

  async function fetchResults() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/admin/validation/results`, { headers: authHeader() });
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
      const res = await fetch(`${API}/admin/validation/run?schedule_id=${scheduleId}`, {
        method: "POST",
        headers: authHeader(),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      await fetchResults();
    } catch (e) {
      setError(e instanceof Error ? e.message : "오류");
    } finally {
      setRunLoading(false);
    }
  }

  const attentionCount = rows?.filter((r) => r.overall === "ATTENTION").length ?? 0;

  return (
    <div className="space-y-6">
      {/* 요약 카드 */}
      <div className="grid grid-cols-3 gap-4">
        <div className="rounded-2xl border border-slate-200 bg-white p-5">
          <p className="text-xs text-slate-400">총 검증</p>
          <p className="mt-1 text-3xl font-black text-slate-800">{rows ? `${rows.length}건` : "—"}</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5">
          <p className="text-xs text-slate-400">ATTENTION</p>
          <p className={`mt-1 text-3xl font-black ${attentionCount > 0 ? "text-red-500" : "text-slate-800"}`}>
            {rows ? `${attentionCount}건` : "—"}
            {rows && rows.length > 0 && (
              <span className="ml-1 text-base font-bold">
                ({Math.round((attentionCount / rows.length) * 100)}%)
              </span>
            )}
          </p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5">
          <p className="text-xs text-slate-400">평균 완전성 점수</p>
          <p className="mt-1 text-3xl font-black text-slate-800">
            {rows && rows.some((r) => r.completeness != null)
              ? `${(rows.reduce((s, r) => s + (r.completeness ?? 0), 0) / rows.filter((r) => r.completeness != null).length).toFixed(1)} / 10`
              : "—"}
          </p>
        </div>
      </div>

      {/* EMR 검증 실행 */}
      <div className="flex items-center gap-3">
        <input
          type="number"
          placeholder="Schedule ID 입력"
          value={scheduleId}
          onChange={(e) => setScheduleId(e.target.value)}
          className="w-48 rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400"
        />
        <button
          onClick={runValidation}
          disabled={runLoading || !scheduleId}
          className="flex items-center gap-2 rounded-xl bg-slate-800 px-4 py-2 text-sm font-bold text-white transition hover:bg-slate-700 disabled:opacity-40"
        >
          {runLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          케이스 검증 실행
        </button>
        <button
          onClick={fetchResults}
          disabled={loading}
          className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-600 transition hover:bg-slate-50 disabled:opacity-40"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          결과 불러오기
        </button>
      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}

      {/* EMR 테이블 */}
      {rows && rows.length > 0 ? (
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-100 bg-slate-50 text-xs text-slate-500">
              <tr>
                <th className="px-4 py-3 text-left">EMR</th>
                <th className="px-4 py-3 text-left">종합</th>
                <th className="px-4 py-3 text-left">Triage</th>
                <th className="px-4 py-3 text-left">Schedule</th>
                <th className="px-4 py-3 text-left">Chart</th>
                <th className="px-4 py-3 text-left">요약</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => {
                const trg = row.checks.find((c) => c.item.startsWith("1") || c.item.includes("triage") || c.item.includes("응급"));
                const sch = row.checks.find((c) => c.item.startsWith("2") || c.item.includes("예약") || c.item.includes("schedule"));
                const cht = row.checks.find((c) => c.item.startsWith("3") || c.item.includes("차트") || c.item.includes("chart"));
                return (
                  <tr key={row.emrid} className={i % 2 === 0 ? "" : "bg-slate-50/50"}>
                    <td className="px-4 py-3 font-bold text-slate-700">#{row.emrid}</td>
                    <td className="px-4 py-3">
                      <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${OVERALL_ROW_STYLE[row.overall]}`}>
                        {row.overall}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {trg ? <CheckBadge status={trg.status as CheckStatus} /> : <span className="text-xs text-slate-300">—</span>}
                    </td>
                    <td className="px-4 py-3">
                      {sch ? <CheckBadge status={sch.status as CheckStatus} /> : <span className="text-xs text-slate-300">—</span>}
                    </td>
                    <td className="px-4 py-3">
                      {cht ? <CheckBadge status={cht.status as CheckStatus} /> : <span className="text-xs text-slate-300">—</span>}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500">{row.summary}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : rows && rows.length === 0 ? (
        <p className="text-sm text-slate-400">검증 결과가 없습니다. 케이스 검증을 실행해보세요.</p>
      ) : null}

      {/* 준비 중 카드 */}
      <div className="grid grid-cols-2 gap-4">
        <ComingSoon
          label="오케스트레이터 라우팅 평가"
          desc="에이전트 라우팅 정확도 90% 이상 여부 확인. MCP 구현 후 활성화."
        />
        <ComingSoon
          label="MCP 안정성"
          desc="MCP 도구 호출 성공률 및 응답 지연 측정. MCP 구현 후 활성화."
        />
      </div>
    </div>
  );
}

// ── 에이전트 벤치마크 탭 (공통) ───────────────────────────────
function AgentBenchmarkTab({
  label,
  endpoint,
  description,
}: {
  label: string;
  endpoint: string | null;
  description: string;
}) {
  const [result, setResult] = useState<AgentEvalResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runEval() {
    if (!endpoint) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}${endpoint}`, { method: "POST", headers: authHeader() });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      setResult(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "오류");
    } finally {
      setLoading(false);
    }
  }

  if (!endpoint) {
    return (
      <ComingSoon
        label={`${label} 평가`}
        desc={description}
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-500">{description}</p>
        <button
          onClick={runEval}
          disabled={loading}
          className="flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-bold text-white transition hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          {loading ? "평가 중..." : "평가 실행"}
        </button>
      </div>

      {error && <p className="text-sm text-red-500">오류: {error}</p>}

      {!result && !loading && (
        <div className="rounded-2xl border border-slate-200 bg-white p-12 text-center text-slate-400">
          <FlaskConical className="mx-auto mb-3 h-10 w-10 opacity-30" />
          <p className="text-sm">평가 실행 버튼을 눌러 시작하세요.</p>
        </div>
      )}

      {result && (
        <div className="space-y-4">
          {/* 종합 + 메트릭 */}
          <div className={`rounded-2xl border p-5 ${OVERALL_AGENT_STYLE[result.overall]}`}>
            <div className="flex items-center justify-between">
              <span className="text-sm font-bold">{label} 에이전트</span>
              <CheckBadge status={result.overall} />
            </div>
            <div className="mt-3 grid grid-cols-4 gap-3 text-center text-xs">
              <div className="rounded-xl bg-white/60 p-3">
                <p className="text-slate-500">키워드 Recall</p>
                <p className="mt-1 text-2xl font-black">{pct(result.metrics.keyword_recall)}</p>
              </div>
              <div className="rounded-xl bg-white/60 p-3">
                <p className="text-slate-500">LLM Recall</p>
                <p className="mt-1 text-2xl font-black">{pct(result.metrics.llm_recall)}</p>
              </div>
              <div className="rounded-xl bg-white/60 p-3">
                <p className="text-slate-500">LLM Precision</p>
                <p className="mt-1 text-2xl font-black">{pct(result.metrics.llm_precision)}</p>
              </div>
              <div className="rounded-xl bg-white/60 p-3">
                <p className="text-slate-500">Urgent 감지</p>
                <p className="mt-1 text-2xl font-black">{result.metrics.urgent_recall ?? "—"}</p>
              </div>
            </div>
            <p className="mt-2 text-right text-xs opacity-60">총 {result.metrics.total_cases ?? "?"}개 케이스</p>
          </div>

          {/* 체크 목록 */}
          <div className="rounded-2xl border border-slate-200 bg-white">
            {result.checks.map((check, i) => (
              <div
                key={check.item}
                className={`flex items-start gap-4 p-4 ${i !== result.checks.length - 1 ? "border-b border-slate-100" : ""}`}
              >
                <CheckBadge status={check.status} />
                <div>
                  <p className="text-sm font-bold text-slate-700">{check.item}</p>
                  <p className="mt-0.5 text-xs text-slate-500">{check.detail}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── 탭 정의 ───────────────────────────────────────────────────
const TABS = [
  { id: "overall",  label: "전체 성능" },
  { id: "triage",   label: "Triage" },
  { id: "schedule", label: "Schedule" },
  { id: "chart",    label: "Chart" },
  { id: "reception",label: "Reception" },
  { id: "followup", label: "경과 필터" },
] as const;

type TabId = (typeof TABS)[number]["id"];

const AGENT_CONFIG: Record<Exclude<TabId, "overall">, { label: string; endpoint: string | null; desc: string }> = {
  triage:    { label: "Triage",    endpoint: null,                  desc: "슬롯 추출 F1·응급도 정확도·red flag 감지율 측정. 테스트셋 준비 후 활성화." },
  schedule:  { label: "Schedule",  endpoint: null,                  desc: "예약 타이밍·근무시간·빈슬롯 검증. MCP 구현 후 활성화." },
  chart:     { label: "Chart",     endpoint: null,                  desc: "차트 완전성·임상 품질 LLM 평가. judge.py 통합 후 활성화." },
  reception: { label: "Reception", endpoint: null,                  desc: "병원 안내 정확도·핸드오프 정확도 측정. 테스트셋 준비 후 활성화." },
  followup:  { label: "경과 필터", endpoint: "/admin/eval/followup", desc: "경과 필터 에이전트의 분류 성능을 측정합니다. 테스트 케이스 80개 기준." },
};

// ── Main ──────────────────────────────────────────────────────
export default function EvalPanel() {
  const [activeTab, setActiveTab] = useState<TabId>("overall");

  return (
    <div className="mx-auto max-w-5xl p-8">
      {/* 헤더 */}
      <div className="mb-6">
        <h1 className="flex items-center gap-2 text-xl font-black text-slate-800">
          <FlaskConical className="h-5 w-5 text-blue-500" /> AI 에이전트 평가
        </h1>
        <p className="mt-1 text-sm text-slate-500">에이전트별 성능 벤치마크 및 케이스 단위 전체 흐름 검증.</p>
      </div>

      {/* 탭 네비게이션 */}
      <div className="mb-6 flex gap-1 rounded-2xl border border-slate-200 bg-slate-100 p-1">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={[
              "flex-1 rounded-xl py-2 text-sm font-bold transition",
              activeTab === tab.id
                ? "bg-white text-slate-800 shadow-sm"
                : "text-slate-400 hover:text-slate-600",
            ].join(" ")}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* 탭 콘텐츠 */}
      {activeTab === "overall" ? (
        <OverallTab />
      ) : (
        <AgentBenchmarkTab
          label={AGENT_CONFIG[activeTab].label}
          endpoint={AGENT_CONFIG[activeTab].endpoint}
          description={AGENT_CONFIG[activeTab].desc}
        />
      )}
    </div>
  );
}
