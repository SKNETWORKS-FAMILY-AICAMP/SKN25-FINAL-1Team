"""문진 에이전트 (오케스트레이터 진입).  담당: 리드

디스크리미네이터 + 2-콜 + 예약-확인 플로우:
 1) (이미지 있으면) vision 분석 → 추출 콜에 줄 근거 note
 2) 추출 콜(LLM): 대화·이미지 → variables(사실값) + 충분여부 판단 (사용자 비노출)
 3) 엔진: variables → 디스크리미네이터 매칭 → 등급(결정론)
 4) 종료 판단: RED는 1~2턴, 그 외는 LLM '충분' 판단(최대 5턴)
 5) 진행 시 질문 콜(LLM): 트리 안 보고 자연스럽게 한 질문
 6) 완료 시: triage_result 저장(+RAG 유사사례) → 의심질환 안내 + "예약 도와드릴까요?"(예/아니오)
 7) 확인: 예 → triage_complete 발사(예약창) / 아니오 → 착하게 마무리(기록은 남음)
 8) 재예약: 기록 있으면 재문진 없이 바로 예약 재개

설계: prompts.py(질문/추출/확인), engine.py(디스크리미네이터), vision.py(CNN+VLM), ai.rag(유사사례).
"""
from __future__ import annotations

import logging

from ai.llm import call_llm, call_llm_json
from ai.orchestrator.contracts import AgentResult, Flow, SessionContext

from . import engine, vision
from .prompts import (
    build_confirm_prompt,
    build_extraction_prompt,
    build_question_prompt,
    build_suspected_confirm_message,
    build_suspected_confirm_prompt,
)

logger = logging.getLogger(__name__)

# 종료 정책: RED는 짧게(1~2턴), 그 외는 LLM '충분' 판단까지(최대 5턴).
RED_MAX_TURNS = 2
NONRED_MIN_TURNS = 3
MAX_TURNS = 5

_YES_KW = ("예", "네", "넹", "응", "어", "그래", "좋아", "해줘", "부탁", "ㅇㅇ", "할게", "진행", "당연")
_NO_KW = ("아니", "아뇨", "싫", "안 할", "안할", "나중", "괜찮", "ㄴㄴ", "노")


def _history_before_current(ctx: SessionContext) -> list[dict]:
    h = ctx.history or []
    if h and h[-1].get("role") == "user" and h[-1].get("content") == ctx.user_message:
        return h[:-1]
    return h


def _keyword_yesno(text: str) -> str:
    t = text or ""
    if any(k in t for k in _NO_KW):
        return "no"
    if any(k in t for k in _YES_KW):
        return "yes"
    return "unclear"


async def _run_rag(db, query: str) -> tuple[list, list]:
    """RAG 유사사례 검색 → (rag_context[dict], 진짜 병명[str]). fail-open.

    쿼리는 '보호자가 실제로 보낸 말'을 쓴다 — RAG 문서(input_text)가 보호자 서술형이라
    같은 스타일로 검색해야 유사도가 잘 나온다. disease가 '기타'인 건 병명 후보에서 제외.
    """
    try:
        from ai.rag import RAG_USABLE_THRESHOLD, search_similar_triage_cases
        q = (query or "").strip()
        if not q:
            return [], []
        matches = await search_similar_triage_cases(db, q, top_k=3)
        usable = [m for m in matches if m.similarity >= RAG_USABLE_THRESHOLD]
        diseases = [m.disease for m in usable if m.disease and m.disease != "기타"]
        return [m.to_dict() for m in usable], diseases
    except Exception as e:
        logger.warning("[triage] RAG 검색 실패: %s", e)
        return [], []


