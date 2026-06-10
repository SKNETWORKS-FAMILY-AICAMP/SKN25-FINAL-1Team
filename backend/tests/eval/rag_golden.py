"""RAG 검색 평가용 골든셋 — '증상 표현 → 기대 진료과' (사람이 라벨/검수).

[검수 방법 — 도메인(수의/실무) 담당이 확인할 것]
  각 항목의 query(보호자 일상어)에 대해 expected_department(기대 진료과)가
  '상식적으로 맞는지'만 보면 된다. 의학적 확정 진단이 아니라 "이 증상이면 보통 어느 과로
  가는가" 수준의 분류다. 애매하면 rationale를 보고 동의/수정한다.

  · 동의하면 그대로 둔다.
  · 진료과가 틀렸다 싶으면 expected_department를 고친다(아래 DEPARTMENTS 중 택1).
  · 너무 모호한 query(여러 과 가능)는 빼거나 더 구체적으로 바꾼다.

코퍼스 진료과(2026-06 적재본 기준, 총 19,206건):
  내과 9846 / 외과 5107 / 피부과 2533 / 안과 970 / 치과 750
→ 내과·외과가 과반이라, 변별력 평가를 위해 피부과·안과·치과 비중을 의도적으로 높였다.
"""
from __future__ import annotations

DEPARTMENTS = ("내과", "외과", "피부과", "안과", "치과")

GOLDEN: list[dict] = [
    # ── 안과 ──────────────────────────────────────────────
    {"query": "눈이 뿌옇게 흐려지고 자꾸 깜빡여요",
     "expected_department": "안과", "rationale": "각막 혼탁·불편감 → 안과"},
    {"query": "눈에 눈곱이 많이 끼고 충혈됐어요",
     "expected_department": "안과", "rationale": "결막염 양상 → 안과"},
    {"query": "눈을 잘 못 뜨고 눈물이 계속 흘러요",
     "expected_department": "안과", "rationale": "유루·안검경련 → 안과"},
    # ── 피부과 ────────────────────────────────────────────
    {"query": "피부가 빨갛게 붓고 가려워서 계속 긁어요",
     "expected_department": "피부과", "rationale": "소양·발적 → 피부과"},
    {"query": "털이 군데군데 빠지고 비듬이 생겨요",
     "expected_department": "피부과", "rationale": "탈모·각질 → 피부과"},
    {"query": "발가락 사이를 자꾸 핥고 진물이 나요",
     "expected_department": "피부과", "rationale": "지간 피부염 → 피부과"},
    # ── 치과 ──────────────────────────────────────────────
    {"query": "입냄새가 심하고 잇몸이 빨갛게 부었어요",
     "expected_department": "치과", "rationale": "치주염 양상 → 치과"},
    {"query": "이빨이 흔들리고 딱딱한 걸 잘 못 씹어요",
     "expected_department": "치과", "rationale": "치아 동요·저작곤란 → 치과"},
    {"query": "침을 많이 흘리고 입 주변을 아파해요",
     "expected_department": "치과", "rationale": "구강 통증 → 치과"},
    # ── 외과 ──────────────────────────────────────────────
    {"query": "산책하다 다리를 다쳐서 절뚝거려요",
     "expected_department": "외과", "rationale": "외상성 파행 → 외과"},
    {"query": "상처가 벌어져서 꿰매야 할 것 같아요",
     "expected_department": "외과", "rationale": "열창·창상 봉합 → 외과"},
    {"query": "배에 혹 같은 게 만져지고 점점 커져요",
     "expected_department": "외과", "rationale": "종괴 → 외과적 평가"},
    # ── 내과 ──────────────────────────────────────────────
    {"query": "어제부터 구토하고 설사를 계속해요",
     "expected_department": "내과", "rationale": "급성 위장관 증상 → 내과"},
    {"query": "기침을 계속하고 숨쉬기 힘들어해요",
     "expected_department": "내과", "rationale": "호흡기 증상 → 내과"},
    {"query": "물을 너무 많이 마시고 소변을 자주 봐요",
     "expected_department": "내과", "rationale": "다음다뇨 → 내과(내분비/신장)"},
]
