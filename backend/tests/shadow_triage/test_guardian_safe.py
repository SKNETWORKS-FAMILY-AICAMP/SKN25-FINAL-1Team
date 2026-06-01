"""Shadow Triage 회귀 테스트 — OpenAI 호출 없음.

보호자 프론트엔드로는 진단성 정보(응급도 라벨·red_flags·추측질환·VTL 근거 등)가
절대 새어나가면 안 된다. _guardian_safe_triage()가 안전 필드만 통과시키는지 고정한다.
이 테스트가 깨지면 = 보호자에게 진단정보가 노출되는 사고이므로 반드시 빨갛게 떠야 한다.
"""
import sys
from pathlib import Path

# app(backend 루트)과 ai(레포 루트) 둘 다 import 가능하도록 경로 추가.
# chat.py가 'from ai.tasks ...'를 사용하므로 레포 루트도 필요하다.
sys.path.insert(0, str(Path(__file__).parents[2]))  # backend/
sys.path.insert(0, str(Path(__file__).parents[3]))  # repo root (ai 패키지)

from app.api.chat import _guardian_safe_triage, _GUARDIAN_SAFE_FIELDS

# 절대 보호자에게 내려가면 안 되는 진단성 필드들
FORBIDDEN_FIELDS = (
    "urgency_level",
    "vtl_basis",
    "red_flags",
    "chief_complaint",
    "symptom_onset",
    "suspected_diseases",
    "symptom_summary",
    "recommended_action",
)


def _full_triage_payload() -> dict:
    """triage 에이전트가 생성하는 전체 collected_info(진단정보 포함)."""
    return {
        "is_triage_complete": True,
        "urgency_level_num": 2,
        "need_followup": True,
        "symptom_keywords": ["경련", "쓰러짐"],
        # --- 이하 진단성 필드 (보호자 차단 대상) ---
        "urgency_level": "응급",
        "vtl_basis": "의식저하 + 발작 지속",
        "red_flags": ["지속 발작", "청색증"],
        "chief_complaint": "갑작스러운 경련",
        "symptom_onset": "10분 전",
        "suspected_diseases": ["뇌전증", "저혈당"],
        "symptom_summary": "10분 전 발작 시작, 의식 저하 동반",
        "recommended_action": "즉시 내원",
        "need_photo": False,
    }


def test_diagnostic_fields_are_stripped():
    """진단성 필드가 결과에서 모두 제거된다."""
    safe = _guardian_safe_triage(_full_triage_payload())
    for field in FORBIDDEN_FIELDS:
        assert field not in safe, f"진단성 필드 '{field}'가 보호자 payload에 노출됨!"


def test_safe_fields_are_preserved():
    """예약 흐름 제어에 필요한 안전 필드는 유지된다."""
    safe = _guardian_safe_triage(_full_triage_payload())
    assert safe["is_triage_complete"] is True
    assert safe["urgency_level_num"] == 2
    assert safe["need_followup"] is True
    assert safe["symptom_keywords"] == ["경련", "쓰러짐"]


def test_output_keys_subset_of_allowlist():
    """출력 키는 화이트리스트 부분집합이어야 한다 (새 필드 유출 방지)."""
    safe = _guardian_safe_triage(_full_triage_payload())
    assert set(safe.keys()).issubset(set(_GUARDIAN_SAFE_FIELDS))


def test_none_and_non_dict_passthrough():
    """None/비-dict 입력은 그대로 통과(방어적)."""
    assert _guardian_safe_triage(None) is None
    assert _guardian_safe_triage("not a dict") == "not a dict"


def test_missing_fields_do_not_raise():
    """일부 안전 필드가 없어도 KeyError 없이 동작한다."""
    partial = {"is_triage_complete": False}
    safe = _guardian_safe_triage(partial)
    assert safe == {"is_triage_complete": False}
