"""레퍼런스 채점기 — vet_triage.json `scoring_engine` 명세의 '독립 재구현'.

목적: ai.triage.engine.compute_urgency(=실제 구현, SUT)가 **사람이 작성한 명세대로**
동작하는지 검증하기 위한 '제2의 독립 구현'이다. 두 구현이 같은 입력에서 항상 같은
결과를 내면, 엔진이 명세를 정확히 따른다는 차등(differential) 증거가 된다.

★ 핵심: 이 채점기는 engine.py 내부를 전혀 보지 않는다. JSON 명세의 5단계
  (red_flag → 점수합 → timing modifier → 종 보정 → 임계 매핑)만 그대로 옮긴다.
  → "AI가 AI를 평가"가 아니라 "명세 vs 구현"의 교차검증이다.

명세 출처: backend/data/triage/vet_triage.json > scoring_engine.steps (steps 1~5)
"""
from __future__ import annotations

# scoring_engine.steps[5].thresholds 를 그대로 옮긴 임계표 (min 점수 → urgency).
_THRESHOLDS = [(10, "RED"), (7, "ORANGE"), (4, "YELLOW"), (0, "GREEN")]

# engine._URGENCY_MAP 과 동일한 표시 매핑(명세상 VTL 4단계 → num).
_URGENCY_NUM = {"RED": 1, "ORANGE": 2, "YELLOW": 3, "GREEN": 4}

# step4 종 보정 대상 섹션(고양이).
_CAT_PLUS1_SECTIONS = {"RESPIRATORY", "CARDIAC", "UNABLE_TO_WALK"}


def score(answers: list[dict], species: str | None, section: str | None,
          gender: str | None = None) -> dict:
    """명세 5단계를 그대로 적용해 (urgency, urgency_level_num, total_score) 산출.

    answers: walk()가 모은 선택 pill dict 리스트.
    """
    sp = (species or "").strip().lower()

    # ── step 1: red_flag 즉시 RED ────────────────────────────────
    if any(p.get("red_flag") for p in answers):
        return {"urgency": "RED", "urgency_level_num": 1, "total_score": None,
                "reason": "red_flag pill 선택 → 즉시 RED (step1)"}

    # ── step 2: urgency_score 합산 ───────────────────────────────
    total = sum(int(p["urgency_score"]) for p in answers if p.get("urgency_score") is not None)

    # ── step 3: timing modifier (is_timing pill의 urgency_modifier) ──
    timing_mod = next(
        (int(p.get("urgency_modifier", 0)) for p in answers if p.get("is_timing")),
        0,
    )
    total += timing_mod

    # ── step 4: 종 보정 ──────────────────────────────────────────
    if sp == "cat" and section in _CAT_PLUS1_SECTIONS:
        total += 1
    if sp == "cat" and section == "UROGENITAL" and (gender or "").lower() in ("male_intact", "male"):
        total += 2

    # ── step 5: 임계 매핑 ────────────────────────────────────────
    urgency = "GREEN"
    for min_score, label in _THRESHOLDS:
        if total >= min_score:
            urgency = label
            break

    return {
        "urgency": urgency,
        "urgency_level_num": _URGENCY_NUM[urgency],
        "total_score": total,
        "reason": f"score={total} → {urgency} (steps 2~5)",
    }
