/**
 * Validation / Judge 모니터링 타입.
 *
 * 운영진 콘솔이 백엔드에서 받아오는 검증/심사 레코드의 형태 정의:
 *   - Validation: validation_resultDB (ai/agents/validation.py 출력 — 결정론적 4종 점검)
 *   - Judge: judge audit log (ai/agents/judge.py 출력 — LLM 운영 품질 모니터링)
 *
 * (과거 데모용 MOCK_VALIDATION / MOCK_JUDGE 더미 데이터는 EvalPanel 도입으로 미사용이 되어 제거함.
 *  타입은 onboarding/api.ts 의 정규화 함수가 계속 참조하므로 유지.)
 */

export type CheckStatus = "PASS" | "WARN" | "SKIPPED";

export interface ValidationCheck {
  item: string;
  status: CheckStatus;
  detail: string;
}

export interface ValidationRecord {
  emrid: number;
  createdAt: string;
  overall: "OK" | "ATTENTION";
  checks: ValidationCheck[];
  completeness: number; // 0~10
  summary: string;
}

export interface JudgeRecord {
  emrid: number;
  createdAt: string;
  verdict: "HEALTHY" | "NEEDS_REVIEW";
  scores: {
    completeness: number;
    question_efficiency: number;
    response_consistency: number;
    structuring_quality: number;
  };
  turnCount: number;
  notes: string;
}