class TriageAgent:
    name = "triage"
    description = "증상 문진 + 응급도 판정. 질문은 LLM이 자연스럽게(트리 비노출), 판정은 디스크리미네이터로 결정론."

    async def run(self, ctx: SessionContext, args: dict) -> AgentResult:
        # 모드 분기
        if ctx.active_flow == Flow.AWAITING_BOOKING_CONFIRM:
            return await self._confirm(ctx)
        if ctx.emrid is not None and ctx.active_flow != Flow.TRIAGING:
            return await self._rebook(ctx)        # 문진 완료 후 '다시 예약'
        return await self._triage_turn(ctx)

    # ── 일반 문진 턴 ──────────────────────────────────────────────
    async def _triage_turn(self, ctx: SessionContext) -> AgentResult:
        state = dict(ctx.triage_state or {})
        extracted = dict(state.get("extracted") or {})
        turn_count = int(state.get("turn_count", 0))
        prev_section = state.get("section")
        pet_name = (ctx.pet_info or {}).get("name") or "아이"
        history = _history_before_current(ctx)

        # 1) 이미지 분석(있으면)
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
            terminate = turn_count >= RED_MAX_TURNS
        else:
            terminate = (turn_count >= NONRED_MIN_TURNS and enough) or turn_count >= MAX_TURNS

        state.update({"extracted": extracted, "section": section,
                      "turn_count": turn_count, "vision_evidence": vision_evidence})

        if not terminate:
            # 5) 질문 콜 (트리 비노출, 따뜻하게)
            try:
                q = await call_llm_json(
                    build_question_prompt(pet_name, history, ctx.user_message, section),
                    temperature=0.6,
                )
            except Exception:
                q = {}
            return AgentResult(
                reply=q.get("reply") or "조금 더 자세히 알려주시겠어요?",
                quick_replies=q.get("quick_replies") or [],
                state_patch={"triage_state": state, "active_flow": "triaging"},
            )

        # 6) 완료 → 판정 확정 + RAG + 적재 (단, 예약창은 '예' 확인 후)
        urgency = urgency or "GREEN"
        # RAG 쿼리 = 보호자가 실제로 보낸 말(문서가 보호자 서술형 → 스타일 일치로 매칭↑)
        user_msgs = [m.get("content", "") for m in (ctx.history or [])
                     if isinstance(m, dict) and m.get("role") == "user" and m.get("content")]
        rag_query = " ".join(user_msgs[-6:]).strip() or (out.get("summary") or "")
        rag_context, rag_diseases = await _run_rag(ctx.db, rag_query)
        # 의심질환 이름 = LLM(신뢰도 높음) + RAG 진짜 병명(있으면). RAG disease '기타'는 이미 제외됨.
        llm_suspected = list(dict.fromkeys(
            (out.get("suspected") or []) + ((vis or {}).get("suspected") or [])
        ))
        suspected = list(dict.fromkeys(llm_suspected + rag_diseases))
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
                    "rag_context": rag_context,
                }
                ctx.db.add(build_triage_result(emrid, info))
                await ctx.db.commit()
            except Exception as e:
                logger.warning("[triage] triage_result 적재 실패: %s", e)
                try:
                    await ctx.db.rollback()
                except Exception:
                    pass

        # 완료 이벤트는 '예' 확인 후 발사하므로 여기선 보류 → state에 저장
        complete_payload = {
            "emrid": emrid,
            "data": {
                "is_triage_complete": True,
                "urgency": urgency,
                "chief_complaints": [out.get("chief_complaint")] if out.get("chief_complaint") else [],
                "suspected_conditions": suspected,
                "symptom_keywords": out.get("keywords") or [],
                "triage_summary": out.get("summary"),
            },
        }
        # 안내 멘트는 LLM 생성(자연스럽게). 실패 시 템플릿 폴백.
        snippets = [(c.get("output_text") or "")[:200] for c in (rag_context or [])[:2]]
        try:
            reply = (await call_llm(
                build_suspected_confirm_prompt(pet_name, suspected, snippets),
                temperature=0.6,
            ) or "").strip()
        except Exception:
            reply = ""
        if not reply:
            reply = build_suspected_confirm_message(pet_name, suspected)

        return AgentResult(
            reply=reply,
            quick_replies=["예", "아니오"],
            state_patch={
                "triage_state": {"last_complete": complete_payload},
                "active_flow": "awaiting_booking_confirm",
            },
        )

    # ── 예약 확인(예/아니오) ──────────────────────────────────────
    async def _confirm(self, ctx: SessionContext) -> AgentResult:
        state = dict(ctx.triage_state or {})
        try:
            ans = (await call_llm_json(build_confirm_prompt(ctx.user_message))).get("answer")
        except Exception:
            ans = _keyword_yesno(ctx.user_message)
        if ans not in ("yes", "no"):
            ans = _keyword_yesno(ctx.user_message)

        if ans == "yes":
            return self._emit_booking(state, "네! 예약을 도와드릴게요. 아래에서 시간을 골라주세요. 🐾")
        if ans == "no":
            return AgentResult(
                reply="알겠습니다. 추가로 궁금한 점이 있거나 예약을 원하시면 언제든 편하게 말씀해 주세요. 🐾",
                state_patch={"active_flow": "idle", "triage_state": state},  # last_complete 유지(재예약용)
            )
        return AgentResult(
            reply="예약을 도와드릴까요? '예' 또는 '아니오'로 알려주세요.",
            quick_replies=["예", "아니오"],
            state_patch={"active_flow": "awaiting_booking_confirm", "triage_state": state},
        )

    # ── 재예약(문진 완료 후 '다시 예약') ──────────────────────────
    async def _rebook(self, ctx: SessionContext) -> AgentResult:
        state = dict(ctx.triage_state or {})
        if not state.get("last_complete"):
            payload = await self._payload_from_db(ctx)
            if payload:
                state["last_complete"] = payload
        if state.get("last_complete"):
            return self._emit_booking(state, "네, 예약을 다시 도와드릴게요. 아래에서 시간을 골라주세요. 🐾")
        return AgentResult(reply="예약을 도와드릴게요. 잠시만 기다려 주세요!")

    def _emit_booking(self, state: dict, reply: str) -> AgentResult:
        payload = state.get("last_complete") or {}
        return AgentResult(
            reply=reply,
            state_patch={"active_flow": "idle", "triage_state": state},  # last_complete 유지
            events=[{"type": "triage_complete", "emrid": payload.get("emrid"),
                     "data": payload.get("data") or {}}],
        )

    async def _payload_from_db(self, ctx: SessionContext) -> dict | None:
        if ctx.db is None or ctx.emrid is None:
            return None
        try:
            from sqlalchemy import select

            from app.models.triage_result import TriageResult
            tr = (await ctx.db.execute(
                select(TriageResult).where(TriageResult.emrid == ctx.emrid)
            )).scalars().first()
            if not tr:
                return None
            return {"emrid": ctx.emrid, "data": {
                "is_triage_complete": True,
                "urgency": tr.urgency_level,
                "chief_complaints": [tr.chief_complaint] if tr.chief_complaint else [],
                "suspected_conditions": tr.suspected_diseases or [],
                "symptom_keywords": tr.symptom_keywords or [],
                "triage_summary": tr.symptom_summary,
            }}
        except Exception:
            return None


triage = TriageAgent()
