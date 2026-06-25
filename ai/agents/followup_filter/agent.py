"""경과 필터 AI.  담당: B

예약 뒤(Phase.BOOKED) 보호자 메시지를 보고, '진짜 경과'면 followupDB에 저장하고
잡담·병원질문이면 저장 안 하고 가볍게 넘긴다(필요 시 응대로 handoff).
흐름: 분류(LLM/fallback) → 경과면 누적요약 머지 + followupDB 저장 → AgentResult.
자세한 할 일: docs/AGENT_SPECS.md "6. 필터링".
"""
from __future__ import annotations

from langfuse import observe

from ai.llm import call_llm_json
from ai.monitoring import push_log
from ai.orchestrator.contracts import AgentResult, Intent, SessionContext

from . import repository
from .prompts import (
    CLARIFY_QUICK_REPLIES,
    CONTINUE_STATUS_PILL,
    HOSPITAL_INFO_PILL,
    NEW_BOOKING_DIRECT_PILL,
    NEW_BOOKING_TRIAGE_PILL,
    PREP_INSTRUCTIONS_PILL,
    REBOOK_ACTION_PILL,
    REBOOK_PILL,
    REPLY_CANCEL,
    REPLY_CANCEL_POLICY,
    REPLY_CARE_METHOD,
    REPLY_CONFIRM_PHOTO,
    REPLY_EMOTION_ACK,
    REPLY_HOSPITAL_INFO,
    REPLY_IRRELEVANT,
    REPLY_NEW_BOOKING_CONFIRM,
    REPLY_PET_GENERAL,
    REPLY_PREP_INSTRUCTIONS,
    REPLY_REBOOK,
    REPLY_REBOOK_OPTIONS,
    REPLY_SCHEDULE_LIST,
    SCHEDULE_LIST_PILL,
    START_TRIAGE_REPLY,
    VISIT_NOTE_SUMMARY_PILL,
    build_classification_prompt,
    build_species_mismatch_reply,
    canon_species,
    is_photo_followup,
    last_assistant_question,
    pick_saved_reply,
    REPLY_SAVED_URGENT,
    short_answer_kind,
)
from app.utils.followup_policy import BOOKING_CHANGE_LIMITED_REPLY, FOLLOWUP_LIMITED_REPLY

from .handlers import (
    _confirmed_time_text,
    _run_pending_action,
    _visit_note_summary_reply,
    appointment_time_reply,
    hospital_info_reply,
    vet_info_reply,
)
from .reply_policy import (
    _LIMITED_QUICK_REPLIES,
    _avoid_consecutive_request_ending,
    _avoid_observation_overload,
    _patch_pending,
    _quick_replies_for_result,
    _reply_state_patch,
)

# 사진 속 동물과 등록 펫의 종 대조 — 둘 다 이 집합 안에서 확실할 때만 불일치로 판정.
_KNOWN_SPECIES = {"dog", "cat", "rabbit"}
_AFFIRMATIVE_SHORTS = {
    "확인해줘", "확인해 줘", "확인", "응", "네", "그래", "좋아", "보여줘", "보여 줘",
    "해줘", "해 줘", "응 보여줘", "네 보여줘", "그래 보여줘", "응 확인해줘",
}
# 병원 인물(수의사/원장 등) 질문 감지 — 사실(누구) vs 주관 평가(친절해?/잘 봐?)를 가른다.
_VET_PERSON_WORDS = ("수의사", "의사", "담당", "선생님", "원장")
_VET_FACTUAL_WORDS = ("누구", "누가", "누군", "어떤", "어느", "이름")
_VET_SUBJECTIVE_WORDS = ("친절", "잘 봐", "잘봐", "잘 보", "잘보", "실력", "괜찮", "어때", "좋", "믿", "꼼꼼", "유명", "잘하")
# 예약 '병원/장소' 질문 — '어느 병원'은 시간이 아니라 병원 질문(시간 분기보다 우선).
_HOSPITAL_LOC_WORDS = (
    "어느 병원", "무슨 병원", "어디 병원", "어떤 병원", "병원 이름", "병원이름", "병원 위치",
    "병원 어디", "병원이 어디", "어느 병원으로", "어디로 예약", "병원 주소", "위치", "주소",
)
# 취소: 실제 '실행' 의도 vs '문의/가정형' 구분(가정형은 cancel_request 금지).
_CANCEL_EXEC_WORDS = (
    "취소해줘", "취소해 줘", "취소할래", "취소할게", "취소하고 싶", "취소해주세요", "취소해 주세요",
    "취소합니다", "취소해야", "없애줘", "없애 줘", "취소 부탁",
)
_CANCEL_INQUIRY_MARKS = (
    "하면", "해도", "가능", "되나요", "될까", "돼요", "되요", "수수료", "환불",
    "어떻게", "다시 예약", "다시 잡", "정책", "괜찮", "수 있", "건가요",
)
# 재예약: '실행 명령'(슬롯 조회로 바로 이어도 됨) vs '방법 문의/막연'(안내+선택지 먼저) 구분.
# 명령형(찾아/바꿔/잡아 + 줘/주세요) 또는 명시적 '빠른 시간 찾/없'은 즉시 슬롯 조회.
_REBOOK_EXEC_PHRASES = (
    "찾아줘", "찾아 줘", "찾아주세요", "찾아 주세요", "찾아줄래", "찾아봐",
    "바꿔줘", "바꿔 줘", "바꿔주세요", "변경해줘", "변경해 줘", "변경해주세요",
    "옮겨줘", "당겨줘", "잡아줘", "잡아 줘", "잡아주세요",
    "빠른 시간 찾", "빠른 시간 없", "빠른 거 없", "빠른 게 없", "다른 시간 찾", "다른 날 찾",
)
# 예약을 '바꾸려는' 의도 단어(문의/막연 포함) — '예약'과 함께 나오면 재예약 관련으로 본다.
_REBOOK_CHANGE_WORDS = (
    "바꾸", "바꿔", "바꿀", "변경", "옮기", "옮겨", "당기", "당겨", "앞당", "다른 날", "다른 시간",
)


