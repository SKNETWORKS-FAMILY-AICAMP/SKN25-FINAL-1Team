from pathlib import Path
import json


_RULES = None


# 룰 로드
def load_rules():

    global _RULES

    if _RULES:
        return _RULES

    project_root = Path(__file__).resolve().parents[3]

    path = project_root / "backend/data/triage/vet_triage.json"
    with open(
        path,
        "r",
        encoding="utf-8",
    ) as f:
        _RULES = json.load(f)

    return _RULES


# 섹션 조회
def get_section(
    rules: dict,
    section_name: str,
):

    for section in rules.get("sections", []):

        if section.get("id") == section_name:
            return section

    return None


# 섹션의 field_schema 조회
def get_field_schema(
    rules: dict,
    section_id: str,
):

    section = get_section(rules, section_id)

    if not section:
        return {}

    return section.get("field_schema", {})


# 우선순위 정렬된 질문 목록
def get_questions(
    rules: dict,
    section_id: str,
):

    section = get_section(rules, section_id)

    if not section:
        return []

    return sorted(
        section.get("questions", []),
        key=lambda x: x.get("priority", 999),
    )


# id로 질문 조회
def get_question(
    rules: dict,
    section_id: str,
    question_id: str,
):

    for question in get_questions(rules, section_id):

        if question.get("id") == question_id:
            return question

    return None


# 최대 질문 수
def get_max_questions(
    rules: dict,
    section_id: str,
):

    section = get_section(rules, section_id)

    if not section:
        return 5

    return section.get("max_questions", 5)


# 종료 전 최소 확인 필드
def get_minimum_fields(
    rules: dict,
    section_id: str,
):

    section = get_section(rules, section_id)

    if not section:
        return []

    return section.get("minimum_fields", [])


# 추출 프롬프트용 섹션/필드 안내 텍스트 생성
def build_sections_guide(
    rules: dict,
):

    lines = []

    for section in rules.get("sections", []):

        schema = section.get("field_schema", {})

        fields = "; ".join(
            f"{name}: {'|'.join(values)}"
            for name, values in schema.items()
        )

        lines.append(
            f"[{section.get('id')}] {section.get('label', '')} — "
            f"{section.get('goal', '')}\n  {fields}"
        )

    return "\n".join(lines)


# 추출용 JSON 스키마 생성 (field_schema 기반)
def build_extract_schema(
    rules: dict,
):

    field_props = {}

    for section in rules.get("sections", []):

        for name, values in (section.get("field_schema") or {}).items():

            # 모르는 필드는 null 허용
            field_props[name] = {
                "type": ["string", "null"],
                "enum": [*values, None],
            }

    section_ids = [s.get("id") for s in rules.get("sections", [])]

    return {
        "title": "TriageExtraction",
        "type": "object",
        "properties": {
            "intent": {"type": "string", "enum": ["triage", "recall", "off_topic"]},
            "section": {"type": ["string", "null"], "enum": [*section_ids, None]},
            "red_flag": {"type": "boolean"},
            "red_flag_chief": {"type": ["string", "null"]},
            "fields": {
                "type": "object",
                "properties": field_props,
                "required": list(field_props.keys()),
                "additionalProperties": False,
            },
            "observations": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "intent",
            "section",
            "red_flag",
            "red_flag_chief",
            "fields",
            "observations",
        ],
        "additionalProperties": False,
    }


# 추출 프롬프트용 red_flag 신호 안내 텍스트 생성
def build_red_flag_guide(
    rules: dict,
):

    flags = rules.get("red_flags", {}).get("flags", [])

    chiefs = [
        flag.get("chief", "")
        for flag in flags
        if flag.get("chief")
    ]

    return ", ".join(dict.fromkeys(chiefs))


# red_flag 발동 시 안내 메시지
def get_red_flag_message(
    rules: dict,
):

    return rules.get("red_flags", {}).get("on_trigger", {}).get(
        "chatbot_message",
        "지금 바로 병원에 내원해 주세요.",
    )


# required_if 조건 충족 여부
def _required_if_satisfied(
    required_if: dict,
    fields: dict,
):

    return all(
        fields.get(key) == value
        for key, value in (required_if or {}).items()
    )


# 다음에 물어볼 질문 선택 (무엇을 물을지 = JSON이 결정)
def select_next_question(
    rules: dict,
    section_id: str,
    fields: dict,
    asked_ids: list,
):

    for question in get_questions(rules, section_id):

        if question.get("id") in asked_ids:
            continue

        if not _required_if_satisfied(question.get("required_if", {}), fields):
            continue

        targets = question.get("extract_fields", [])

        # 해당 질문의 항목이 모두 확인됐으면 건너뜀
        if targets and all(field in fields for field in targets):
            continue

        return question

    return None
