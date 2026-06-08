"""Triage Engine — vet_triage.json decision tree 결정론 walker + scoring.

`triage_kb.load_triage_kb()` 위에 구축한다.

설계(결정론 walker 주도):
- 노드(질문)별 JSON 질문 + pill을 제시하고, pill 선택을 따라 `next`로 이동한다.
- 종료 노드(`is_final` 또는 next 없음, red_flag pill)에 도달하면 scoring_engine 규칙으로
  urgency를 결정론적으로 산출한다(LLM 무관).
- LLM은 자유텍스트→pill 분류에만 쓰이며(chat.py), 엔진 자체는 순수 결정론이다.

scoring_engine(vet_triage.json):
  score = Σ pill.urgency_score + 선택된 timing pill.urgency_modifier + 종 보정
  종 보정: cat & section∈{RESPIRATORY,CARDIAC,UNABLE_TO_WALK} +1 / cat & UROGENITAL & male +2
  임계: red_flag→RED, ≥10 RED, ≥7 ORANGE, ≥4 YELLOW, else GREEN
"""
from __future__ import annotations

import re
from functools import lru_cache

from .kb import load_triage_kb

START_NODE = "Q_INIT_SYMPTOM"  # species는 펫 프로필에서 선주입 → Q_INIT_SPECIES 스킵

# VTL 4단계 → urgency_level_num(1~4) + 표시 라벨(3버킷)
# 라벨은 화면 표시 버킷(응급/준응급/일반)과 동일하게 맞춘다(혼동 방지).
# 세부 등급은 urgency_level_num으로 보존.
_URGENCY_MAP = {
    "RED": (1, "응급"),
    "ORANGE": (2, "준응급"),
    "YELLOW": (3, "준응급"),
    "GREEN": (4, "일반"),
}


def urgency_num_to_visit_type(urgency_num: int | None) -> str:
    """VTL 4단계(urgency_level_num) → 수의사 화면 표시 3버킷(단일 기준).

    즉시(1)            → emergency(응급)
    응급(2)·긴급(3)    → semiEmergency(준응급)
    준긴급(4) 및 그 외 → normal(일반)

    대시보드/EMR 큐/예약 화면이 모두 이 함수를 공유한다(매핑 중복·드리프트 방지).
    """
    if urgency_num == 1:
        return "emergency"
    if urgency_num in (2, 3):
        return "semiEmergency"
    return "normal"

_WS_RE = re.compile(r"\s+")
_EMOJI_RE = re.compile(r"[\U00010000-\U0010ffff]", flags=re.UNICODE)

_CLINICAL_KO_MAP = {
    "foreign body >24h": "이물 섭취 의심",
    "persistent vomiting": "반복 구토",
    "hematemesis bloody diarrhea": "혈성 구토/설사",
    "occasional vomiting mild": "경미한 구토",
    "rapid onset abdominal distension gdv": "위확장염전 의심",
    "foreign body ingestion": "이물 섭취 의심",
    "toxin ingestion": "독성물질 섭취 의심",
    "respiratory distress": "호흡곤란",
    "persistent cough": "반복 기침",
    "open mouth breathing": "개구호흡",
    "coughing": "기침",
    "acute stridor": "협착음/천명음",
    "upper airway": "상부기도 문제",
    "lower airway": "하부기도 문제",
    "pleural effusion": "흉수 의심",
    "pneumothorax": "기흉 의심",
    "subcutaneous emphysema": "피하기종",
    "brachycephalic airway syndrome": "단두종 기도증후군",
    "cardiogenic pulmonary edema": "심인성 폐부종 의심",
    "congestive heart failure": "울혈성 심부전 의심",
    "currently seizuring": "현재 발작",
    "status epilepticus": "지속성 발작",
    "post-ictal": "발작 후 상태",
    "cluster seizures": "군집 발작",
    "isolated seizure": "단발성 발작",
    "permethrin toxicity": "퍼메트린 중독 의심",
    "hypoglycemia": "저혈당 의심",
    "vomiting": "구토",
    "diarrhea": "설사",
    "hematemesis": "토혈",
    "melena": "흑변",
    "gdv": "위확장염전 의심",
    "urinary obstruction": "요도폐색 의심",
    "stranguria": "배뇨곤란",
    "trauma": "외상",
    "fracture": "골절 의심",
    "lameness": "파행",
    "pain": "통증",
    "corneal ulcer": "각막궤양 의심",
    "uveitis": "포도막염 의심",
}

