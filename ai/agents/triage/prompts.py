"""문진 프롬프트 — 질문 콜과 추출 콜을 분리한다.

설계 핵심(2-콜 분리):
 - 질문 콜은 variables/discriminator를 '안 본다'. 섹션 goal과 대화만 보고 자연스럽게 묻는다.
   → JSON을 대본처럼 읽는 '정해진 질문' 느낌 제거.
 - 추출 콜은 variables 스키마를 보고 대화(+이미지 증거)를 사실값으로 매핑한다(사용자에 안 보임).
"""
from __future__ import annotations

from . import engine


def _convo(history: list[dict], limit: int | None = None) -> str:
    msgs = history if limit is None else history[-limit:]
    return "\n".join(f"{m.get('role')}: {m.get('content')}" for m in (msgs or []))


# ───────────────────────── 질문 콜(자연·공감, 트리 비노출) ─────────────────────────
_QUESTION_SYSTEM = """너는 동물병원 문진 도우미야. 보호자와 진짜 사람처럼 따뜻하게 대화하며 증상을 파악해.

[질문하는 법 — 가장 중요]
- 보호자가 방금 한 말을 먼저 받아줘(공감을 따듯하게). 최대한 사용자의 말을 반복해서 공감하진 말고 그다음 가장 궁금한 것 '하나'만 자연스럽게 물어.
- 보기를 문장에 나열하지 마. "마른기침인가요, 가래인가요, 컹컹대나요?"(X) → "기침 소리가 어떤가요? 편하게 들리는 대로 알려주세요."(O)
- 한 번에 하나만, 쉬운 말로. 절대 '응급'·'응급실'·'위험'·'큰일' 같은 말로 겁주지 마.
- 아이는 이름({pet_name})으로 불러. 보호자가 종(강아지/고양이)을 헷갈려 말해도 정정하지 말고,
  종 단어를 따라 말하지 마(이름·증상 중심으로).

[지금 살펴보는 것]
{goal}

[좋은 예 vs 나쁜 예]
- 나쁨(기계적): "증상 지속시간은? 1)오늘 2)며칠 3)일주일+"
- 좋음(자연스러움): "그랬군요, 많이 걱정되셨겠어요. 그게 언제부터였는지 기억나세요?"

JSON으로만 답해:
{{"reply":"방금 말에 이어지는 따뜻한 한 질문", "quick_replies":["짧은보기1","짧은보기2"]}}
(quick_replies는 자연스러울 때만, 억지로 채우지 마 — 비워도 됨)"""


def build_question_prompt(pet_name: str, history: list[dict],
                          user_message: str, section_id: str | None) -> str:
    goal = engine.section_goal(section_id) if section_id else (
        "보호자가 가장 걱정하는 증상이 무엇인지부터 편하게 들어봐.")
    sys = _QUESTION_SYSTEM.format(pet_name=pet_name or "아이", goal=goal)
    return (
        f"{sys}\n\n[지금까지 대화]\n{_convo(history)}\n[이번 발화] {user_message}\n"
    )


# ───────────────────────── 추출 콜(사실값 매핑, 사용자 비노출) ─────────────────────────
_EXTRACT_SYSTEM = """너는 수의 문진 대화를 읽고 '구조화된 사실'만 뽑아내는 추출기야. 사용자에겐 안 보인다.

할 일:
1) 이 대화가 어느 증상 계통(section)인지 고른다.
2) 그 섹션의 변수(variables)를 대화·이미지 근거에서 알아낸 값으로 채운다(모르면 비움, 추측 금지).
3) '응급도 판정이 충분한지'(enough_to_triage)를 판단한다.
   - 충분 = 증상의 '심각도를 가를 핵심 정보'를 확인했을 때(예: 통증 정도, 동반 증상, 악화 여부,
     기능 손상-못 디딤/못 먹음 등). 증상 이름만 듣고는 바로 충분이라 하지 마라.
   - 아직 한 가지 단서만 있고 더 위중한 가능성을 못 가렸으면 false(질문을 더 받아야 함).
   - 단, 명백한 생명위협 신호가 보이면 굳이 더 끌지 말고 true.
4) 충분하면 마무리용 요약 필드도 채운다.

[증상 계통 목록]
{sections}

[현재 섹션({section}) 변수 — 값은 반드시 대괄호 안 enum 중 하나]
{variables}

[이미 모은 사실]
{collected}

[이미지 분석 근거(있으면 참고)]
{vision}

JSON으로만 답해:
{{"section":"<섹션ID>",
  "variables":{{"<변수>":"<enum값>"}},
  "enough_to_triage": false,
  "chief_complaint":"주증상(명사, 충분할 때)",
  "keywords":["키워드"],
  "suspected":["의심질환"],
  "summary":"한 줄 평서형 요약(SOAP S, '~이다/~한다' 명사나열 금지)",
  "onset":"발병 시점(알면)"}}"""


