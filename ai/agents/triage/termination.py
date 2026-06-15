from ai.agents.triage.rules import (
    get_section,
    get_minimum_fields,
    get_max_questions,
)

from ai.agents.triage.scoring import (
    urgency_for_score,
    max_remaining_score,
)


# 문진 종료 여부 판단
def should_finish(
    rules: dict,
    section: str,
    fields: dict,
    red_flag: bool,
    question_count: int,
    score: int,
):

    # 레드플래그 → 즉시 종료
    if red_flag:
        return True

    section_rule = get_section(rules, section)

    if not section_rule:
        return True

    # 남은 정보로 응급도 등급이 더는 바뀔 수 없으면 종료
    low = urgency_for_score(section_rule, score, False)
    high = urgency_for_score(
        section_rule,
        score + max_remaining_score(section_rule, fields),
        False,
    )

    minimum = get_minimum_fields(rules, section)
    minimum_met = all(field in fields for field in minimum)

    if low == high and minimum_met:
        return True

    # 최대 질문 수 도달 → 종료
    if question_count >= get_max_questions(rules, section):
        return True

    return False
