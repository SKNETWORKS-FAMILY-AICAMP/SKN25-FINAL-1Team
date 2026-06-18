"""문진 노드 (오케스트레이터용 프로토타입).  담당: 리드

오케스트레이터가 부르는 문진 진입점. 매 턴 LLM이 (질문 더 할지 / 끝낼지)를 판단하고,
끝나면 triage_resultDB에 적재 + emrid 발급한다.
※ 프로토타입: 응급도도 LLM이 판정(나중에 결정론 점수표로 단단하게 — AGENT_SPECS §2).
※ 실제 문진 로직을 새로 쓰면 이 파일의 run()만 그쪽을 부르게 바꾸면 됨.
"""
from __future__ import annotations

from ai.llm import call_llm_json
from ai.orchestrator.contracts import AgentResult, Intent, SessionContext

# 프로토타입 프롬프트 (다듬으면 prompts.py 로 옮기기)
TRIAGE_PROMPT = """너는 동물병원 문진 도우미야. 보호자와 자연스럽고 다정하게 대화하며 증상을 파악해.
지금까지 모은 정보와 이번 발화를 보고, 더 물어볼지 / 충분한지 판단해.
- 더 물어볼 게 있으면 한 번에 한 가지만, 따뜻한 존댓말로 질문(버튼 보기 2~4개).
- 충분하면 끝내고 응급도를 정해(RED/ORANGE/YELLOW/GREEN).
JSON으로만 답해:
{"done": false,
 "reply": "다음 질문(또는 완료 인사)",
 "quick_replies": ["보기1","보기2"],
 "urgency": "GREEN", "urgency_num": 4,
 "chief_complaint": "주증상(명사)",
 "keywords": ["증상키워드"],
 "suspected": ["의심질환"],
 "summary": "한 줄 평서형 요약(~이다)",
 "onset": "증상 시작(예: 어제부터)",
 "red_flags": []}
"""


class TriageNode:
    name = "triage"
    description = "증상 문진 + 응급도 판정. 질문은 자연스럽게."

    async def run(self, ctx: SessionContext, args: dict) -> AgentResult:
        state = dict(ctx.triage_state or {})
        recent = ctx.history[-8:] if ctx.history else []
        convo = "\n".join(f"{m.get('role')}: {m.get('content')}" for m in recent)
        prompt = (
            f"{TRIAGE_PROMPT}\n\n[반려동물] {ctx.pet_info}\n"
            f"[지금까지 대화]\n{convo}\n[이번 발화] {ctx.user_message}\n"
        )
        try:
            out = await call_llm_json(prompt)
        except Exception:
            return AgentResult(
                reply="증상을 조금 더 자세히 알려주시겠어요?",
                state_patch={"active_flow": "triaging"},
            )

        state["turn_count"] = int(state.get("turn_count", 0)) + 1

        # 아직 문진 진행 중
        if not out.get("done"):
            return AgentResult(
                reply=out.get("reply") or "증상을 조금 더 알려주세요.",
                quick_replies=out.get("quick_replies") or [],
                state_patch={"triage_state": state, "active_flow": "triaging"},
            )

        # 문진 완료 → triage_resultDB 적재 + emrid 발급
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
                    "urgency_level": out.get("urgency", "GREEN"),
                    "urgency_level_num": out.get("urgency_num", 4),
                    "chief_complaint": out.get("chief_complaint"),
                    "symptom_keywords": out.get("keywords") or [],
                    "suspected_diseases": out.get("suspected") or [],
                    "symptom_summary": out.get("summary") or "",
                    "symptom_onset": out.get("onset"),        # ★ 차트가 읽음
                    "red_flags": out.get("red_flags") or [],  # ★ 차트가 읽음
                }
                ctx.db.add(build_triage_result(emrid, info))
                await ctx.db.commit()
            except Exception:
                await ctx.db.rollback()

        return AgentResult(
            reply=out.get("reply") or "증상 정리했어요. 가까운 예약 시간을 잡아드릴까요?",
            quick_replies=["예약 시간 보기"],
            state_patch={"triage_state": {}, "active_flow": "scheduling"},
            events=[{"type": "triage_complete", "emrid": emrid, "data": {
                "is_triage_complete": True,
                "urgency": out.get("urgency"),
                "chief_complaints": [out.get("chief_complaint")] if out.get("chief_complaint") else [],
                "suspected_conditions": out.get("suspected") or [],
                "symptom_keywords": out.get("keywords") or [],
                "triage_summary": out.get("summary"),
            }}],
            handoff=Intent.SCHEDULE,
        )


triage = TriageNode()
