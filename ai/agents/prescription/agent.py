"""처방전(Prescription) 에이전트 — 담당 리드. 상세: AGENT_SPECS §7.

★ 챗봇 오케스트레이터와 무관한 별도 트랙. 수의사 EMR 페이지 보조 기능.
현재 진단 + 과거 병력(emr_history)을 읽고 약을 추천. 사람(수의사)이 수정 가능(차트처럼 보조).
"""
from __future__ import annotations


class PrescriptionAgent:
    """수의사 EMR 처방 보조. SessionContext/AgentResult 안 씀(챗봇 흐름 밖)."""

    async def suggest(self, emrid: int, patient_context: dict) -> dict:
        # TODO(리드): AGENT_SPECS §7
        #  - 입력: 현재 진단/차트(reportDB) + 과거 병력(emr_history)
        #  - 출력: 약물 추천 목록 + 근거 → 수의사가 검토·수정
        #  - 안전장치: 단정 금지, "보조 추천" 명시, 사람 승인 전제
        raise NotImplementedError("처방 추천 구현 필요 (AGENT_SPECS §7)")
