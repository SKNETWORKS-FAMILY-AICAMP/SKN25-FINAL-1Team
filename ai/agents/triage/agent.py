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

from langfuse import observe

import logging
import re

from ai.llm import call_llm_json
from ai.orchestrator.contracts import (
    INITIAL_SYMPTOM_PILLS,
    INITIAL_TRIAGE_PILL,
    AgentResult,
    Flow,
    SessionContext,
)

from . import engine, vision
from .prompts import (
    build_confirm_prompt,
    build_extraction_prompt,
    build_question_prompt,
    build_redirect_reply_prompt,
    build_suspected_confirm_message,
    build_suspected_confirm_prompt,
)

logger = logging.getLogger(__name__)

# 종료 정책 — urgency_tier(LLM 임상 판단)로 문진 길이 제어
#  critical: 생명위협 → 최대 2턴 / high: 빨리 봐야 → 최대 3턴 / normal: 최대 5턴(충분하면 조기).
CRITICAL_MAX_TURNS = 2
HIGH_MAX_TURNS = 3
NORMAL_MIN_TURNS = 3
NORMAL_MAX_TURNS = 5

_YES_KW = ("예", "네", "넹", "응", "어", "그래", "좋아", "해줘", "부탁", "ㅇㅇ", "할게", "진행", "당연")
_NO_KW = ("아니", "아뇨", "싫", "안 할", "안할", "나중", "괜찮", "ㄴㄴ", "노")


def _pet_call(name: str | None) -> str:
    """반려동물 호칭 — 받침 있는 이름엔 친근형 '이'를 붙인다(군밤 → 군밤이가, 뽀미 → 뽀미가)."""
    n = (name or "아이").strip()
    ch = n[-1:]
    if "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28:
        return n + "이"
    return n

# 문진 전 '바로 예약' 차단 안내 — 증상 먼저 / 그래도 바로 예약은 홈 탭으로.
_BOOKING_BLOCKED_REPLY = (
    "{pet}가 어디가 불편한지 먼저 알려주시면 제가 살펴보고 예약까지 도와드릴게요. 🐾\n\n"
    "증상 없이 바로 예약만 원하시면 홈 화면의 '예약하기'를 이용해 주세요."
)


def _history_before_current(ctx: SessionContext) -> list[dict]:
    h = ctx.history or []
    if h and h[-1].get("role") == "user" and h[-1].get("content") == ctx.user_message:
        return h[:-1]
    return h


def _push_status(ctx: SessionContext, phase: str) -> None:
    """진행 상태(image_analysis/generating/searching)를 SSE로 흘려보낸다(있으면)."""
    if ctx.status_queue is not None:
        try:
            ctx.status_queue.put_nowait({"type": "status", "phase": phase})
        except Exception:
            pass


def _format_confirm_reply(text: str) -> str:
    """완료 안내 멘트 가독성 — '예약을 도와드릴까요?'를 항상 빈 줄 뒤로 보낸다(LLM이 안 나눠도)."""
    t = re.sub(
        r"원하시면\s*(?:\n+\s*)+(예약을 도와드릴까요\??)",
        r"원하시면 \1",
        (text or "").strip(),
    )
    idx = t.rfind("예약을 도와드릴까요")
    if idx > 0:
        return f"{t[:idx].rstrip()}\n\n{t[idx:]}"
    return t


def _keyword_yesno(text: str) -> str:
    t = text or ""
    if any(k in t for k in _NO_KW):
        return "no"
    if any(k in t for k in _YES_KW):
        return "yes"
    return "unclear"


_RAG_TOP_K = 5  # threshold 컷 대신 top-k를 가져와 LLM이 증상에 맞는 것만 리랭크/선별한다.


async def _run_rag(query: str) -> tuple[list, list]:
    """RAG 유사사례 검색 → (rag_context[dict], 수의사답변[output_text]). fail-open.

    ⚠️ 요청 진행 중인 세션(ctx.db)이 아니라 '전용 새 세션'으로 검색한다 — pgvector 검색을
    진행 중 세션에서 돌리면 앱에서 실패하던 문제(post-booking이 새 세션 쓰는 이유와 동일).
    threshold로 자르지 않고 top-k를 그대로 넘겨, 증상과 맞는지(리랭크)·질환 추출은 LLM이 한다.
    """
    try:
        from app.db.session import AsyncSessionLocal

        from ai.rag import search_similar_triage_cases
        q = (query or "").strip()
        if not q:
            return [], []
        async with AsyncSessionLocal() as db:
            matches = await search_similar_triage_cases(db, q, top_k=_RAG_TOP_K)
        return [m.to_dict() for m in matches], [m.output_text for m in matches if m.output_text]
    except Exception as e:
        logger.warning("[triage] RAG 검색 실패: %s", e)
        return [], []


