"""문진 노드 (오케스트레이터용).  담당: 리드

방식 (설계 D7):
 - LLM이 '알아서' 자연스럽게 질문 생성 (JSON 항목은 참고 예시일 뿐, 그대로/순서대로 X)
 - 점수는 코드가 결정론으로 (engine.py = vet_triage.json 점수표). LLM이 urgency 안 정함.
 - 종료: done(LLM 판단) OR 문진 5턴 / red_flag면 한 질문만 더 받고 종료(차트 보강용)
 - red_flag(생명위협)는 '속으로만' 기록 — 사용자에겐 응급이라 알리지 않음
 - 완료 시: triage_complete 이벤트로 프론트 '예약 창'이 열림 (챗봇 pill 안 띄움)
"""
from __future__ import annotations

from ai.llm import call_llm_json
from ai.orchestrator.contracts import AgentResult, SessionContext

from . import engine

MAX_TURNS = 5  # 문진 질문 최대 턴

_PROMPT = """너는 동물병원 문진 도우미야. 보호자와 진짜 사람처럼 따뜻하고 자연스럽게 대화하며 증상을 파악해.

[아주 중요한 규칙]
- 질문은 네가 대화 맥락을 보고 '알아서' 자연스럽게 만들어. 아래 항목 목록은 '참고용 예시'일 뿐,
  그대로 읽거나 정해진 순서로 묻지 마.
- 한 번에 하나만, 공감 한마디 곁들여 쉬운 말로.
- 절대 '응급'·'응급실'·'위험'·'큰일' 같은 말로 겁주지 마. 늘 침착하고 따뜻하게.
- 생명에 위협이 될 신호(지금 발작 중, 숨 못 쉼, 의식 없음, 대량 출혈 등)면 red_flag=true 로 표시
  (단, 사용자에게는 응급이라고 말하지 말 것).
- 증상이 충분히 파악됐다 싶으면 done=true 로 마무리해.

[참고용 증상 항목 예시 — 점수 계산에 쓰이니, 대화 중 파악되면 fields에 enum 값으로 담아줘(모르면 비움)]
{reference}

JSON으로만 답해:
{{"section":"RESPIRATORY", "fields":{{"breathing_difficulty":"moderate"}}, "red_flag":false, "done":false,
  "reply":"자연스러운 다음 질문(또는 done이면 마무리 인사)", "quick_replies":["보기1","보기2"],
  "chief_complaint":"주증상(명사, done일 때)", "keywords":["키워드"], "suspected":["의심질환"], "summary":"한 줄 평서형 요약"}}"""


class TriageNode:
    name = "triage"
    description = "증상 문진 + 응급도 판정. 질문은 LLM이 자연스럽게, 점수는 점수표로 결정론."

    async def run(self, ctx: SessionContext, args: dict) -> AgentResult:
        state = dict(ctx.triage_state or {})
        prev_fields = dict(state.get("fields") or {})

        recent = ctx.history[-8:] if ctx.history else []
        convo = "\n".join(f"{m.get('role')}: {m.get('content')}" for m in recent)
        prompt = (
            _PROMPT.format(reference=engine.section_reference())
            + f"\n\n[반려동물] {ctx.pet_info}\n[지금까지 대화]\n{convo}\n[이번 발화] {ctx.user_message}\n"
            + f"[지금까지 모은 슬롯] {prev_fields}\n"
        )
        try:
            out = await call_llm_json(prompt)
        except Exception:
            return AgentResult(
                reply="증상을 조금 더 자세히 알려주시겠어요?",
                state_patch={"triage_state": state, "active_flow": "triaging"},
            )

        section = out.get("section") or state.get("section") or "GENERAL"
        merged = {**prev_fields, **{k: v for k, v in (out.get("fields") or {}).items() if v}}
        red_flag = bool(out.get("red_flag")) or bool(state.get("red_flag"))
        rf_followup = int(state.get("red_flag_followup", 0))
        turn_count = int(state.get("turn_count", 0))

        # 결정론 채점 (LLM 아님) — 속으로만 기록, 사용자엔 노출 안 함
        total = engine.score(section, merged)
        urgency = engine.urgency(section, total, red_flag)

        # 종료 판단
        if red_flag:
            terminate = rf_followup >= 1            # red_flag면 딱 한 질문 더 받고 종료
        else:
            terminate = bool(out.get("done")) or (turn_count >= MAX_TURNS)

        if not terminate:
            state.update({
                "section": section, "fields": merged,
                "turn_count": turn_count + 1, "red_flag": red_flag,
                "red_flag_followup": rf_followup + (1 if red_flag else 0),
            })
            return AgentResult(
                reply=out.get("reply") or "증상을 조금 더 알려주세요.",
                quick_replies=out.get("quick_replies") or [],
                state_patch={"triage_state": state, "active_flow": "triaging"},
            )

        # ── 완료 → triage_resultDB 적재 + emrid 발급 ──
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
                    "chief_complaint": out.get("chief_complaint"),
                    "symptom_keywords": out.get("keywords") or [],
                    "suspected_diseases": out.get("suspected") or [],
                    "symptom_summary": out.get("summary") or "",
                    "symptom_onset": merged.get("onset"),   # 차트가 읽음
                    "red_flags": ["red_flag"] if red_flag else [],
                }
                ctx.db.add(build_triage_result(emrid, info))
                await ctx.db.commit()
            except Exception:
                await ctx.db.rollback()

        # 사용자에게 보일 마무리 — 응급 표현 없이 침착하게. pill 없음(예약 창은 프론트가 염).
        reply = out.get("reply") if out.get("done") else "말씀 잘 들었어요. 아래에서 예약을 도와드릴게요."

        return AgentResult(
            reply=reply,
            quick_replies=[],                         # '예약 시간 보기' 같은 pill 안 띄움
            state_patch={"triage_state": {}, "active_flow": "idle"},
            events=[{"type": "triage_complete", "emrid": emrid, "data": {
                "is_triage_complete": True,
                "urgency": urgency,                   # 프론트 예약 창이 쓰는 값(배지·슬롯)
                "chief_complaints": [out.get("chief_complaint")] if out.get("chief_complaint") else [],
                "suspected_conditions": out.get("suspected") or [],
                "symptom_keywords": out.get("keywords") or [],
                "triage_summary": out.get("summary"),
            }}],
        )


triage = TriageNode()
