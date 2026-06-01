"""Triage 결과 영속화 공용 헬퍼.

triage_result 적재 로직이 chat.py(메인 챗봇 흐름)와 ai/tasks.py(/api/agent/run 경로)
양쪽에 중복돼 있어 필드 추가 시 한쪽만 고치면 데이터가 어긋날 위험이 있었다.
이 빌더 하나로 매핑을 단일화한다. 세션/commit은 호출부가 각자 제어한다.
"""
from __future__ import annotations

from app.models.triage_result import TriageResult


def build_triage_result(emrid: int, info: dict) -> TriageResult:
    """triage collected_info(dict)를 TriageResult ORM 객체로 변환한다.

    호출부에서 ``db.add(build_triage_result(emrid, info))`` 후 commit 한다.
    """
    return TriageResult(
        emrid=emrid,
        urgency_level=info.get("urgency_level", ""),
        urgency_level_num=int(info.get("urgency_level_num", 3)),
        vtl_basis=info.get("vtl_basis"),
        red_flags=info.get("red_flags"),
        chief_complaint=info.get("chief_complaint"),
        symptom_onset=info.get("symptom_onset"),
        symptom_keywords=info.get("symptom_keywords"),
        suspected_diseases=info.get("suspected_diseases"),
        symptom_summary=info.get("symptom_summary"),
        recommended_action=info.get("recommended_action"),
        need_photo=info.get("need_photo", False),
    )
