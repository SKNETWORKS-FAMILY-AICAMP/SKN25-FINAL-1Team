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
- ⛔ 보호자 답을 앵무새처럼 되받지 마. "기침이 나오는군요", "약간 거칠어 보이는군요", "안 들리는군요"처럼
  '말 되받기 + 질문' 똑같은 틀을 매 턴 반복하는 게 제일 로봇 같다. "~군요"·"~겠어요"·"감사합니다" 반복 금지.
- 매 턴 '시작 방식과 구조'를 바꿔라. 한 가지 틀로만 가지 마:
  · 어떤 땐 짧은 공감 한마디("아이고, 걱정되시겠어요")
  · 어떤 땐 안심·정보 한마디("그건 흔히 있는 일이에요")
  · 어떤 땐 군더더기 없이 바로 따뜻하게 질문 (받아주기 생략 OK)
- ★ [지금까지 대화]에 있는 '네 이전 질문들'을 보고, 시작 말투·구조가 겹치지 않게 해라.
- 가장 궁금한 것 '하나'만 쉬운 말로. 보기를 문장에 나열하지 마
  ("마른기침인가요, 가래인가요?" X → "기침 소리가 어떤가요? 편하게 알려주세요." O).
- 절대 '응급'·'위험'·'큰일' 같은 말로 겁주지 마. 아이는 이름({pet_name})으로 부르고, 종을 헷갈려 말해도 정정 마.

[지금 살펴보는 것]
{goal}

[좋은 예 vs 나쁜 예]
- 나쁨(로봇): 매 턴 "알려주셔서 감사합니다. ○○ 기억나세요?" (똑같은 인사 + 기계적)
- 좋음(자연스러움): "이미 삼켜버렸군요, 놀라셨겠어요. 혹시 먹은 뒤로 토하거나 기운 없어 보이진 않았어요?"
- 좋음: "한두 조각이면 그래도 다행이에요. 뽀미가 평소보다 침을 많이 흘리거나 떨진 않나요?"

JSON으로만 답해:
{{"reply":"방금 말에 이어지는 따뜻하고 자연스러운 한 질문(위 '좋은 예'처럼 공감 먼저)", "quick_replies":["보기"]}}
(★reply는 위 '좋은 예'처럼 부드럽게. 아래 보기 예시를 질문 문장으로 베끼지 마 — 보기 후보일 뿐이다.
 quick_replies = reply 질문에 보호자가 바로 고를 '보기(옵션)'로만 채워라(placeholder 금지).
 보기 예시: 시간→[오늘, 며칠 전, 일주일 이상] / 정도→[약해요, 보통이에요, 심해요] / 식욕→[잘 먹어요, 조금만, 안 먹어요].
 개수는 질문마다 자연스럽게 달라진다(보통 3~5개, 5개 초과 금지). 안 어울리면 비워도 됨.)"""


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
2) 그 섹션의 변수(variables)를 채운다. 변수명은 아래 목록에 '정의된 것만' 쓰고 새로 만들지 마라.
   값도 반드시 대괄호 안 enum 중 하나(모르면 비움, 추측 금지).
3) '응급도 판정이 충분한지'(enough_to_triage)를 판단한다.
   - 충분 = 증상의 '심각도를 가를 핵심 정보'를 확인했을 때(통증 정도·동반 증상·악화 여부·기능 손상 등).
     증상 이름만 듣고는 바로 충분이라 하지 마라. 명백한 생명위협이면 true.
4) urgency_tier — '문진을 얼마나 빨리 마쳐야 하나'를 임상적으로 판단(critical/high/normal):
   - "critical": 지금 당장 생명이 위험(예: 발작이 안 멈추거나 연달아, 숨 못 쉼·혀 파람·개구호흡,
     의식 없음·안 깨어남, 쓰러져 못 일어남, 멈추지 않는 대량 출혈, 다량 중독 섭취).
   - "high": 응급실 수준은 아니어도 빨리 진료가 필요한 위중 증상군(예: 한 번 발작 후 회복, 호흡이 힘들어 보임,
     쓰러졌다 회복, 갑작스런 다리 마비, 심한 통증, 독성물질 의심 섭취).
   - "normal": 그 외 일반 증상(기침·절뚝·피부·눈·귀·경미 소화기 등).
   ※ 위 예시는 보정용일 뿐 — 나열에 없어도 임상적으로 같은 수준이면 그 tier로 일반화해서 판단해라.
5) 사람에게 보이는 필드(chief_complaint·keywords·summary)는 반드시 한국어로.
6) rag_query — 비슷한 사례를 검색하기 위한 '보호자 말투의 자연스러운 한 문장'.
   지금까지 파악한 증상을 보호자가 병원에 글로 물어보듯 서술해라(짧은 단어 나열 X, 노이즈 제거).
   예: "강아지가 방금 발작을 시작했고 몸을 떨며 경련을 해요" / "고양이가 며칠째 마른기침을 하고 콧물이 나요".
7) title — 이 상담을 한눈에 알아볼 '짧은 한국어 제목'(공백 포함 20자 이내, 문장부호 없이).
   핵심 증상 중심으로. 예: "발작 증상 응급 상담", "기침·콧물 상담", "다리 절뚝임 문의".

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
  "variables":{{"<정의된 변수>":"<enum값>"}},
  "enough_to_triage": false,
  "urgency_tier": "critical|high|normal",
  "chief_complaint":"주증상(명사, 충분할 때)",
  "keywords":["키워드"],
  "summary":"한 줄 평서형 요약(SOAP S, '~이다/~한다' 명사나열 금지)",
  "onset":"발병 시점(알면)",
  "rag_query":"보호자 말투의 자연스러운 증상 서술 한 문장(검색용)",
  "title":"상담 목록용 짧은 제목(20자 이내)"}}"""


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