# 관리방법 질문(상태보고 아님) — '해도 되나/어떻게 관리'. clarify로 새지 않게 한다.
_CARE_METHOD_WORDS = (
    "양치", "칫솔", "씻겨", "씻어", "목욕", "헹궈", "헹구", "닦아", "닦여", "빗겨", "발라",
    "관리", "산책", "먹여도", "그냥 둬", "둬도", "해줘야", "해줘도",
)
_CARE_Q_MARKS = ("되나", "되요", "돼요", "돼", "될까", "해야", "해도", "줘도", "어떻게", "뭘 해", "뭐 해",
                 "하나요", "하나", "할까", "?")
# 감정 표현 — 공감 먼저, clarify 금지.
_EMOTION_WORDS = ("걱정", "불안", "무서", "겁나", "겁이", "속상", "눈물", "마음이", "신경 쓰", "신경쓰",
                  "괜찮은 거 맞", "괜찮은거 맞", "별일 아니", "안심", "초조", "무섭")
_CRITICAL_FOLLOWUP_KW = (
    "피를 토",
    "토혈",
    "숨을 헐떡",
    "헐떡",
    "숨을 못",
    "숨쉬기 힘",
    "숨 쉬기 힘",
    "숨이 가쁘",
    "호흡곤란",
    "혀가 파",
    "혀가 보라",
    "잇몸이 파래",
    "입술이 파",
    "발작",
    "쓰러",
    "의식이 없",
    "의식이 잘",
    "잇몸이 하얗",
    "잇몸이 파",
    "소변을 아예 못",
    "소변을 못",
    "배가 갑자기 빵빵",
    "배가 갑자기 부",
)
_TREATMENT_PROGRESS_KW = ("수술", "시술", "약 먹", "약을 먹", "처방약", "주사 맞")
_PROGRESS_SIGNAL_KW = (
    "잘 먹",
    "안 먹",
    "별 이상",
    "기운",
    "통증",
    "끙끙",
    "부었",
    "진물",
    "토했",
    "구토",
    "설사",
    "잘 걸",
    "나아",
    "심해",
)


def _is_care_method_question(message: str) -> bool:
    t = message or ""
    return any(w in t for w in _CARE_METHOD_WORDS) and any(m in t for m in _CARE_Q_MARKS)


def _is_emotional(message: str) -> bool:
    return any(w in (message or "") for w in _EMOTION_WORDS)


def _is_cancel_execution(message: str) -> bool:
    """'예약 취소해줘/취소할래' 같은 실제 취소 실행 의도. 문의/가정형이면 False."""
    t = message or ""
    if "취소" not in t:
        return False
    if any(m in t for m in _CANCEL_INQUIRY_MARKS):
        return False
    return any(k in t for k in _CANCEL_EXEC_WORDS) or t.strip() in {"예약 취소", "취소"}


def _is_cancel_inquiry(message: str) -> bool:
    """'취소하면 다시 예약돼요?/취소 가능해요?' 같은 정책·가능여부 문의(취소 실행 아님)."""
    t = message or ""
    return "취소" in t and any(m in t for m in _CANCEL_INQUIRY_MARKS)


