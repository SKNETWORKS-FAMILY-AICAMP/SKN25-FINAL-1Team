"""문진 에이전트 (오케스트레이터 진입).  담당: 리드

디스크리미네이터 + 2-콜 구조:
 1) (이미지 있으면) vision 분석 → 추출 콜에 줄 근거 note
 2) 추출 콜(LLM): 대화·이미지 → variables(사실값) + 충분여부 판단 (사용자 비노출)
 3) 엔진: variables → 디스크리미네이터 매칭 → 등급(결정론)
 4) 종료 판단: 최소 2턴 + (충분 or 등급확정), red여도 즉시종료 X, 최대 5턴
 5) 진행 시 질문 콜(LLM): 트리 안 보고 자연스럽게 한 질문
 6) 완료 시: triage_resultDB 적재 + emrid 발급 + triage_complete 이벤트

설계: prompts.py(질문/추출), engine.py(디스크리미네이터), vision.py(CNN+VLM).
"""
from __future__ import annotations

import logging

from ai.llm import call_llm_json
from ai.orchestrator.contracts import AgentResult, SessionContext

from . import engine, vision
from .prompts import build_extraction_prompt, build_question_prompt

logger = logging.getLogger(__name__)

# 종료 정책:
#  - RED(생명위협): 놀라게 끌지 않되 즉시 종료도 아님 → 한두 턴(차트 보강용 1턴 더) 안에 마무리.
#  - 그 외(ORANGE/YELLOW/GREEN): LLM이 '심각도 가를 정보를 충분히 봤다'고 판단할 때까지 묻되 최대 5턴.
#    (잎 하나 매칭됐다고 바로 끝내지 않음 — GREEN은 '안 급함'이 아니라 '아직 못 찾음'일 수 있어서.)
RED_MAX_TURNS = 2      # red flag면 이 턴수 내 종료
NONRED_MIN_TURNS = 3   # 비-RED는 이 턴 전엔 '충분' 판단을 받아들이지 않음
MAX_TURNS = 5          # 최대 턴


def _history_before_current(ctx: SessionContext) -> list[dict]:
    """ctx.history 마지막이 이번 발화와 같으면 중복 제거."""
    h = ctx.history or []
    if h and h[-1].get("role") == "user" and h[-1].get("content") == ctx.user_message:
        return h[:-1]
    return h


class TriageAgent:
    name = "triage"
    description = "증상 문진 + 응급도 판정. 질문은 LLM이 자연스럽게(트리 비노출), 판정은 디스크리미네이터로 결정론."

    async def run(self, ctx: SessionContext, args: dict) -> AgentResult:
        state = dict(ctx.triage_state or {})
        extracted = dict(state.get("extracted") or {})
        turn_count = int(state.get("turn_count", 0))
        prev_section = state.get("section")
        pet_name = (ctx.pet_info or {}).get("name") or "아이"
        history = _history_before_current(ctx)

        # 1) 이미지 분석(있으면) — fail-open
        vis = None
        if ctx.attachments:
            try:
                vis = await vision.analyze(ctx.attachments, ctx.user_message, prev_section)
            except Exception as e:
                logger.warning("[triage] vision 분석 실패: %s", e)
        vision_note = (vis or {}).get("note", "")
        vision_evidence = (vis or {}).get("evidence") or state.get("vision_evidence")

        # 2) 추출 콜
        try:
            out = await call_llm_json(
                build_extraction_prompt(history, ctx.user_message, prev_section, extracted, vision_note)
            )
        except Exception as e:
            logger.warning("[triage] 추출 콜 실패: %s", e)
            out = {}

        section = out.get("section") or prev_section or "GENERAL"
        new_vars = {k: v for k, v in (out.get("variables") or {}).items() if v}
        bucket = dict(extracted.get(section) or {})
        bucket.update(new_vars)
        extracted[section] = bucket

        # 3) 디스크리미네이터 매칭
        matched = engine.match(extracted)
        urgency = engine.top_urgency(matched)

        # 4) 종료 판단
        turn_count += 1
        enough = bool(out.get("enough_to_triage"))
        has_red = bool(engine.red_flag_labels(matched))
        if has_red:
            # 생명위협: 짧게(한두 턴). 즉시 종료는 아님 — 첫 턴이면 한 번 더 받고 종료.
            terminate = turn_count >= RED_MAX_TURNS
        else:
            # 그 외: 잎 매칭만으론 종료 안 함. LLM이 '충분' 판단할 때까지 묻되 최대 5턴.
            terminate = (turn_count >= NONRED_MIN_TURNS and enough) or turn_count >= MAX_TURNS

        state.update({"extracted": extracted, "section": section,
                      "turn_count": turn_count, "vision_evidence": vision_evidence})

        if not terminate:
            # 5) 질문 콜 (트리 비노출)
            try:
                q = await call_llm_json(
                    build_question_prompt(pet_name, history, ctx.user_message, section),
                    temperature=0.6,   # 질문은 따뜻하고 자연스럽게(추출은 0 결정론)
                )
            except Exception:
                q = {}
            return AgentResult(
                reply=q.get("reply") or "조금 더 자세히 알려주시겠어요?",
                quick_replies=q.get("quick_replies") or [],
                state_patch={"triage_state": state, "active_flow": "triaging"},
            )

        # 6) 완료 → 판정 확정 + 적재
        urgency = urgency or "GREEN"
        suspected = list(dict.fromkeys(
            (out.get("suspected") or []) + ((vis or {}).get("suspected") or [])
        ))
        vtl_basis = engine.build_vtl_basis(
            matched, urgency, evidence=vision_note, reason=out.get("summary") or "",
        )

        emrid = ctx.emrid
        if ctx.db is not None and ctx.session is not None:
            try:
                from app.crud.chat import create_triage_guardian, update_session_emrid
                from app.crud.triage import build_triage_result

                if emrid is None:
                    guardian = await create_triage_guardian(ctx.db, ctx.petid)
                    emrid = guardian.emrid
                    await update_session_emrid(ctx.db, ctx.session, emrid)
                info = {
                    "urgency_level": urgency,
                    "urgency_level_num": engine.urgency_num(urgency),
                    "vtl_basis": vtl_basis,
                    "red_flags": engine.red_flag_labels(matched),
                    "chief_complaint": out.get("chief_complaint"),
                    "symptom_keywords": out.get("keywords") or [],
                    "suspected_diseases": suspected,
                    "symptom_summary": out.get("summary") or "",
                    "symptom_onset": out.get("onset"),
                    "recommended_action": engine.recommended_action(urgency),
                    "matched_discriminators": matched,
                    "extracted_variables": extracted,
                    "vision_evidence": vision_evidence,
                }
                ctx.db.add(build_triage_result(emrid, info))
                await ctx.db.commit()
            except Exception as e:
                logger.warning("[triage] triage_result 적재 실패: %s", e)
                try:
                    await ctx.db.rollback()
                except Exception:
                    pass

        return AgentResult(
            reply="말씀 잘 들었어요. 아래에서 예약을 도와드릴게요.",
            quick_replies=[],
            state_patch={"triage_state": {}, "active_flow": "idle"},
            events=[{"type": "triage_complete", "emrid": emrid, "data": {
                "is_triage_complete": True,
                "urgency": urgency,
                "chief_complaints": [out.get("chief_complaint")] if out.get("chief_complaint") else [],
                "suspected_conditions": suspected,
                "symptom_keywords": out.get("keywords") or [],
                "triage_summary": out.get("summary"),
            }}],
        )


triage = TriageAgent()