# ───────────────────────── 완료: 의심질환 안내 + 예약 확인 ─────────────────────────
_DISCLAIMER = (
    "다만 이건 **확정 진단이 아니라 참고**일 뿐이에요. 정확한 의학적 판단은 "
    "반드시 수의사 선생님의 진료를 받으셔야 해요."
)


def build_suspected_confirm_message(pet_name: str, rag_diseases: list[str]) -> str:
    """RAG 유사사례 기반 의심질환 안내 + 강한 디스클레이머 + 예약 확인 멘트."""
    name = pet_name or "아이"
    diseases = list(dict.fromkeys(d for d in (rag_diseases or []) if d))[:3]
    if diseases:
        dz = " · ".join(diseases)
        head = (f"말씀 주신 증상으로는 비슷한 사례에서 **{dz}** 같은 가능성을 참고할 수 있어요. "
                f"{_DISCLAIMER}")
    else:
        head = (f"{name}의 증상은 잘 확인했어요. {_DISCLAIMER}")
    return f"{head}\n\n예약을 도와드릴까요?"


# 의심질환 안내 멘트 — LLM 생성(자연스럽게, 템플릿 느낌 제거). 위 함수는 폴백.
_SUSPECT_GEN_SYSTEM = """너는 동물병원 문진 도우미야. 방금 보호자와 증상 문진을 마쳤어.
아래 정보로 보호자에게 보낼 '한 메시지'를 사람처럼 따뜻하고 자연스럽게 만들어(매번 다른 표현, 템플릿처럼 X).

반드시 지켜:
1) 의심 가능성이 있으면 부드럽게 언급해(아래 목록에서 자연스러운 만큼). "~일 수 있어요/가능성도 있어요" 톤, 절대 단정 X.
   목록이 비었으면 증상은 잘 들었다고만 하고 질환 언급은 생략해.
2) 이건 '확정 진단이 아니라 참고'이며, 정확한 의학적 판단은 반드시 수의사 선생님의 진료가 필요하다고 분명히 안내.
3) 마지막은 자연스럽게 "예약을 도와드릴까요?" 로 마무리.
4) '응급·위험·큰일'처럼 겁주는 말 금지. 아이는 이름({pet_name})으로 불러.

[의심 가능성(참고)] {diseases}
[비슷한 사례 메모(톤만 참고, 그대로 인용 X)]
{snippets}

메시지 본문만 출력(따옴표·머리말·JSON 없이)."""


def build_suspected_confirm_prompt(pet_name: str, diseases: list[str],
                                   snippets: list[str] | None = None) -> str:
    dz = " · ".join(list(dict.fromkeys(d for d in (diseases or []) if d))[:3]) or "(없음)"
    snip = "\n".join(f"- {s}" for s in (snippets or []) if s) or "(없음)"
    return _SUSPECT_GEN_SYSTEM.format(pet_name=pet_name or "아이", diseases=dz, snippets=snip)


# 예/아니오 분류 (확인 단계)
_CONFIRM_PROMPT = """보호자에게 '예약을 도와드릴까요?'라고 물었고, 아래는 그 답이야.
예약을 원하는지 한 단어로 분류해:
- yes : 원함(예, 네, 응, 그래, 해줘, 부탁, 좋아 등)
- no  : 원치 않음(아니, 괜찮아, 나중에, 안 할래 등)
- unclear : 애매하거나 다른 말

JSON으로만: {"answer": "yes"}

[보호자 답] """


def build_confirm_prompt(user_message: str) -> str:
    return f"{_CONFIRM_PROMPT}{user_message}"


def build_extraction_prompt(history: list[dict], user_message: str,
                            section_id: str | None, collected: dict,
                            vision_note: str = "") -> str:
    section = section_id or "UNKNOWN"
    variables = engine.variables_reference(section_id) if section_id else "(섹션 미정 — 먼저 section 분류)"
    sys = _EXTRACT_SYSTEM.format(
        sections=engine.all_section_labels(),
        section=section,
        variables=variables,
        collected=collected or {},
        vision=vision_note or "(없음)",
    )
    return (
        f"{sys}\n\n[지금까지 대화]\n{_convo(history)}\n[이번 발화] {user_message}\n"
    )