def _enforce_safety_classification(cls, message: str):
    """LLM 누락 시에도 명백한 응급/치료 경과는 저장·응급 안내를 보장한다."""
    text = message or ""
    updates = {}
    if any(keyword in text for keyword in _CRITICAL_FOLLOWUP_KW):
        updates.update(
            is_followup=True,
            category=Category.SYMPTOM_CHANGE,
            severity_hint=SeverityHint.URGENT_POSSIBLE,
            reply_kind=ReplyKind.URGENT_REBOOK,
        )
        if any(k in (cls.assistant_reply or "") for k in ("예약 시간", "현재 예약", "예약을 확인", "예약 내역")):
            updates["assistant_reply"] = ""
    elif (
        any(keyword in text for keyword in _TREATMENT_PROGRESS_KW)
        and any(keyword in text for keyword in _PROGRESS_SIGNAL_KW)
    ):
        updates["is_followup"] = True
        if cls.category not in FOLLOWUP_CATEGORIES:
            updates["category"] = Category.MEDICATION_RESPONSE
    if updates and not (cls.summary_delta or "").strip():
        updates["summary_delta"] = text.strip()[:100]
    return cls.model_copy(update=updates) if updates else cls


def _is_affirmative_for_pending(message: str) -> bool:
    text = " ".join((message or "").strip().split())
    return text in _AFFIRMATIVE_SHORTS or (
        len(text) <= 8 and any(k in text for k in ("응", "네", "그래", "좋아")) and not any(
            x in text for x in ("말고", "아니", "취소")
        )
    )


from .schema import (
    Category,
    FOLLOWUP_CATEGORIES,
    ReplyKind,
    SeverityHint,
    allows_save_notice_question,
    ensure_safe_reply,
    merge_followup_summary,
    needs_saved_reply_fallback,
    parse_classification,
    strip_save_notice,
)


async def classify_followup(
    ctx: SessionContext,
    user_message: str,
    *,
    vision_findings: str = "",
    vision_relevant: bool | None = None,
    prev_question: str = "",
    last_media_summary: str = "",
):
    """LLM으로 경과 여부 분류. 실패하면 키워드 fallback.

    vision_findings/vision_relevant: 첨부 사진·영상의 VLM 소견(있으면 분류·답변에 반영).
    prev_question: 직전 봇이 던진 질문(있으면 짧은 답변을 그 주제와 연결해 판단하게 한다).
    last_media_summary: 직전 사진 소견(이번 발화가 그 사진을 가리키면 참조하게 한다).
    """
    prompt = build_classification_prompt(
        pet_info=ctx.pet_info,
        followup_summary=ctx.followup_summary,
        history=ctx.history,
        user_message=user_message,
        attachment_count=len(ctx.attachments or []),
        vision_findings=vision_findings,
        vision_relevant=vision_relevant,
        last_reply_kind=ctx.last_followup_reply_kind,
        asked_fields=ctx.asked_followup_fields,
        prev_question=prev_question,
        last_media_summary=last_media_summary,
        conversation_memory=ctx.conversation_memory,
    )
    try:
        raw = await call_llm_json(prompt)
    except Exception:
        raw = None
    return parse_classification(raw, user_message)


async def analyze_media(ctx: SessionContext, user_message: str) -> tuple[str, bool | None, str]:
    """첨부 이미지/영상을 읽어 (소견, 관련성, 사진속_동물종) 반환. triage vision 재사용(fail-open).

    첨부가 없거나 분석 실패 시 ("", None, "") — 저장/응답 흐름을 막지 않는다.
    species는 등록된 반려동물 종과 대조해 '잘못 보낸 사진'을 가려내는 데 쓴다.
    """
    if not ctx.attachments:
        return "", None, ""
    from ai.agents.triage import vision
    # VLM/다운로드가 가끔 일시적으로 실패해 사진 설명이 빠지는 걸 줄이려고 1회 재시도(fail-open).
    vis = None
    for _ in range(2):
        try:
            vis = await vision.analyze(ctx.attachments, user_message)
        except Exception:
            vis = None
        if vis:
            break
    if not vis:
        return "", None, ""
    findings = (vis.get("note") or "").strip() \
        or ((vis.get("evidence") or {}).get("vlm_description") or "").strip()
    return findings, vis.get("relevant"), (vis.get("species") or "").strip().lower()