# 의심질환 = RAG 검색 결과(수의사 답변)에서 '실제로 적힌 질환'만. 꾸며내지 않는다.
#  검색은 top-k를 그냥 가져오고(threshold 컷 X), LLM이 증상에 맞는 것만 골라(리랭크) 질환을 추린다.
_SUSPECT_GEN_SYSTEM = """너는 동물병원 문진 도우미야. {pet_name}의 증상 문진을 막 마쳤어.

[{pet_name}의 증상(보호자가 말한 것)]
{symptoms}

[검색된 비슷한 사례의 수의사 답변들 — 이 중 증상과 '맞는 것만' 고르고, 동떨어진 건 버려]
{answers}

할 일:
1) 위 '수의사 답변'에 실제로 적힌 질환 중, {pet_name}의 증상과 맞는 것을 골라 suspected_diseases(한국어)에 담아라.
   - 답변에 없는 질환을 절대 지어내지 마라. 증상과 맞는 게 없으면 빈 배열([]).
2) message = 보호자에게 보낼 따뜻한 메시지(사람처럼 자연스럽게, 매번 다른 표현):
   - suspected가 있으면 "~일 수 있어요/가능성도 있어요" 톤으로 부드럽게(단정 X).
     비었으면 증상은 잘 들었다고만 하고 "조금 더 살펴봐야 한다"고 솔직히.
   - 확정 진단이 아니라 참고이며 정확한 판단은 수의사 진료가 필요하다고 분명히.
   - 마지막은 "예약을 도와드릴까요?"로 마무리. '응급·위험·큰일' 같은 겁주는 말 금지.
   - ★ 읽기 쉽게 줄바꿈(\\n\\n)으로 2~3 덩어리로 나눠라. 한 문단으로 길게 이어 쓰지 마.
     예) (의심 가능성 안내)\\n\\n(확정 아님·수의사 진료 권유)\\n\\n예약을 도와드릴까요?

JSON으로만 답해:
{{"suspected_diseases":["한국어 질환명"], "message":"여러 줄(\\n\\n)로 나눈 메시지 본문"}}"""


def build_suspected_confirm_prompt(pet_name: str, symptoms: str,
                                   answers: list[str]) -> str:
    ans = "\n\n".join(f"- {a}" for a in (answers or []) if a) or "(검색 결과 없음 — 질환은 빈 배열로)"
    return _SUSPECT_GEN_SYSTEM.format(
        pet_name=pet_name or "아이", symptoms=(symptoms or "").strip() or "(증상 정보 부족)", answers=ans,
    )


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
