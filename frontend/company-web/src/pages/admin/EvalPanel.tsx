import { useState } from "react";
import { FlaskConical, Loader2, RefreshCw } from "lucide-react";
import { getAdminToken } from "../../onboarding/api";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

type CheckStatus = "PASS" | "WARN" | "SKIPPED";

interface Check {
  item: string;
  status: CheckStatus;
  detail: string;
}

interface Metrics {
  keyword_recall: number | null;
  keyword_precision: number | null;
  llm_recall: number | null;
  llm_precision: number | null;
  urgent_recall: string;
  total_cases: number;
}

interface EvalResult {
  agent: string;
  overall: CheckStatus;
  checks: Check[];
  metrics: Metrics;
}

const STATUS_STYLE: Record<CheckStatus, string> = {
  PASS: "bg-green-100 text-green-700",
  WARN: "bg-yellow-100 text-yellow-700",
  SKIPPED: "bg-slate-100 text-slate-500",
};

const OVERALL_STYLE: Record<CheckStatus, string> = {
  PASS: "border-green-300 bg-green-50 text-green-700",
  WARN: "border-yellow-300 bg-yellow-50 text-yellow-700",
  SKIPPED: "border-slate-200 bg-slate-50 text-slate-500",
};

function pct(v: number | null) {
  if (v === null) return "—";
  return `${Math.round(v * 100)}%`;
}

export default function EvalPanel() {
  const [result, setResult] = useState<EvalResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runEval() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/admin/eval/followup`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getAdminToken()}` },
      });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      setResult(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "알 수 없는 오류");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl p-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-black text-slate-800">
            <FlaskConical className="h-5 w-5 text-blue-500" /> AI 에이전트 평가
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            경과 필터 에이전트의 분류 성능을 측정합니다.
          </p>
        </div>
        <button
          onClick={runEval}
          disabled={loading}
          className="flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-bold text-white transition hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          {loading ? "평가 중..." : "평가 실행"}
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-600">
          오류: {error}
        </div>
      )}

      {!result && !loading && !error && (
        <div className="rounded-2xl border border-slate-200 bg-white p-12 text-center text-slate-400">
          <FlaskConical className="mx-auto mb-3 h-10 w-10 opacity-30" />
          <p className="text-sm">평가 실행 버튼을 눌러 시작하세요.</p>
          <p className="mt-1 text-xs">경과 필터 AI 테스트 케이스 80개를 기준으로 측정합니다.</p>
        </div>
      )}

      {result && (
        <div className="space-y-4">
          {/* 종합 결과 */}
          <div className={`rounded-2xl border p-5 ${OVERALL_STYLE[result.overall]}`}>
            <div className="flex items-center justify-between">
              <span className="text-sm font-bold">경과 필터 에이전트 (followup_filter)</span>
              <span className={`rounded-full px-3 py-1 text-xs font-bold ${STATUS_STYLE[result.overall]}`}>
                {result.overall}
              </span>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-3 text-center text-xs">
              <div className="rounded-xl bg-white/60 p-3">
                <p className="text-slate-500">키워드 Recall</p>
                <p className="mt-1 text-2xl font-black">{pct(result.metrics.keyword_recall)}</p>
              </div>
              <div className="rounded-xl bg-white/60 p-3">
                <p className="text-slate-500">LLM Recall</p>
                <p className="mt-1 text-2xl font-black">{pct(result.metrics.llm_recall)}</p>
              </div>
              <div className="rounded-xl bg-white/60 p-3">
                <p className="text-slate-500">Urgent 감지</p>
                <p className="mt-1 text-2xl font-black">{result.metrics.urgent_recall}</p>
              </div>
            </div>
            <p className="mt-2 text-right text-xs opacity-60">총 {result.metrics.total_cases}개 케이스</p>
          </div>

          {/* 체크 목록 */}
          <div className="rounded-2xl border border-slate-200 bg-white">
            {result.checks.map((check, i) => (
              <div
                key={check.item}
                className={`flex items-start gap-4 p-4 ${i !== result.checks.length - 1 ? "border-b border-slate-100" : ""}`}
              >
                <span className={`mt-0.5 shrink-0 rounded-full px-2.5 py-0.5 text-xs font-bold ${STATUS_STYLE[check.status]}`}>
                  {check.status}
                </span>
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