class TriageAgent:
    name = "triage"
    description = "증상 문진 + 응급도 판정. 질문은 LLM이 자연스럽게(트리 비노출), 판정은 디스크리미네이터로 결정론."

    @observe(name="triage")
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
        pet_name = _pet_call((ctx.pet_info or {}).get("name"))
        history = _history_before_current(ctx)

        # 0) 초기 진입 pill 클릭 → 추출/판정 없이 바로 증상부터 묻는다(첫 턴·첨부 없을 때).
        if ctx.user_message == INITIAL_TRIAGE_PILL and turn_count == 0 and not ctx.attachments:
            return AgentResult(
                reply=f"네! {pet_name}가 어디가 어떻게 불편한지 편하게 말씀해 주세요. "
                      "살펴보고 예약까지 도와드릴게요. 🐾",
                quick_replies=INITIAL_SYMPTOM_PILLS,
                state_patch={"triage_state": state, "active_flow": "triaging"},
            )

        # 1) 이미지/영상 분석(있으면) — VLM 먼저 판단 → 피부/안구면 CNN 보조 → RAG에 투입
        vis = None
        if ctx.attachments:
            _push_status(ctx, "image_analysis")   # 📷 이미지 분석중
            try:
                vis = await vision.analyze(ctx.attachments, ctx.user_message)
            except Exception as e:
                logger.warning("[triage] vision 분석 실패: %s", e)
            _push_status(ctx, "generating")        # 분석 끝 → 💬 응답 작성중
        vision_note = (vis or {}).get("note", "")
        vision_evidence = (vis or {}).get("evidence") or state.get("vision_evidence")
        vision_rag = (vis or {}).get("rag_text") or state.get("vision_rag", "")
        # 무관 이미지면 안내(이 턴에 표시). 관련 있으면 note가 추출에, rag_text가 RAG에 들어감.
        image_notice = ""
        if vis and vis.get("relevant") is False:
            image_notice = "📷 보내주신 사진은 증상과 직접 관련은 없어 보여요. 말씀으로 이어서 도와드릴게요.\n\n"
            # 무관 사진 + 증상 텍스트도 없는 '첫 턴' → 문진 시작 않고 정중히 거절(막기)
            text_has_content = bool(re.sub(r"[\W_]+", "", ctx.user_message or ""))
            if not text_has_content and turn_count == 0:
                return AgentResult(
                    reply="📷 보내주신 사진은 반려동물 증상과 관련이 없어 보여요. "
                          "어디가 불편한지 글로 알려주시거나, 증상이 보이는 사진을 보내주세요.",
                    state_patch={"active_flow": "idle"},
                )

        # 2) 추출 콜
        try:
            out = await call_llm_json(
                build_extraction_prompt(history, ctx.user_message, prev_section, extracted, vision_note)
            )
        except Exception as e:
            logger.warning("[triage] 추출 콜 실패: %s", e)
            out = {}

        # 1.5) 의도 분기 — '증상 정보가 아닌 발화'(메타·잡담·막연한 도움요청)는
        #      추출/완료판정/턴카운트에 넣지 않고, 그 발화에 응대한 뒤 본론으로 데려온다.
        #      ⚠️ 안전: 이미지 첨부거나 임상 위급(critical/high)이면 의도와 무관하게 정상 문진으로.
        intent = (out.get("intent") or "symptom").lower()
        tier_signal = (out.get("urgency_tier") or "normal").lower()
        if ctx.attachments or tier_signal in ("critical", "high"):
            intent = "symptom"
        if intent == "vague_help" and turn_count > 0:
            intent = "chitchat"   # 막연한 도움요청은 '진입 시점'에만 의미 — 진행 중엔 잡담으로
        # 증상 없이 '바로 예약'만 원하는 경우 → 예약은 문진 후에. 증상 먼저 / 그래도 바로면 홈 탭 안내.
        #   (문진 흐름은 유지 — 이어서 증상을 말하면 그대로 문진 진행. 턴카운트·추출은 건드리지 않음.)
        if intent == "booking_request" and ctx.emrid is None:
            return AgentResult(
                reply=_BOOKING_BLOCKED_REPLY.format(pet=pet_name),
                state_patch={"triage_state": state, "active_flow": "triaging"},
            )
        if intent == "closing":
            # '괜찮아요/됐어요' 등 마무리 신호 → 응대처럼 깔끔히 종료(다시 캐묻지 않음).
            return AgentResult(
                reply="알겠습니다. 추가로 궁금한 점이 있거나 예약을 원하시면 언제든 편하게 말씀해 주세요. 🐾",
                state_patch={"triage_state": state, "active_flow": "idle"},
            )
        if intent in ("meta", "chitchat", "vague_help"):
            return await self._nonsymptom_turn(ctx, intent, history, prev_section, pet_name, state)

        section = out.get("section") or prev_section or "GENERAL"
        # LLM이 값에 대괄호/따옴표를 붙이거나("[recent_single]") 없는 변수를 지어내도 엔진 매칭이
        # 깨지지 않게 정규화: 대괄호·공백 제거 + '정의된 변수만' 통과(플레이스홀더 unknown 무시).
        known_vars = set(engine.variables_for(section).keys())
        new_vars = {}
        for k, v in (out.get("variables") or {}).items():
            if not v:
                continue
            val = str(v).strip().strip("[]").strip().strip("'\"").strip()
            if not val or val == "unknown":
                continue
            if known_vars and k not in known_vars:
                continue
            new_vars[k] = val
        bucket = dict(extracted.get(section) or {})
        bucket.update(new_vars)
        extracted[section] = bucket

        # 3) 디스크리미네이터 매칭
        matched = engine.match(extracted)
        urgency = engine.top_urgency(matched)

        # 4) 종료 판단 — urgency_tier(LLM) + 디스크리미네이터 RED. RED는 critical로 취급(둘 중 위급).
        turn_count += 1
        enough = bool(out.get("enough_to_triage"))
        tier = (out.get("urgency_tier") or "normal").lower()
        if engine.red_flag_labels(matched):
            tier = "critical"
        if tier == "critical":
            terminate = turn_count >= CRITICAL_MAX_TURNS
        elif tier == "high":
            terminate = enough or turn_count >= HIGH_MAX_TURNS
        else:
            terminate = (turn_count >= NORMAL_MIN_TURNS and enough) or turn_count >= NORMAL_MAX_TURNS

        state.update({"extracted": extracted, "section": section,
                      "turn_count": turn_count, "vision_evidence": vision_evidence,
                      "vision_rag": vision_rag})

        if not terminate:
            # 5) 질문 콜 (트리 비노출, 따뜻하게)
            try:
                q = await call_llm_json(
                    build_question_prompt(pet_name, history, ctx.user_message, section, extracted),
                    temperature=0.75,   # 표현 다양성 ↑ (똑같은 인사 반복 완화)
                )
            except Exception:
                q = {}
            # pill은 최대 5개로 하드캡(LLM이 더 줘도 잘라냄). 최소 3은 프롬프트로 유도.
            # 막연한 포괄/회피성 보기('기타·여기저기' 등)는 프롬프트에서 안 만들게 지시.
            pills = [p for p in (q.get("quick_replies") or []) if p][:5]
            return AgentResult(
                reply=image_notice + (q.get("reply") or "조금 더 자세히 알려주시겠어요?"),
                quick_replies=pills,
                state_patch={"triage_state": state, "active_flow": "triaging"},
            )

        # 6) 완료 → 판정 확정 + RAG + 적재 (단, 예약창은 '예' 확인 후)
        urgency = urgency or "GREEN"
        # RAG 쿼리 = 추출 LLM이 만든 '보호자 말투 자연어 한 문장'. 짧은 응급 대화(노이즈 多)도
        # 깨끗한 서술형이라 narrative 문서(input_text)와 유사도가 잘 나온다. 없으면 대화 전체로 폴백.
        convo_texts = [m.get("content", "") for m in (ctx.history or [])
                       if isinstance(m, dict) and m.get("content")]
        rag_query = (out.get("rag_query") or "").strip() or " ".join(convo_texts).strip()
        if vision_rag:  # 이미지/영상 소견·CNN 병명도 RAG 검색에 반영
            rag_query = f"{rag_query} {vision_rag}".strip()
        _push_status(ctx, "searching")   # 🔍 증상 검색중(RAG)
        rag_context, rag_answers = await _run_rag(rag_query)
        _push_status(ctx, "generating")  # 검색 끝 → 💬 응답(의심질환 멘트) 작성중
        # 의심질환 + 안내 멘트 = RAG 답변(수의사 답변)에서 LLM이 도출(꾸며내지 않음). 단일 출처.
        symptom_text = " ".join([m.get("content", "") for m in (ctx.history or [])
                                 if isinstance(m, dict) and m.get("role") == "user" and m.get("content")])
        try:
            gen = await call_llm_json(
                build_suspected_confirm_prompt(pet_name, symptom_text, [a[:500] for a in rag_answers[:5]]),
                temperature=0.5,
            )
        except Exception:
            gen = {}
        suspected = list(dict.fromkeys(d for d in (gen.get("suspected_diseases") or []) if d))
        reply = (gen.get("message") or "").strip() or build_suspected_confirm_message(pet_name, suspected)
        reply = image_notice + _format_confirm_reply(reply)
        vtl_basis = engine.build_vtl_basis(
            matched, urgency, evidence=vision_note, reason=out.get("summary") or "",
        )
        symptom_keywords = [kw for kw in (out.get("keywords") or []) if kw]
        title = (out.get("title") or "").strip()[:60]  # 채팅 목록 요약 제목
        final_title = title or ", ".join(symptom_keywords[:3])

        emrid = ctx.emrid
        if ctx.db is not None and ctx.session is not None:
            try:
                from app.crud.chat import (
                    create_triage_guardian,
                    update_session_complete,
                    update_session_emrid,
                )
                from app.crud.triage import build_triage_result

                # new_booking(예약 후 챗에서 새로 예약하기)면 기존 emrid가 있어도 새 emrid를 발급해
                # 세션을 새 예약으로 옮긴다(force) — 기존 예약은 별도 emrid로 그대로 남는다.
                if emrid is None or ctx.new_booking:
                    guardian = await create_triage_guardian(ctx.db, ctx.petid)
                    emrid = guardian.emrid
                    await update_session_emrid(ctx.db, ctx.session, emrid, force=ctx.new_booking)
                    ctx.emrid = emrid
                info = {
                    "urgency_level": urgency,
                    "urgency_level_num": engine.urgency_num(urgency),
                    "vtl_basis": vtl_basis,
                    "red_flags": engine.red_flag_labels(matched),
                    "chief_complaint": out.get("chief_complaint"),
                    "symptom_keywords": symptom_keywords,
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
                # 대화 요약 제목/키워드 저장 + 문진 완료 표시(재진입 시 슬롯 재개 조건 resumable_schedule용)
                await update_session_complete(
                    ctx.db,
                    ctx.session,
                    info["symptom_keywords"],
                    title=final_title,
                )
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
                "symptom_keywords": symptom_keywords,
                "triage_summary": out.get("summary"),
            },
        }
        # 제목은 지금(완료 시점) 바로 푸시 → 채팅 목록 제목 실시간 갱신
        events = []
        if final_title:
            events.append({"type": "chat_title", "session_id": ctx.session_id, "title": final_title})
        return AgentResult(
            reply=reply,
            quick_replies=["예", "아니오"],
            state_patch={
                "triage_state": {"last_complete": complete_payload},
                "active_flow": "awaiting_booking_confirm",
                # 새 emrid를 발급했으니 new_booking 오버라이드는 해제(이후 phase는 새 예약 기준).
                "new_booking": False,
            },
            events=events,
        )

    # ── 비증상 발화(메타·잡담·막연한 도움요청) → 응대 후 본론 복귀 ──────────────
    #    상태(extracted·turn_count·section)는 그대로 둔다 = 노이즈가 종료 보험을 깎지 않음.
    async def _nonsymptom_turn(self, ctx: SessionContext, intent: str, history: list[dict],
                               prev_section: str | None, pet_name: str, state: dict) -> AgentResult:
        try:
            r = await call_llm_json(
                build_redirect_reply_prompt(pet_name, history, ctx.user_message, intent, prev_section),
                temperature=0.7,
            )
        except Exception:
            r = {}
        fallback = {
            "meta": f"방금까지 {pet_name} 얘기를 나누고 있었어요. 지금 가장 신경 쓰이는 증상을 "
                    "한 가지만 더 알려주시면 이어서 살펴볼게요.",
            "chitchat": f"{pet_name}의 증상을 조금 더 들려주시면 살펴보고 도와드릴게요. "
                        "어디가 불편해 보이는지 편하게 알려주실래요?",
            "vague_help": f"많이 걱정되시겠어요. {pet_name}가 어떤 상태인지 조금 더 들려주시면 "
                          "살펴보고, 필요하면 예약까지 도와드릴게요.",
        }.get(intent, "")
        # pill은 응대 에이전트처럼 고정 2지선다 — 증상 더 들을지 / 여기서 마칠지.
        return AgentResult(
            reply=r.get("reply") or fallback,
            quick_replies=["증상 더 말할게요", "괜찮아요"],
            state_patch={"triage_state": state, "active_flow": "triaging"},
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
