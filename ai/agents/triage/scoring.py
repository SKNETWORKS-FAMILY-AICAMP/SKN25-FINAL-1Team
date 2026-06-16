import operator

from ai.agents.triage.rules import get_section


# CNN이 확신하는 비정상 소견의 가중치 / 신뢰 임계
_IMAGE_FINDING_SCORE = 4
_IMAGE_CONF_THRESHOLD = 70.0

# 성별이 위험을 키우는 소견의 가중치
_GENDER_FINDING_SCORE = 2


_OPS = {
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
    "==": operator.eq,
    "!=": operator.ne,
}


# 조건 문자열 값 파싱
def _parse_value(raw: str):

    low = raw.lower()

    if low == "true":
        return True

    if low == "false":
        return False

    try:
        return float(raw)
    except ValueError:
        return raw


# "total_score >= 8" / "red_flag == true" 범용 평가
def _eval_condition(
    condition: str,
    ctx: dict,
):

    parts = condition.split()

    if len(parts) != 3:
        return False

    var, op, raw = parts

    if var not in ctx or op not in _OPS:
        return False

    return bool(_OPS[op](ctx[var], _parse_value(raw)))


# 점수로 응급도 등급 판정 (임계값 = JSON urgency_rules)
def urgency_for_score(
    section_rule: dict,
    score: int,
    red_flag: bool = False,
):

    ctx = {
        "total_score": score,
        "red_flag": red_flag,
    }

    for rule in section_rule.get("urgency_rules", []):

        if _eval_condition(rule.get("condition", ""), ctx):
            return rule.get("urgency", "GREEN")

    return "GREEN"


# 아직 확인 안 된 필드에서 나올 수 있는 최대 추가 점수
def max_remaining_score(
    section_rule: dict,
    fields: dict,
):

    field_scoring = section_rule.get("field_scoring", {})

    total = 0

    for name, value_map in field_scoring.items():

        if name in fields or not value_map:
            continue

        total += max(value_map.values())

    return total


# 이미지(CNN) 소견 → (추가 점수, 의심질환 한글명 목록)
def image_findings(
    image_analysis: dict | None,
):

    if not image_analysis:
        return 0, []

    bonus = 0
    suspected: list[str] = []

    # 피부: top_class 영문 → 한글, 'healthy' 제외
    skin = image_analysis.get("skin") or {}
    s_cls, s_conf = skin.get("top_class"), skin.get("top_confidence") or 0
    if s_cls and s_cls != "healthy" and s_conf >= _IMAGE_CONF_THRESHOLD:
        from ai.services.vision_model import SKIN_CLASS_KO
        bonus += _IMAGE_FINDING_SCORE
        suspected.append(SKIN_CLASS_KO.get(s_cls, s_cls))

    # 안구: top_class 이미 한글, '정상' 제외
    eye = image_analysis.get("eye") or {}
    e_cls, e_conf = eye.get("top_class"), eye.get("top_confidence") or 0
    if e_cls and e_cls != "정상" and e_conf >= _IMAGE_CONF_THRESHOLD:
        bonus += _IMAGE_FINDING_SCORE
        suspected.append(e_cls)

    return bonus, suspected


# 성별이 위험을 키우는 소견 → 추가 점수 (암컷+생식기 / 수컷+비뇨기)
def gender_findings(
    section: str,
    fields: dict,
    gender: str | None,
):

    g = gender or ""
    female = g in ("암컷", "female", "여아")
    male = g in ("수컷", "male", "남아")

    bonus = 0

    # 암컷 + 생식기: 자궁축농증·난산 위험 (비정상 분비물·질출혈)
    if section == "REPRODUCTIVE" and female:
        if fields.get("vaginal_discharge") == "abnormal":
            bonus += _GENDER_FINDING_SCORE
        if fields.get("vaginal_bleeding") in ("spotting", "heavy"):
            bonus += _GENDER_FINDING_SCORE

    # 수컷 + 비뇨기: 요도폐색 위험 (배뇨불가·헛힘주기)
    if section == "UROLOGY" and male:
        if fields.get("urination_ability") in ("reduced", "unable"):
            bonus += _GENDER_FINDING_SCORE
        if fields.get("straining_frequency") == "frequent_no_output":
            bonus += _GENDER_FINDING_SCORE

    return bonus


# 응급도 채점
def calculate_score(
    rules: dict,
    section: str,
    fields: dict,
    red_flag: bool = False,
    image_analysis: dict | None = None,
    gender: str | None = None,
):

    section_rule = get_section(rules, section)

    if not section_rule:
        return {
            "score": 0,
            "urgency": "GREEN",
        }

    field_scoring = section_rule.get("field_scoring", {})

    score = 0

    for name, value in fields.items():
        score += field_scoring.get(name, {}).get(value, 0)

    # 이미지 소견 가중
    bonus, _ = image_findings(image_analysis)
    score += bonus

    # 성별 가중
    score += gender_findings(section, fields, gender)

    return {
        "score": score,
        "urgency": urgency_for_score(section_rule, score, red_flag),
    }
