/**
 * Validation / Judge 모니터링 목업.
 *
 * ⚠️ 데모용. 실제로는 백엔드에서 받아온다:
 *   - Validation: validation_resultDB (ai/agents/validation.py 출력 — 결정론적 4종 점검)
 *   - Judge: judge audit log (ai/agents/judge.py 출력 — LLM 운영 품질 모니터링)
 * 키/형태는 위 두 에이전트 실제 출력과 동일하게 맞춰 둠.
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

const CHECK_ITEMS = ["데이터 완전성", "문진-차트 일치도", "예약 안전성", "응급신호 정합성"] as const;

const ok = (details: [string, string, string, string]): ValidationCheck[] =>
  CHECK_ITEMS.map((item, i) => ({ item, status: "PASS" as CheckStatus, detail: details[i] }));

export const MOCK_VALIDATION: ValidationRecord[] = [
  {
    emrid: 1042,
    createdAt: "2026-06-15T09:12:00",
    overall: "OK",
    completeness: 10,
    checks: ok([
      "필수 문진 정보 모두 수집됨",
      "문진 증상 4개 중 차트 언급 4개 (일치율 100%)",
      "예약 메타데이터 정상",
      "사전 정의된 응급 신호 표현 미감지",
    ]),
    summary: "특이 검증 이슈 없음",
  },
  {
    emrid: 1043,
    createdAt: "2026-06-15T08:40:00",
    overall: "ATTENTION",
    completeness: 10,
    checks: [
      { item: "데이터 완전성", status: "PASS", detail: "필수 문진 정보 모두 수집됨" },
      { item: "문진-차트 일치도", status: "PASS", detail: "일치율 75%" },
      { item: "예약 안전성", status: "PASS", detail: "예약 메타데이터 정상" },
      {
        item: "응급신호 정합성",
        status: "WARN",
        detail: "응급 신호 표현(이물 섭취, 반복 구토) 감지됐으나 triage 응급도 Level 5(낮음) — 재확인 권고",
      },
    ],
    summary: "수의사 검토 권고: 응급 신호 ↔ 응급도 불일치",
  },
  {
    emrid: 1044,
    createdAt: "2026-06-14T17:05:00",
    overall: "ATTENTION",
    completeness: 6,
    checks: [
      { item: "데이터 완전성", status: "WARN", detail: "누락 항목: 성별, 발현 시점" },
      { item: "문진-차트 일치도", status: "PASS", detail: "일치율 100%" },
      { item: "예약 안전성", status: "PASS", detail: "예약 메타데이터 정상" },
      { item: "응급신호 정합성", status: "PASS", detail: "사전 정의된 응급 신호 표현 미감지" },
    ],
    summary: "수의사 검토 권고: 필수 문진 정보 누락",
  },
  {
    emrid: 1045,
    createdAt: "2026-06-14T15:22:00",
    overall: "ATTENTION",
    completeness: 10,
    checks: [
      { item: "데이터 완전성", status: "PASS", detail: "필수 문진 정보 모두 수집됨" },
      { item: "문진-차트 일치도", status: "WARN", detail: "문진 증상 2개 중 차트 언급 0개 (일치율 0% < 50%)" },
      { item: "예약 안전성", status: "PASS", detail: "예약 메타데이터 정상" },
      { item: "응급신호 정합성", status: "PASS", detail: "사전 정의된 응급 신호 표현 미감지" },
    ],
    summary: "수의사 검토 권고: 문진-차트 불일치 의심",
  },
  {
    emrid: 1046,
    createdAt: "2026-06-14T11:48:00",
    overall: "OK",
    completeness: 10,
    checks: ok([
      "필수 문진 정보 모두 수집됨",
      "일치율 80%",
      "예약 메타데이터 정상",
      "응급 신호 표현 감지(기침) — 응급도 Level과 일치",
    ]),
    summary: "특이 검증 이슈 없음",
  },
];

export const MOCK_JUDGE: JudgeRecord[] = [
  {
    emrid: 1042,
    createdAt: "2026-06-15T09:12:00",
    verdict: "HEALTHY",
    scores: { completeness: 9.0, question_efficiency: 8.8, response_consistency: 9.2, structuring_quality: 8.5 },
    turnCount: 6,
    notes: "필수 항목을 효율적으로 수집하고 구조화 결과가 일관됨.",
  },
  {
    emrid: 1043,
    createdAt: "2026-06-15T08:40:00",
    verdict: "NEEDS_REVIEW",
    scores: { completeness: 8.0, question_efficiency: 8.5, response_consistency: 6.4, structuring_quality: 7.2 },
    turnCount: 6,
    notes: "대화 내용과 구조화된 응급도 사이 일관성이 낮음 — 프롬프트 점검 권고.",
  },
  {
    emrid: 1044,
    createdAt: "2026-06-14T17:05:00",
    verdict: "NEEDS_REVIEW",
    scores: { completeness: 5.5, question_efficiency: 7.0, response_consistency: 7.8, structuring_quality: 7.0 },
    turnCount: 4,
    notes: "필수 문진 항목 일부를 끝까지 수집하지 못함(성별·발현시점).",
  },
  {
    emrid: 1045,
    createdAt: "2026-06-14T15:22:00",
    verdict: "NEEDS_REVIEW",
    scores: { completeness: 8.2, question_efficiency: 8.0, response_consistency: 7.5, structuring_quality: 5.8 },
    turnCount: 5,
    notes: "자연어를 구조화 데이터로 변환하는 품질이 낮음 — 차트 표류.",
  },
  {
    emrid: 1046,
    createdAt: "2026-06-14T11:48:00",
    verdict: "HEALTHY",
    scores: { completeness: 8.8, question_efficiency: 9.1, response_consistency: 8.6, structuring_quality: 8.4 },
    turnCount: 5,
    notes: "전반적으로 양호.",
  },
];