_DISEASE_HINTS = (
    "의심", "증후군", "폐부종", "심부전", "기흉", "요도폐색", "위확장염전",
    "각막궤양", "포도막염", "골절", "중독", "저혈당",
)

_SECTION_DEFAULT_DISEASES = {
    "RESPIRATORY": ["기관지염/기관염", "기관허탈", "폐렴"],
    "SEIZURE": ["특발성 발작", "대사성 발작", "중독"],
    "COLLAPSE": ["실신", "쇼크", "심혈관계 이상"],
    "BLEEDING": ["외상성 출혈", "응고장애", "위장관 출혈"],
    "CARDIAC": ["부정맥", "울혈성 심부전", "심장성 실신"],
    "UNABLE_TO_WALK": ["척추/디스크 질환", "골절/탈구", "신경계 이상"],
    "GI": ["급성 위장염", "췌장염", "이물 섭취"],
    "TRAUMA": ["연부조직 손상", "골절/탈구", "교상/창상"],
    "UROGENITAL": ["방광염", "요도폐색", "요로감염"],
    "GENERAL": ["감염/염증성 질환", "대사성 질환", "통증성 질환"],
}


def _normalize(text: str) -> str:
    """공백 제거 + 소문자화(라벨 정확매칭용)."""
    return _WS_RE.sub("", (text or "").strip().lower())