class FollowupFilterAgent:
    name = "followup_filter"
    # 라우터 LLM이 담당 선택 시 읽는 설명(router._AGENT_DESC 단일 출처).
    description = ("예약 후 아이 상태에 대한 모든 대화·질문(증상 변화·사진·되묻기 포함)을 받고, "
                   "예약 시간 변경·재예약, '내 예약 시각이 언제인지' 확인도 처리한다.")

    @observe(name="followup_filter")
    async def run(self, ctx: SessionContext, args: dict) -> AgentResult:
        user_message = (args or {}).get("user_message") or ctx.user_message or ""
        has_media = bool(ctx.attachments)
        msg = user_message.strip()
        pending_action = (ctx.pending_confirmation_action or "").strip()
        if pending_action and not has_media and _is_affirmative_for_pending(msg):
            return await _run_pending_action(ctx, pending_action)
        if not has_media and msg == CONTINUE_STATUS_PILL:
            return AgentResult(
                reply=FOLLOWUP_LIMITED_REPLY if ctx.followup_limited else "아이 상태에서 달라진 점을 편하게 남겨 주세요.",
                quick_replies=_LIMITED_QUICK_REPLIES if ctx.followup_limited else [],
                state_patch=_patch_pending(""),
            )
        if not has_media and msg == HOSPITAL_INFO_PILL:
            return await _run_pending_action(ctx, "hospital_info")
        if not has_media and msg == PREP_INSTRUCTIONS_PILL:
            return await _run_pending_action(ctx, "prep")
        if not has_media and msg == VISIT_NOTE_SUMMARY_PILL:
            return AgentResult(
                reply=_visit_note_summary_reply(ctx),
                quick_replies=_LIMITED_QUICK_REPLIES if ctx.followup_limited else [],
                state_patch=_patch_pending(""),
            )

        # P0(맥락 유지): 직전 봇 발화가 '질문'이고 이번이 짧은 긍정/부정/애매 답변이면,
        # 새 요청이 아니라 그 질문에 대한 답으로 보고 clarify 폴백("무엇을 도와드릴까요?")으로 빠지지 않는다.
        prev_question = "" if (has_media or pending_action) else last_assistant_question(ctx.history)
        answering_prev_q = bool(prev_question) and bool(short_answer_kind(msg))

        # P1(사진 기억): 이번 턴 첨부가 없어도 직전 사진을 가리키는 후속 발화면, 최근 사진 소견을 참조한다.
        recent_media = (ctx.last_media_summary or "").strip()
        photo_followup = (not has_media) and bool(recent_media) and is_photo_followup(msg)

        # P3(대화 품질): 관리방법 질문·감정 표현은 clarify로 새지 않게 한다(아래 분기에서 소비).
        is_care_method = (not has_media) and _is_care_method_question(msg)
        is_emotional = (not has_media) and _is_emotional(msg)

        # 사진·영상을 먼저 읽어, 분류·답변·요약에 소견을 반영한다(없으면 빈값).
        vision_findings, vision_relevant, vision_species = await analyze_media(ctx, user_message)
        cls = await classify_followup(
            ctx, user_message,
            vision_findings=vision_findings, vision_relevant=vision_relevant,
            prev_question=prev_question if answering_prev_q else "",
            last_media_summary=recent_media if photo_followup else "",
        )
        cls = _enforce_safety_classification(cls, user_message)
        # LLM이 그래도 일반 clarify로 답하면(맥락 무시) 무력화 — 저장 경로의 주제연결 fallback이 받게 한다.
        if answering_prev_q and "무엇을 도와드릴까요" in (cls.assistant_reply or ""):
            cls = cls.model_copy(update={"assistant_reply": ""})
        # 사진 후속인데도 '사진이 없다/보내달라'고 하면 무력화 — 직전 소견 기반 fallback이 받게 한다.
        if photo_followup and any(p in (cls.assistant_reply or "") for p in ("사진이 없", "사진을 보내", "사진을 다시")):
            cls = cls.model_copy(update={"assistant_reply": ""})
        # P4-d: 감정 단독 발화인데 공감 뒤 '의도 되묻기'로 흐르면 무력화 — clarify 폴백 방지(공감 마무리).
        if is_emotional and any(p in (cls.assistant_reply or "")
                                for p in ("알려주시는 걸까요", "예약을 바꾸시려", "무엇을 도와드릴까요", "관리 방법을 묻는")):
            cls = cls.model_copy(update={"assistant_reply": ""})

        # 이번 턴에 '관련 있는' 새 사진을 분석했으면, 다음 턴 후속 발화용으로 짧은 소견을 저장한다(원본 미보관).
        new_media_summary = ""
        if has_media and vision_findings and vision_relevant is not False:
            new_media_summary = vision_findings.strip()[:120]

        is_saved = False

        # 예약 취소 — '실행' 의도만 cancel_request. '취소하면 다시 돼요?' 같은 문의/가정형은 제외(이벤트 금지).
        cancel_inquiry = _is_cancel_inquiry(msg)
        # 재예약(예약 변경/앞당김) 의도 — 경과 보고·취소가 아닐 때만 예약 흐름으로 넘긴다.
        #  · 실행 명령(pill 클릭 / "찾아줘·바꿔줘" / "더 빠른 시간 찾·없") → 바로 슬롯 조회(rebook_request).
        #  · 방법 문의·막연("바꾸고 싶어요/어떻게/바꿀 수 있나요") → 슬롯 조회 전에 현재 예약+선택지 안내.
        rebook_exec = (
            msg in {REBOOK_PILL, REBOOK_ACTION_PILL}
            or any(k in msg for k in _REBOOK_EXEC_PHRASES)
        )
        rebook_related = (
            (cls.wants_rebooking or rebook_exec
             or ("예약" in msg and any(k in msg for k in _REBOOK_CHANGE_WORDS)))
            and not cls.is_followup and not cancel_inquiry and not _is_cancel_execution(msg)
        )
        wants_rebook = rebook_related and rebook_exec               # 실행만 즉시 슬롯 조회
        rebook_inquiry = rebook_related and not rebook_exec         # 문의·막연은 안내+선택지 먼저
        deterministic_cancel = _is_cancel_execution(msg) or (
            "예약" in msg and any(k in msg for k in ("안 갈", "못 갈"))
        )
        wants_cancel = (
            ((cls.wants_cancel and not cancel_inquiry) or deterministic_cancel)
            and not cls.is_followup and not wants_rebook
        )

        # 신규(추가) 예약 의도 — '바로 예약 / 문진 작성 후 예약' 선택지를 띄운다(변경=rebook과 구분).
        deterministic_new_booking = (
            msg == NEW_BOOKING_DIRECT_PILL
            or ("예약" in msg and any(k in msg for k in ("새", "새로", "추가", "잡고 싶", "잡을래")))
        )
        wants_new_booking = ((cls.wants_new_booking or deterministic_new_booking) and not cls.is_followup
                             and not wants_rebook and not wants_cancel)
        # '문진 작성 후 예약하기' pill 클릭 → 같은 챗에서 새 문진 시작(start_inchat_triage 이벤트).
        start_inchat_triage = msg == NEW_BOOKING_TRIAGE_PILL
        # 예약 내역 보기 — pill(결정론)은 분류와 무관히 동작, LLM 판단은 경과 아닐 때만.
        asks_schedule_list = (
            msg == SCHEDULE_LIST_PILL
            or msg == "예약 내역 보기"
            or (
                not cls.is_followup and (
                    ("예약" in msg and any(k in msg for k in ("내역", "목록", "볼래", "보여", "확인", "알려", "보여줘", "알려줘")))
                    or cls.asks_schedule_list
                    or any(k in msg for k in ("현재 예약", "내 예약", "여기서 예약", "이 대화의 예약", "지금 예약"))
                )
            )
        )
        # 내원 전 준비사항 다시 보기.
        asks_prep = (msg == PREP_INSTRUCTIONS_PILL) or (cls.asks_prep_instructions and not cls.is_followup)

        # 예약 '병원/장소' 질문('어느 병원이야?') → 예약된 병원 정보 안내. 시간 분기보다 우선한다.
        asks_hospital = (
            any(w in user_message for w in _HOSPITAL_LOC_WORDS)
            and not wants_rebook and not wants_cancel and not cls.is_followup
        )
        # '내 예약 시각이 언제인지' 묻는 경우 → 실제 confirmed_time 안내(병원 운영시간 아님).
        # 정확일치 대신 '예약' + (언제/시간/몇시) 부분일치로 견고하게 잡는다(변경 의도는 위에서 제외됨).
        # 단, '어느/무슨/어디 병원·위치·주소'는 시간이 아니라 병원 질문이므로 asks_hospital이 우선.
        asks_time = (
            cls.asks_appointment_time
            or ("예약" in user_message and any(k in user_message for k in ("언제", "시간", "몇 시", "몇시")))
        ) and not asks_hospital and not wants_rebook and not rebook_inquiry and not cls.is_followup

        # 병원 인물 질문 → 예약(scheduleDB.doctorid)으로 실제 수의사 이름 안내.
        # 짧은 발화("누구 의사지?")도 예약 컨텍스트와 연결되게 부분일치로 잡는다(병원 행정질문과 별개).
        _msg_has_person = any(k in user_message for k in _VET_PERSON_WORDS)
        asks_vet_factual = cls.asks_vet_info or (
            _msg_has_person and any(k in user_message for k in _VET_FACTUAL_WORDS)
        ) or (
            any(k in user_message for k in ("누구", "누가", "어떤", "어느"))
            and any(k in user_message for k in ("진료받", "진료 받", "봐줘", "봐 줘"))
        )
        # "그 의사 친절해?/잘 봐?" 같은 주관 평가 — 단정 대신 따뜻한 일반 안내(유형 4).
        asks_vet_subjective = _msg_has_person and any(k in user_message for k in _VET_SUBJECTIVE_WORDS)
        asks_vet = (asks_vet_factual or asks_vet_subjective) and not wants_rebook and not cls.is_followup

        # 사진 속 동물 종이 등록된 반려동물과 다르면(둘 다 확실할 때만) → 잘못 보낸 사진일 수 있음.
        # ※ 펫 등록 종은 DB에 한글/영어 섞여 있어(예: '고양이') 반드시 정규화해서 비교한다.
        pet_species = canon_species((ctx.pet_info or {}).get("species"))
        photo_species = canon_species(vision_species)
        species_mismatch = (
            has_media and photo_species in _KNOWN_SPECIES
            and pet_species in _KNOWN_SPECIES and photo_species != pet_species
        )

        # 텍스트가 경과도 아닌데 사진이 '무관해 보이면'(relevant=false) → 잘못 보낸 것일 수 있으니
        # 저장하지 말고 한 번 더 확인한다(맞으면 다시 보내달라). 데이터 오염/오알람 방지.
        photo_missent = has_media and (not cls.is_followup) and (vision_relevant is False)
        # 종 불일치는 관련성과 무관하게 '잘못 보낸 사진'으로 본다(강아지 눈병이라도 펫이 고양이면).
        ask_photo = photo_missent or species_mismatch

        if ctx.followup_limited and (wants_rebook or wants_cancel or rebook_inquiry):
            result = AgentResult(reply=BOOKING_CHANGE_LIMITED_REPLY, quick_replies=_LIMITED_QUICK_REPLIES)
        # 0) 재예약 '실행' 요청 → 저장하지 않고 예약 흐름 신호(rebook_request)를 프론트로 넘긴다.
        elif wants_rebook:
            # P4-b: 현재 예약을 한 번 되짚고 변경 흐름으로(이벤트·pill 유지). 시각 없으면 기존 답변.
            when = await _confirmed_time_text(ctx)
            prefix = f"현재 예약은 {when}이에요. " if when else ""
            result = AgentResult(
                reply=prefix + ensure_safe_reply(cls, REPLY_REBOOK),
                events=[{"type": "rebook_request", "emrid": ctx.emrid}],
            )
        # 0-z) 예약 변경 '방법 문의·막연한 요청' → 슬롯을 바로 찾지 않고 현재 예약 + 선택지 제시(이벤트 없음).
        #      "직접 변경" / "제가 찾아드림" 두 선택지를 pill로 주고, 사용자가 고르면 그때 슬롯 조회로 이어진다.
        elif rebook_inquiry:
            when = await _confirmed_time_text(ctx)
            prefix = f"현재 예약은 {when}이에요. " if when else ""
            result = AgentResult(
                reply=prefix + REPLY_REBOOK_OPTIONS,
                quick_replies=[REBOOK_PILL, SCHEDULE_LIST_PILL],
            )
        # 0-a) '문진 작성 후 예약하기' → 같은 챗에서 새 문진 시작(백엔드가 new_booking 플래그 ON).
        elif start_inchat_triage:
            result = AgentResult(
                reply=START_TRIAGE_REPLY,
                events=[{"type": "start_inchat_triage", "emrid": ctx.emrid}],
            )
        # 0-b) 신규(추가) 예약 의도 → 바로/문진 선택지를 띄운다(동작은 프론트·후속 턴이 처리).
        elif wants_new_booking:
            result = AgentResult(
                reply=ensure_safe_reply(cls, REPLY_NEW_BOOKING_CONFIRM),
                quick_replies=[NEW_BOOKING_DIRECT_PILL, NEW_BOOKING_TRIAGE_PILL],
            )
        # 0-c) 예약 내역 보기 → 현재 예약 목록(show_schedules)을 프론트가 카드로 렌더.
        elif asks_schedule_list:
            is_all_schedules_requested = any(k in msg for k in ("전체", "전부", "목록", "내역", "다가오는"))
            if msg == SCHEDULE_LIST_PILL:
                is_all_schedules_requested = True
            
            current_only = not is_all_schedules_requested
            
            if current_only:
                when = await _confirmed_time_text(ctx)
                hospital_name = ""
                if ctx.db and ctx.hospitalid:
                    try:
                        from app.models.hospital import Hospital
                        from sqlalchemy import select
                        h = (await ctx.db.execute(select(Hospital).where(Hospital.hospitalid == ctx.hospitalid))).scalar_one_or_none()
                        hospital_name = f", {h.hospital_name}" if h else ""
                    except Exception:
                        pass
                if when:
                    reply = f"현재 이 대화에 연결된 예약은 {when}{hospital_name} 예약이에요."
                else:
                    reply = "현재 연결된 확정 예약을 찾지 못했어요."
            else:
                reply = ensure_safe_reply(cls, REPLY_SCHEDULE_LIST)

            result = AgentResult(
                reply=reply,
                events=[{"type": "list_schedules", "emrid": ctx.emrid, "current_only": current_only}],
            )
        # 0-d) 내원 전 준비사항 다시 보기 → 저장된 준비사항(show_prep)을 프론트가 카드로 렌더.
        elif asks_prep:
            result = AgentResult(
                reply=ensure_safe_reply(cls, REPLY_PREP_INSTRUCTIONS),
                events=[{"type": "show_prep", "emrid": ctx.emrid}],
            )
        # 0-0) 예약 '병원/장소' 질문 → 예약된 병원 정보 안내(시간 아님). reception 핸드오프로 표시.
        elif asks_hospital:
            result = AgentResult(
                reply=await hospital_info_reply(ctx),
                handoff=Intent.RECEPTION,
            )
        # 0-1) '내 예약 시각' 질문 → 실제 confirmed_time 안내(저장 안 함).
        elif asks_time:
            result = AgentResult(reply=await appointment_time_reply(ctx))
        # 0-1b) 병원 인물 질문 → 예약의 실제 수의사 이름 안내(주관 질문이면 일반 안내). 저장 안 함.
        elif asks_vet:
            result = AgentResult(
                reply=await vet_info_reply(ctx, subjective=asks_vet_subjective),
                quick_replies=_LIMITED_QUICK_REPLIES if ctx.followup_limited else [HOSPITAL_INFO_PILL, SCHEDULE_LIST_PILL],
            )
        # 0-2a) 취소 '문의/가정형'("취소하면 다시 돼요?") → 취소 이벤트 없이 정책/가능여부만 안내.
        #       P4-c: 현재 예약을 한 번 되짚는다(cancel_request는 절대 발생시키지 않음).
        elif cancel_inquiry:
            when = await _confirmed_time_text(ctx)
            if ctx.followup_limited:
                prefix = f"현재 예약은 {when}이에요. " if when else ""
                base = BOOKING_CHANGE_LIMITED_REPLY
            else:
                prefix = f"현재 예약은 {when}로 잡혀 있어요. " if when else ""
                base = REPLY_CANCEL_POLICY
            result = AgentResult(
                reply=prefix + base,
                quick_replies=_LIMITED_QUICK_REPLIES if ctx.followup_limited else [SCHEDULE_LIST_PILL, HOSPITAL_INFO_PILL],
            )
        # 0-2) 예약 취소 '실행' 요청 → 저장 안 하고 취소 신호(cancel_request)를 프론트로 넘긴다.
        elif wants_cancel:
            result = AgentResult(
                reply=ensure_safe_reply(cls, REPLY_CANCEL),
                events=[{"type": "cancel_request", "emrid": ctx.emrid}],
            )
        # 1) 저장하지 않는 경우: (경과 아님 + 첨부 없음) 또는 (잘못 보낸 듯한 사진 = 무관/종 불일치).
        #    단, 직전 봇 질문에 대한 짧은 답변(answering_prev_q)이나 직전 사진 후속(photo_followup)이면
        #    clarify로 빠지지 말고 저장 경로로 보내 맥락(질문 주제·사진 소견)을 잇는다.
        elif (not cls.is_followup and not has_media and not answering_prev_q and not photo_followup) or ask_photo:
            if species_mismatch:
                pet_name = (ctx.pet_info or {}).get("name") or "아이"
                result = AgentResult(
                    reply=build_species_mismatch_reply(pet_name, pet_species, photo_species)
                )
            elif photo_missent:
                result = AgentResult(reply=ensure_safe_reply(cls, REPLY_CONFIRM_PHOTO))
            elif cls.category == Category.HOSPITAL_INFO:
                result = AgentResult(
                    reply=ensure_safe_reply(cls, REPLY_HOSPITAL_INFO),
                    handoff=Intent.RECEPTION,
                )
            # 관리방법 질문 → clarify 금지. LLM의 3부분 답변(care_advice) 우선, 비면 care fallback.
            elif is_care_method or cls.category == Category.PET_GENERAL:
                result = AgentResult(
                    reply=ensure_safe_reply(cls, REPLY_CARE_METHOD if is_care_method else REPLY_PET_GENERAL),
                    state_patch=_reply_state_patch(ctx, cls),
                )
            # 감정 표현 → 공감 먼저(clarify 금지).
            elif is_emotional:
                result = AgentResult(
                    reply=ensure_safe_reply(cls, REPLY_EMOTION_ACK),
                    state_patch=_reply_state_patch(ctx, cls),
                )
            else:
                # 모호/무관 → 차단 멘트 대신 무엇을 원하는지 되묻고, 의도 선택지를 띄운다.
                result = AgentResult(
                    reply=ensure_safe_reply(cls, REPLY_IRRELEVANT),
                    quick_replies=CLARIFY_QUICK_REPLIES,
                )

        elif ctx.followup_limited and (cls.is_followup or has_media):
            result = AgentResult(
                reply=FOLLOWUP_LIMITED_REPLY,
                quick_replies=_LIMITED_QUICK_REPLIES,
                state_patch=_reply_state_patch(ctx, cls),
            )

        else:
            # 2) 저장할 경과 메모(delta) 결정.
            delta = (cls.summary_delta or "").strip()
            if not delta and answering_prev_q:
                # 짧은 답변은 그 자체론 메모가 빈약하므로 직전 질문 주제와 함께 남긴다.
                delta = f"직전 질문 '{prev_question[:30]}'에 '{user_message.strip()}'라고 답함."
            if not delta and photo_followup:
                # 사진 후속도 직전 사진 소견과 함께 남겨 맥락을 보존한다.
                delta = f"직전 사진 소견({recent_media[:60]})에 대해 '{user_message.strip()}'."
            if not delta:
                delta = user_message.strip()[:100] if user_message.strip() else "보호자가 상태 사진·영상을 공유함."
            # 사진 소견을 차트 요약에 보강(LLM이 빠뜨렸을 때만 — 중복 방지).
            if vision_findings and vision_findings not in delta:
                delta = f"{delta} / {vision_findings}".strip(" /")
            updated_summary = merge_followup_summary(ctx.followup_summary, delta)

            # 3) followupDB 저장.
            emergency = cls.severity_hint == SeverityHint.URGENT_POSSIBLE
            saved = await repository.save_followup(
                ctx.db,
                emrid=ctx.emrid,
                userid=ctx.userid,
                message=user_message,
                images=ctx.attachments,
                ai_summary=updated_summary,
                emergency_alert=emergency,
            )
            is_saved = saved is not None

            # 사진 소견을 반영한 LLM 답변(assistant_reply) 우선, 비면 상황별 캔드 멘트로.
            # 캔드 멘트는 매번 같은 문장이 반복되지 않게 결정론적으로 변형을 고른다(직전 답변 회피).
            # 사진 후속이면, '사진 없다'가 아니라 직전 사진 소견을 되짚는 fallback을 쓴다.
            if photo_followup:
                fallback_reply = (
                    f"방금 사진에서는 {recent_media.rstrip(' .')}이 보였어요. "
                    "같은 부위가 더 달라지거나 진물이 생기는지 이어서 살펴봐 주세요."
                )
            elif emergency:
                # 응급 경과: '변화 있으면 말씀해 주세요' 같은 한가한 저장 문구를 base로 쓰면
                # 뒤에 붙는 응급 안내(URGENT_SAFETY_NOTE)와 충돌한다 → 공감 한 줄만 둔다.
                fallback_reply = REPLY_SAVED_URGENT
            else:
                fallback_reply = pick_saved_reply(cls.is_followup, ctx.history)
            raw_reply = ensure_safe_reply(cls, fallback_reply)
            allow_save_notice = allows_save_notice_question(user_message)
            reply = strip_save_notice(raw_reply, allow_save_notice=allow_save_notice)
            if needs_saved_reply_fallback(reply, user_message):
                fallback_cls = cls.model_copy(update={"assistant_reply": ""})
                reply = strip_save_notice(
                    ensure_safe_reply(fallback_cls, fallback_reply),
                    allow_save_notice=allow_save_notice,
                )
            events = []
            if is_saved:
                events.append({
                    "type": "followup_saved",
                    "emrid": ctx.emrid,
                    "followupid": getattr(saved, "followupid", None),
                    "category": cls.category.value,
                    "severity_hint": cls.severity_hint.value,
                    "emergency": emergency,
                    "has_media": has_media,
                    "forced_by_media": has_media and not cls.is_followup,
                })
            # urgent면 진료를 앞당기는 '더 빠른 시간 찾기' pill을 제안(클릭 시 재예약 흐름).
            media_patch = {"last_media_summary": new_media_summary} if new_media_summary else {}
            result = AgentResult(
                reply=reply,
                quick_replies=[],
                state_patch={"followup_summary": updated_summary, **_reply_state_patch(ctx, cls), **media_patch},
                events=events,
            )

        # 다음 턴에 짧은 긍정("응/보여줘")이 오면 실행할 동작(pending)을 '한 번만' 정한다.
        # 위 분기에서 쓴 의도 플래그를 그대로 재사용 — 같은 조건을 두 번 판단/덮어쓰지 않는다.
        if ctx.followup_limited and (wants_rebook or wants_cancel or rebook_inquiry):
            pending_action = ""
        elif wants_new_booking:
            pending_action = "new_booking"
        elif asks_schedule_list:
            pending_action = "schedule_list"
        elif asks_prep:
            pending_action = "prep"
        elif asks_time:
            pending_action = "appointment_time"
        elif asks_vet:
            pending_action = "vet_info"
        elif wants_rebook or rebook_inquiry:
            # 변경 문의 뒤 짧은 긍정("응/네")이 오면 그때 슬롯 조회로 이어지게 rebook을 예약해 둔다.
            pending_action = "rebook"
        elif result.handoff == Intent.RECEPTION or cls.category == Category.HOSPITAL_INFO:
            pending_action = "hospital_info"
        else:
            pending_action = ""
        result.state_patch = {**(result.state_patch or {}), **_patch_pending(pending_action)}

        result.reply = _avoid_consecutive_request_ending(result.reply, ctx.history)
        result.reply = _avoid_observation_overload(result.reply, ctx.history)
        result.quick_replies = _quick_replies_for_result(result, saved=is_saved, emergency=(
            cls.severity_hint == SeverityHint.URGENT_POSSIBLE
        ), limited=ctx.followup_limited)

        # 공통 모니터링 로그
        push_log("followup_filter", {
            "emrid": ctx.emrid,
            "scheduleid": ctx.scheduleid,
            "message": user_message[:80],
            "category": cls.category.value,
            "severity": cls.severity_hint.value,
            "is_saved": is_saved,
            "has_media": has_media,
        })

        return result


followup_filter = FollowupFilterAgent()