def _clean_label(label: str) -> str:
    """보호자용 pill 라벨을 차트/요약에 맞는 짧은 관찰 표현으로 변환."""
    text = _EMOJI_RE.sub("", label or "")
    text = _WS_RE.sub(" ", text).strip(" ・,")
    for prefix in ("네, ", "아니요, "):
        if text.startswith(prefix):
            text = text[len(prefix):]
    replacements = (
        ("구토를 해요", "구토"),
        ("설사를 해요", "설사"),
        ("멈추지 않고 계속 구토해요", "반복 구토"),
        ("숨소리가 이상하고 힘들어 보여요", "호흡곤란/숨소리 이상"),
        ("네, 그르렁거리거나 쌕쌕 소리가 나요", "그르렁/쌕쌕 호흡음"),
        ("그르렁거리거나 쌕쌕 소리가 나요", "그르렁/쌕쌕 호흡음"),
        ("하루 종일 계속 기침해요", "반복 기침"),
        ("기침만 해요", "기침"),
        ("이물 삼킴 후 24시간 이상 됐고 구토·밥 안 먹어요", "이물 섭취 후 24시간 이상 경과 및 구토/식욕저하"),
        ("주둥이가 납작한 품종이에요", "단두종 품종"),
        ("잘 모르겠어요", "보호자 확인 불명확"),
        ("해당 없음", ""),
        ("없어요", "없음"),
        ("있어요", "있음"),
        ("보여요", "보임"),
        ("같아요", "것으로 보임"),
        ("해요", "함"),
        ("했어요", "함"),
        ("됐어요", "됨"),
        ("먹어요", "먹음"),
        ("나요", "남"),
        ("않아요", "않음"),
        ("못 쉬어요", "호흡 곤란"),
        ("쉬어요", "쉼"),
        ("중이에요", "중"),
        ("이에요", ""),
        ("예요", ""),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    return text.strip(" ・,")


def _clinical_to_korean(value: str) -> str:
    lower = (value or "").strip().lower()
    if not lower:
        return ""
    for needle, korean in sorted(_CLINICAL_KO_MAP.items(), key=lambda item: len(item[0]), reverse=True):
        if needle in lower:
            return korean
    return value.strip()


def _add_unique(items: list[str], value: str | None) -> None:
    value = (value or "").strip()
    if value and value not in items:
        items.append(value)


def _summarize_answers(answers: list[dict], section: str | None, keywords: list[str] | None = None) -> str:
    """SOAP의 S에 해당하는 '한 줄' 요약.

    주요증상·의심질환은 명사형이므로, 요약은 대비되게 짧은 평서형('~이다') 한 문장으로 만든다.
    """
    label = section_label(section)
    keywords = [kw for kw in (keywords or []) if kw]
    positives: list[str] = []

    for p in answers:
        cleaned = _clean_label(p.get("label", ""))
        if not cleaned:
            continue
        value = str(p.get("value") or "").lower()
        score = p.get("urgency_score") or 0
        if value not in {"unknown", "unsure"} and "불명확" not in cleaned and score > 0:
            _add_unique(positives, cleaned)

    primary = ", ".join(keywords[:2]) if keywords else ", ".join(positives[:2])
    if primary:
        return f"{primary} 양상의 {label}이다."[:80]
    return f"{label} 관련 상담이다."[:80]


def _suspected_from_context(section: str | None, clinical: list[str], answers: list[dict]) -> list[str]:
    suspected: list[str] = []
    values = {str(p.get("value") or "") for p in answers}
    text = " ".join([*clinical, *(str(p.get("label") or "") for p in answers)])

    if section == "GI":
        if "이물 섭취 의심" in clinical or "foreign_body" in values or "fb_over_24h" in values:
            _add_unique(suspected, "이물 섭취")
        if "독성물질 섭취 의심" in clinical or "toxin" in values:
            _add_unique(suspected, "독성물질 섭취")
        if "위확장염전 의심" in clinical or "acute_bloat" in values:
            _add_unique(suspected, "위확장염전")
        if any(token in text for token in ("혈성", "흑변", "melena", "피 섞")):
            _add_unique(suspected, "위장관 출혈")
        if any(token in text for token in ("반복 구토", "멈추지 않고 계속 구토", "persistent")):
            _add_unique(suspected, "급성 위장염")
            _add_unique(suspected, "췌장염")
        if any(token in text for token in ("구토", "설사")):
            _add_unique(suspected, "급성 위장염")

    if section == "RESPIRATORY":
        if any(token in text for token in ("협착음", "천명음", "쌕쌕", "그르렁", "상부기도")):
            _add_unique(suspected, "기관허탈")
            _add_unique(suspected, "상부기도 폐쇄")
        if any(token in text for token in ("기침", "cough")):
            _add_unique(suspected, "기관지염/기관염")
            _add_unique(suspected, "기관허탈")
        if any(token in text for token in ("호흡곤란", "개구호흡", "하부기도")):
            _add_unique(suspected, "폐렴")
            _add_unique(suspected, "흉수/기흉")
        if any(token in text for token in ("폐부종", "심부전")):
            _add_unique(suspected, "심인성 폐부종")

    return suspected


@lru_cache(maxsize=1)
def _node_index() -> dict:
    """node_id → {question dict + section_id} 평탄화 인덱스(initial + sections)."""
    kb = load_triage_kb()
    index: dict[str, dict] = {}

    for q in kb.get("initial_questions", []):
        index[q["id"]] = {**q, "section_id": None}

    for section in kb.get("sections", []):
        sid = section.get("id")
        for q in section.get("questions", []):
            index[q["id"]] = {**q, "section_id": sid}

    return index


@lru_cache(maxsize=1)
def _section_entry_map() -> dict:
    """section_id → 첫 질문 id (예: RESPIRATORY → Q_RESP_01)."""
    kb = load_triage_kb()
    out: dict[str, str] = {}
    for section in kb.get("sections", []):
        qs = section.get("questions", [])
        if qs:
            out[section.get("id")] = qs[0]["id"]
    return out


def get_node(node_id: str) -> dict | None:
    """node_id의 질문 dict(+section_id) 반환."""
    return _node_index().get(node_id)


def section_label(section_id: str | None) -> str:
    """section_id → 한국어 라벨(chief_complaint용)."""
    if not section_id:
        return "증상 상담"
    for section in load_triage_kb().get("sections", []):
        if section.get("id") == section_id:
            return section.get("label", section_id)
    return section_id


def visible_pills(node_id: str, species: str | None = None) -> list[dict]:
    """현재 노드에서 보여줄 pill 목록(종 한정 pill은 종 불일치 시 제외)."""
    node = get_node(node_id)
    if not node:
        return []
    pills = []
    for p in node.get("pills", []):
        sp = p.get("species")
        if sp and species and sp != species:
            continue
        pills.append(p)
    return pills


def pill_labels(node_id: str, species: str | None = None) -> list[str]:
    """quick_replies로 내려줄 pill 라벨 목록."""
    return [p["label"] for p in visible_pills(node_id, species)]


def is_multi(node_id: str) -> bool:
    node = get_node(node_id)
    return bool(node and node.get("type") == "multi")


def match_pill(node_id: str, text: str) -> dict | None:
    """현재 노드 pill 중 라벨이 일치하는 pill 반환(클릭 처리). 없으면 None."""
    norm = _normalize(text)
    if not norm:
        return None
    node = get_node(node_id)
    for p in (node.get("pills", []) if node else []):
        nl = _normalize(p.get("label", ""))
        if nl and (nl == norm or nl in norm or norm in nl):
            return p
    return None


def advance(node_id: str, selected: list[dict]) -> str | None:
    """선택된 pill(들)을 반영해 다음 노드 id를 결정. None이면 종료.

    - Q_INIT_SYMPTOM: 첫 선택 증상의 next_section → 섹션 첫 질문.
    - red_flag pill 선택: 즉시 종료(None).
    - 그 외: pill.next(있으면) → 없으면 question.next → 없으면 종료.
    """
    if not selected:
        return None

    if node_id == START_NODE:
        first = selected[0]
        section = first.get("next_section") or first.get("value")
        return _section_entry_map().get(section)

    if any(p.get("red_flag") for p in selected):
        return None

    node = get_node(node_id) or {}
    for p in selected:
        if p.get("next"):
            return p["next"]
    return node.get("next")


def is_terminal(node_id: str, selected: list[dict]) -> bool:
    """이 선택으로 문진이 종료되는지(다음 노드 없음)."""
    node = get_node(node_id) or {}
    if node.get("is_final"):
        return True
    return advance(node_id, selected) is None


def compute_urgency(answers: list[dict], species: str | None, section: str | None,
                    gender: str | None = None) -> dict:
    """누적 answers로 scoring_engine 규칙에 따라 urgency 산출.

    반환: {urgency, urgency_level_num, urgency_level, total_score, red_flag}
    """
    red_flag = any(p.get("red_flag") for p in answers)

    score = 0
    for p in answers:
        score += p.get("urgency_score") or 0
        score += p.get("urgency_modifier") or 0  # timing pill

    if species == "cat":
        if section in ("RESPIRATORY", "CARDIAC", "UNABLE_TO_WALK"):
            score += 1
        # 중성화 정보 부재 시 보수적으로 수컷을 intact로 간주(+2)
        if section == "UROGENITAL" and gender == "male":
            score += 2

    if red_flag or score >= 10:
        urgency = "RED"
    elif score >= 7:
        urgency = "ORANGE"
    elif score >= 4:
        urgency = "YELLOW"
    else:
        urgency = "GREEN"

    num, label = _URGENCY_MAP[urgency]
    return {
        "urgency": urgency,
        "urgency_level_num": num,
        "urgency_level": label,
        "total_score": score,
        "red_flag": red_flag,
    }


# freeform(off-tree, 예: 피부) 공용 심각도 신호 → 점수.
# 트리에는 pill 점수가 없으므로 주제 무관 일반 신호를 점수화해, 트리와 동일한
# compute_urgency 임계(≥10 RED / ≥7 ORANGE / ≥4 YELLOW)로 통일한다.
# 단일 신호=YELLOW, 두 신호=ORANGE 정도가 되도록 칼리브레이션.
FREEFORM_SIGNAL_SCORES = {
    "systemic_signs": 4,   # 발열·식욕저하·기력저하 등 전신증상 동반
    "rapid_worsening": 4,  # 급격한 악화 / 빠르게 번짐
    "severe_pain": 5,      # 심한 통증
    "active_bleeding": 4,  # 활동성 출혈 / 궤양 / 진물
    "prolonged": 1,        # 수일 이상 지속(타이밍성 가산)
}


def freeform_severity_answers(signals: dict | None) -> list[dict]:
    """freeform 심각도 신호(bool dict) → compute_urgency가 먹는 pseudo-answers.

    신호가 없으면 빈 리스트 → score 0 → GREEN(준긴급). red flag는 상위 단계에서 처리.
    """
    if not isinstance(signals, dict):
        return []
    return [
        {"value": f"freeform:{name}", "urgency_score": score}
        for name, score in FREEFORM_SIGNAL_SCORES.items()
        if signals.get(name)
    ]


def to_collected_info(answers: list[dict], species: str | None, section: str | None,
                      gender: str | None = None) -> dict:
    """walk 결과를 기존 triage collected_info 스키마로 변환."""
    u = compute_urgency(answers, species, section, gender)

    symptom_pills = [p for p in answers if p.get("urgency_score")]
    symptom_pills.sort(key=lambda p: p.get("urgency_score", 0), reverse=True)
    keywords: list[str] = []

    clinical: list[str] = []
    for p in answers:
        for kw in p.get("keywords", []) or []:
            ko = _clinical_to_korean(str(kw))
            _add_unique(clinical, ko)

    for kw in clinical:
        if not any(hint in kw for hint in _DISEASE_HINTS):
            _add_unique(keywords, kw)

    if not keywords:
        for p in symptom_pills:
            value = str(p.get("value") or "").lower()
            cleaned = _clean_label(p.get("label", ""))
            if value in {"unknown", "unsure"} or "불명확" in cleaned:
                continue
            _add_unique(keywords, cleaned)

    keywords = keywords[:4]
    suspected = [kw.replace(" 의심", "") for kw in clinical if any(hint in kw for hint in _DISEASE_HINTS)]
    for disease in _suspected_from_context(section, clinical, answers):
        _add_unique(suspected, disease)
    if not suspected:
        for disease in _SECTION_DEFAULT_DISEASES.get(section or "", []):
            _add_unique(suspected, disease)

    red_flags = [
        p.get("vtl_discriminator_id") or p.get("value")
        for p in answers if p.get("red_flag")
    ]

    label = section_label(section)
    summary = _summarize_answers(answers, section, keywords)
    return {
        "is_triage_complete": True,
        "urgency_level": u["urgency_level"],
        "urgency_level_num": u["urgency_level_num"],
        "vtl_basis": f"decision_tree {section} score={u['total_score']} → {u['urgency']}",
        "red_flags": red_flags,
        "is_initial_visit": True,
        "chief_complaint": label,
        "symptom_keywords": keywords or [label],
        "suspected_diseases": suspected[:3],
        "symptom_summary": summary,
        "recommended_action": "내원 권장",
        "need_followup": u["urgency_level_num"] <= 2,
        "followup_reason": (f"응급도 {u['urgency_level']}" if u["urgency_level_num"] <= 2 else None),
    }
