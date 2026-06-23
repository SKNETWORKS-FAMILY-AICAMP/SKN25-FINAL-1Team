"""대화 메모리(맥락 기억) 평가 — '이 챗봇이 내 이전 말을 기억한다고 느끼는가'.

8개 카테고리 × ~12개 = 100개의 '실제 보호자 말투' 발화를, 각 카테고리에 맞는
직전 대화(맥락)를 깔고 그 다음 턴으로 BOOKED 오케스트레이터에 넣는다.
짧은 긍정/부정·애매·사진후속 발화는 맥락 없이는 의미가 없으므로, 맥락을 함께 줘야
'기억하는지'가 드러난다.

각 케이스마다:
  - 현재 라우팅 (route())
  - 현재 답변 (run_turn 결과 reply / quick_replies)
  - 기대 답변 (LLM 저지가 생성)
  - 메모리 점수 1~5 (5=직전 맥락을 분명히 활용, 1=맥락 무시/되물음/모순)  ★핵심 지표★

실행(도커):
  docker cp backend/scripts/run_memory_eval.py docker-backend-1:/app/backend/scripts/
  docker exec -w /app/backend docker-backend-1 \
    python scripts/run_memory_eval.py --out /tmp/memory_eval.json --html /tmp/memory_eval.html
  docker cp docker-backend-1:/tmp/memory_eval.json backend/data/validation/
  docker cp docker-backend-1:/tmp/memory_eval.html backend/data/validation/
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))          # backend/
sys.path.insert(0, str(HERE.parent.parent))   # repo root (ai.*)

import ai.orchestrator.graph as graph_mod  # noqa: E402
from ai.agents.followup_filter import repository as followup_repo  # noqa: E402
from ai.orchestrator.contracts import Flow, Phase, SessionContext  # noqa: E402
from ai.llm import call_llm_json  # noqa: E402

DEFAULT_OUT = HERE.parent / "data" / "validation" / "memory_eval_report.json"
DEFAULT_HTML = HERE.parent / "data" / "validation" / "memory_eval_report.html"

PET = {"name": "뽀미", "species": "dog"}

# ── 카테고리별 '직전 대화'(history) — 발화가 맥락 속에서 평가되게 한다. ──
# 마지막은 봇 발화여야, 다음 사용자 발화가 '응답'이 된다.
CONTEXTS: dict[str, list[dict]] = {
    "짧은 긍정": [
        {"role": "user", "content": "어제 중성화 수술하고 집에 데려왔어요. 수술 부위가 좀 부었어요."},
        {"role": "assistant", "content": "수술 부위가 부었군요. 수의사 선생님이 보실 수 있게 남겨둘게요. 혹시 아이가 실밥 부위를 자꾸 핥으려고 하나요?"},
    ],
    "짧은 부정": [
        {"role": "user", "content": "어제 중성화 수술했는데 실밥 부위가 신경 쓰여요."},
        {"role": "assistant", "content": "남겨둘게요. 혹시 그 부위에서 진물이 나거나 빨갛게 부어오른 곳이 있나요?"},
    ],
    "예약 질문": [
        {"role": "user", "content": "어제 수술하고 내일 경과 보러 가기로 예약했어요."},
        {"role": "assistant", "content": "네, 경과 잘 챙기고 계시네요. 상태 변화 있으면 또 알려주세요."},
    ],
    "수의사 질문": [
        {"role": "user", "content": "어제 중성화 수술 받았어요. 부기가 조금 있네요."},
        {"role": "assistant", "content": "부기가 있군요. 남겨둘게요. 더 궁금하신 점 있으세요?"},
    ],
    "사진 후속 질문": [
        {"role": "user", "content": "수술 부위 사진 한 장 보냈어요."},
        {"role": "assistant", "content": "사진 잘 봤어요. 부기가 약간 있지만 심해 보이진 않네요. 수의사 선생님이 보실 수 있게 남겨둘게요."},
    ],
    "애매한 질문": [
        {"role": "user", "content": "오늘 아이가 한 번 토했어요."},
        {"role": "assistant", "content": "한 번 토했군요. 걱정되셨겠어요. 수의사 선생님이 보실 수 있게 남겨둘게요."},
    ],
    "감정 표현": [
        {"role": "user", "content": "수술하고 나서 밥도 잘 안 먹고 축 처져 있어요."},
        {"role": "assistant", "content": "기운 없어 보이면 마음이 많이 쓰이시죠. 말씀해주신 상태는 남겨둘게요."},
    ],
    "잡담": [
        {"role": "user", "content": "어제 수술하고 오늘은 좀 잠잠해요."},
        {"role": "assistant", "content": "다행이에요. 상태 변화 있으면 또 편하게 알려주세요."},
    ],
}

# 카테고리별 기대 라우팅(러프) — 자동 점검용. 메모리 점수는 LLM 저지가 매긴다.
EXPECTED_ROUTE = {
    "짧은 긍정": "followup_filter", "짧은 부정": "followup_filter",
    "예약 질문": "followup_filter", "수의사 질문": "reception",
    "사진 후속 질문": "followup_filter", "애매한 질문": "followup_filter",
    "감정 표현": "followup_filter", "잡담": "followup_filter",
    "P0 회귀": "followup_filter", "P1 사진후속": "followup_filter",
    "P2 예약병원": "followup_filter", "P2 취소문의": "followup_filter", "P2 취소실행": "followup_filter",
    "P3 관리방법": "followup_filter", "P3 감정": "followup_filter",
}


_CLARIFY_PHRASES = ("무엇을 도와드릴까요", "관리 방법을 묻는", "상태를 알려주시는 건")


def _p2_eval(check: str, reply: str, events: list) -> bool | None:
    """P2/P3 결정론 검증. check 없으면 None(점검 안 함)."""
    if not check:
        return None
    if check == "hospital":  # 시간 안내(confirmed_time fallback)로 새지 않아야 통과
        return ("확정된 예약 정보를 찾지" not in reply) and ("예약 시간은" not in reply)
    if check == "no_cancel":  # 문의/가정형은 취소·재예약 이벤트 금지
        return ("cancel_request" not in events) and ("rebook_request" not in events)
    if check == "cancel":  # 실행형은 취소 이벤트 발생
        return "cancel_request" in events
    if check == "care":  # 관리방법 질문 → clarify 금지(상태 되묻기 금지)
        return not any(p in reply for p in _CLARIFY_PHRASES)
    if check == "emotion":  # 감정 표현 → clarify 금지 + 공감 표현 포함
        return (not any(p in reply for p in _CLARIFY_PHRASES)) and any(
            w in reply for w in ("걱정", "마음", "불안", "괜찮", "안심", "놀라", "속상", "신경", "겠어요", "이시겠"))
    return None

# 실제 제품에선 직전 '사진 턴'이 orch_state에 짧은 소견을 저장한다. '사진 후속 질문' 카테고리는
# 그 상황을 반영해 최근 소견을 주입한다(맥락 history의 봇 소견과 일치).
CATEGORY_MEDIA = {"사진 후속 질문": "수술 부위에 약간의 부기가 보임"}

# P0 회귀 케이스 — 직전 봇 '질문' + 짧은 답변. 케이스마다 직전 질문이 달라 per-case 맥락을 둔다.
# 검증: '무엇을 도와드릴까요?'가 안 나오고, 직전 질문 주제를 반영하며, route가 followup_filter 유지.
def _q(bot_q: str, user_a: str) -> dict:
    return {
        "category": "P0 회귀",
        "context": [
            {"role": "user", "content": "어제 수술하고 아이 상태 보고 있어요."},
            {"role": "assistant", "content": bot_q},
        ],
        "utterance": user_a,
    }


REGRESSION_CASES = [
    _q("실밥 부위를 자꾸 핥으려고 하나요?", "응 했어요"),
    _q("그 부위에서 진물이 있나요?", "아니요"),
    _q("붓기가 어제보다 더 커졌나요?", "잘 모르겠어요"),
    _q("밥은 잘 먹나요?", "조금 먹어요"),
    _q("수술 부위를 가려워하나요?", "맞아요 계속 긁어요"),
    _q("오늘 토한 적 있나요?", "아직은요"),
]


# P1 사진 후속 — 직전에 사진을 보내 봇이 소견을 말한 뒤의 후속 발화. last_media_summary로 직전 소견을 주입.
def _p1(finding: str, bot_line: str, user_a: str, recent: bool = True) -> dict:
    return {
        "category": "P1 사진후속",
        "context": [
            {"role": "user", "content": "상태 사진 한 장 보냈어요."},
            {"role": "assistant", "content": bot_line},
        ],
        "utterance": user_a,
        "last_media_summary": finding if recent else "",
    }


P1_CASES = [
    _p1("코와 콧등 주변에 붉은 자극이 보임", "보내주신 사진 보니 코와 콧등 주변에 붉은 자극이 보이네요.",
        "방금 보낸 사진 어때요?"),
    _p1("코와 콧등 주변에 붉은 자극이 보임", "보내주신 사진 보니 코와 콧등 주변에 붉은 자극이 보이네요.",
        "저게 왜 생긴 건지 모르겠네 갑자기 생겼어요"),
    _p1("발 부위가 붉어져 보임", "보내주신 사진에서 발 부위가 붉어져 보였어요.",
        "저 부분 더 빨개진 것 같아"),
    _p1("상처 주변이 부어 보임", "보내주신 사진에서 상처 주변이 부어 보였어요.",
        "아까 보낸 거랑 같은 부위야"),
    # 음성 대조군: 최근 사진 소견이 없을 때 — '사진 보내달라' 안내가 맞다(직전 소견 있을 때와 구분).
    _p1("", "네, 상태 변화 있으면 편하게 알려주세요.", "사진 어때요?", recent=False),
]


# P2 예약/병원 맥락 — 단발 의도 분류 정확도(결정론 체크 동반).
#   check: hospital(시간으로 새면 실패) | no_cancel(취소/재예약 이벤트 금지) | cancel(취소 이벤트 발생)
def _p2(cat: str, utterance: str, check: str) -> dict:
    return {"category": cat, "context": [], "utterance": utterance, "last_media_summary": "", "check": check}


P2_CASES = [
    _p2("P2 예약병원", "지금은 어느 병원 예약이야?", "hospital"),
    _p2("P2 예약병원", "어느 병원으로 예약돼 있어?", "hospital"),
    _p2("P2 예약병원", "예약한 병원 이름이 뭐야?", "hospital"),
    _p2("P2 예약병원", "병원 위치 어디야?", "hospital"),
    _p2("P2 취소문의", "취소하면 다시 예약돼요?", "no_cancel"),
    _p2("P2 취소문의", "취소하면 다음에 다시 예약할 수 있죠?", "no_cancel"),
    _p2("P2 취소문의", "취소해도 다시 잡을 수 있어요?", "no_cancel"),
    _p2("P2 취소문의", "취소 가능해요?", "no_cancel"),
    _p2("P2 취소실행", "이 예약 취소해줘", "cancel"),
    _p2("P2 취소실행", "예약 취소할래", "cancel"),
    _p2("P2 취소실행", "지금 예약 없애줘", "cancel"),
]

# P3 대화 품질 — 관리방법/감정 질문은 clarify로 새지 않아야 한다. 고양이가 쥐를 물어온 정상 상황 맥락.
_RAT_CTX = [
    {"role": "user", "content": "고양이가 쥐를 물고 왔어요."},
    {"role": "assistant", "content": "쥐를 물고 온 뒤 걱정되셨겠어요. 지금 상처를 핥거나 아파 보이는지 살펴봐 주세요."},
    {"role": "user", "content": "상처도 없고 멀쩡해요. 그냥 쥐를 물어온 게 문제죠."},
    {"role": "assistant", "content": "상처 없이 멀쩡하군요. 구토나 처짐 같은 변화가 있는지만 봐 주세요."},
    {"role": "user", "content": "구토도 처짐도 없어요. 옆에서 얌전히 그루밍 중이에요."},
    {"role": "assistant", "content": "구토·처짐 없이 얌전히 그루밍 중이군요."},
]


def _p3(cat: str, utterance: str, check: str, ctx: list | None = None) -> dict:
    return {"category": cat, "context": ctx if ctx is not None else _RAT_CTX,
            "utterance": utterance, "last_media_summary": "", "check": check}


P3_CASES = [
    _p3("P3 관리방법", "양치시켜야되나????", "care"),
    _p3("P3 관리방법", "씻겨도 되나?", "care"),
    _p3("P3 관리방법", "그냥 둬도 되나?", "care"),
    _p3("P3 관리방법", "뭐 먹여도 되나?", "care"),
    _p3("P3 감정", "너무 걱정돼", "emotion"),
    _p3("P3 감정", "신경 쓰여 죽겠어", "emotion"),
    _p3("P3 감정", "괜찮은 거 맞아?", "emotion"),
]

# 4턴 반복 방지 시퀀스 — 정상이 쌓이면 체크리스트 멈추고 마무리해야 한다(관찰안내 3연속 금지).
REPETITION_SEQUENCE = [
    "상처는 전혀 없어요.",
    "구토도 안 했어요.",
    "처지지도 않고 잘 놀아요.",
    "그냥 평소처럼 얌전히 그루밍해요.",
]

UTTERANCES: dict[str, list[str]] = {
    "짧은 긍정": ["네 자꾸 핥아요", "응", "맞아요", "네 그래요", "어 했어요", "응 그랬어요",
              "네네", "그런 것 같아요", "맞아요 계속 그래요", "응 어제부터요", "네 좀 그래요", "그러네요"],
    "짧은 부정": ["아니요 안 그래요", "아니", "아니요", "그건 아니에요", "안 그래요", "아니 괜찮아요",
              "아뇨", "별로요", "아직은 아니에요", "아니요 가만히 있어요", "그러진 않아요", "아니 전혀요"],
    "예약 질문": ["내 예약 언제였죠?", "예약 시간 좀 바꾸고 싶어요", "예약 취소돼요?", "더 빠른 시간 없어요?",
              "예약 다시 잡을 수 있나요?", "예약을 오전으로 옮기고 싶어요", "예약 며칠이죠?",
              "예약 변경하려면 어떻게 해요?", "내일 맞죠 예약?", "예약 좀 미룰 수 있어요?",
              "취소하고 다시 잡을래요", "제 예약 확인해주세요"],
    "수의사 질문": ["수술한 선생님 누구세요?", "원장님 성함이 어떻게 되나요?", "어느 수의사분이 보나요?",
               "내일 누가 진료해요?", "선생님 경력이 어떻게 되나요?", "담당 수의사 바꿀 수 있어요?",
               "수의사분 연락처 있어요?", "전문 분야가 뭐예요?", "그 선생님 내일도 계세요?",
               "여자 선생님이세요?", "진료는 누가 보는지 알려주세요", "수의사분 소개 좀 해주세요"],
    "사진 후속 질문": ["아까 보낸 사진 어땠어요?", "사진 보니까 괜찮아요?", "방금 보낸 사진 어떤가요?",
                "사진에 문제 있어 보여요?", "사진 다시 한번 봐주세요", "사진상으로는 어때요?",
                "그 사진 심각한가요?", "사진 보고 어떻게 생각하세요?", "사진 분석 됐어요?",
                "아까 그거 보셨어요?", "사진 보니 부은 거 맞죠?", "사진 결과 알려주세요"],
    "애매한 질문": ["이거 괜찮은 거죠?", "어떻게 해야 해요?", "그냥 둬도 돼요?", "심각한가요?",
              "그거 어떡하죠?", "괜찮겠죠?", "지켜봐도 될까요?", "병원 가야 해요?",
              "이대로 두면 안 되나요?", "더 나빠지면 어떡해요?", "지금 뭐 해줘야 해요?", "걱정 안 해도 되죠?"],
    "감정 표현": ["너무 걱정돼요", "무서워요", "마음이 안 놓여요", "다행이에요 정말", "눈물 나요",
              "불안해서 잠도 안 와요", "고마워요 정말", "속상해요", "겁이 나요", "안심이 되네요",
              "괜히 미안한 마음이 들어요", "너무 힘드네요"],
    "잡담": ["오늘 날씨 좋네요", "심심해요", "뭐 하고 계세요?", "주말에 뭐 하세요?", "당신 이름이 뭐예요?",
           "혹시 AI세요?", "점심 뭐 드셨어요?", "노래 추천해줘요", "재밌는 얘기 해줘요",
           "로또 번호 좀 알려줘요", "축구 좋아하세요?", "그냥 한번 말 걸어봤어요"],
}


# ── 가로채기(라우팅 기록 + DB 없는 저장 스텁) ──
_routed = {"agent": None}
_orig_route = graph_mod.route


async def _traced_route(ctx):
    agent = await _orig_route(ctx)
    _routed["agent"] = agent
    return agent


_save_n = {"n": 0}


async def _stub_save(db, **kw):
    _save_n["n"] += 1
    return SimpleNamespace(followupid=_save_n["n"])


def _ctx(msg: str, history: list[dict], last_media_summary: str = "", attachments=None,
         state: dict | None = None) -> SessionContext:
    st = state or {}
    return SessionContext(
        session_id=1, userid=1, petid=1, pet_info=PET,
        hospitalid=1, emrid=1, scheduleid=1,
        user_message=msg, attachments=attachments or [], history=list(history),
        phase=Phase.BOOKED, active_flow=Flow.IDLE,
        last_media_summary=last_media_summary, db=None,
        followup_summary=st.get("followup_summary", ""),
        last_followup_reply_kind=st.get("last_followup_reply_kind", ""),
        asked_followup_fields=st.get("asked_followup_fields", []),
    )


async def run_repetition() -> dict:
    """4턴 동안 정상이 쌓일 때 체크리스트('~봐 주세요')를 멈추는지 검사."""
    history = list(_RAT_CTX)
    state: dict = {}
    turns = []
    for i, msg in enumerate(REPETITION_SEQUENCE, 1):
        _routed["agent"] = None
        result = await graph_mod.run_turn(_ctx(msg, history, state=state))
        reply = result.reply or ""
        patch = result.state_patch or {}
        for k in ("followup_summary", "last_followup_reply_kind", "asked_followup_fields"):
            if k in patch:
                state[k] = patch[k]
        obs = any(reply.rstrip(".!?。！？ ").endswith(e) for e in
                  ("살펴봐 주세요", "봐 주세요", "지켜봐 주세요", "확인해 주세요", "살펴봐주세요", "봐주세요"))
        turns.append({"turn": i, "user_message": msg, "reply": reply,
                      "reply_kind": patch.get("last_followup_reply_kind", ""), "obs_ending": obs})
        history.append({"role": "user", "content": msg})
        history.append({"role": "assistant", "content": reply})
        print(f"  [반복{i}] obs={obs} kind={patch.get('last_followup_reply_kind','')} :: {msg} → {reply[:50]}",
              file=sys.stderr)
    obs_streak_end = sum(1 for t in turns if t["obs_ending"])
    # 합격: 마지막 턴이 관찰지시로 끝나지 않음(체크리스트 멈춤) + 관찰종결이 4턴 내내는 아님.
    passed = (not turns[-1]["obs_ending"]) and obs_streak_end < 4
    return {"turns": turns, "obs_ending_count": obs_streak_end, "passed": passed}


async def _run_one(category: str, utterance: str, context: list[dict],
                   last_media_summary: str = "", check: str = "") -> dict:
    # '사진 후속 질문'은 직전에 사진을 보낸 맥락이라 첨부는 새로 안 붙인다(과거 사진을 '기억'하는지가 핵심).
    _routed["agent"] = None
    try:
        result = await graph_mod.run_turn(_ctx(utterance, context, last_media_summary))
        reply = result.reply or ""
        quick = result.quick_replies or []
        events = [e.get("type") for e in (result.events or [])]
        reply_kind = (result.state_patch or {}).get("last_followup_reply_kind", "")
        err = None
    except Exception as e:  # noqa: BLE001
        reply, quick, events, reply_kind, err = "", [], [], "", f"{type(e).__name__}: {e}"
    obs_ending = any(reply.rstrip(".!?。！？ ").endswith(e) for e in
                     ("살펴봐 주세요", "봐 주세요", "지켜봐 주세요", "확인해 주세요", "살펴봐주세요", "봐주세요"))
    return {
        "category": category, "utterance": utterance, "context": context,
        "last_media_summary": last_media_summary,
        "routed": _routed["agent"], "reply": reply, "quick_replies": quick,
        "events": events, "reply_kind": reply_kind, "obs_ending": obs_ending,
        "expected_route": EXPECTED_ROUTE[category],
        "route_ok": _routed["agent"] == EXPECTED_ROUTE[category],
        "clarify_leak": any(p in reply for p in _CLARIFY_PHRASES),
        "no_photo_leak": any(p in reply for p in ("사진이 없", "사진을 보내", "사진을 다시")) and bool(last_media_summary),
        "p2_check": check or None,
        "p2_pass": _p2_eval(check, reply, events),
        "error": err,
    }


JUDGE_PROMPT = """너는 반려동물 챗봇의 '대화 메모리(맥락 기억)' 평가자다.
핵심 질문: **보호자 입장에서, 이 챗봇이 '내 이전 말을 기억한다'고 느껴지는가?**

[직전 대화(맥락)]
{context}

[이번 보호자 발화]
{utterance}

[챗봇이 라우팅한 담당] {routed}
[챗봇의 실제 답변]
{reply}

평가 기준(memory_score, 1~5):
- 5: 직전 맥락(앞서 말한 증상/사진/질문)을 분명히 이어받아 자연스럽게 답함. 기억하는 게 확실히 느껴짐.
- 4: 맥락을 대체로 반영하나 약간 일반적.
- 3: 틀리진 않지만 맥락 없이도 할 수 있는 일반적 답변(기억하는지 알 수 없음).
- 2: 맥락을 거의 무시. 방금 한 말을 또 묻거나 흐름이 끊김.
- 1: 맥락을 완전히 잊음/모순됨(예: 이미 보낸 사진을 다시 보내라거나, 방금 답한 걸 처음 듣는 듯).

또한 짧은 발화('응','아니요' 등)는 직전 봇 질문에 대한 답으로 올바르게 해석했는지가 핵심이다.

JSON만 출력:
{{
  "memory_score": 1~5 정수,
  "feels_remembered": "yes" | "partial" | "no",
  "expected_reply": "이 상황에서 이상적인 한국어 답변 한두 문장",
  "routing_appropriate": true | false,
  "reason": "짧은 한국어 근거(맥락을 살렸는지/놓쳤는지 구체적으로)"
}}"""


def _fmt_ctx(history: list[dict]) -> str:
    return "\n".join(f"{'보호자' if m['role']=='user' else '챗봇'}: {m['content']}" for m in history)


async def _judge(rec: dict) -> dict:
    prompt = JUDGE_PROMPT.format(
        context=_fmt_ctx(rec.get("context") or []),
        utterance=rec["utterance"], routed=rec["routed"], reply=rec["reply"] or "(빈 답변)")
    try:
        out = await call_llm_json(prompt)
        return {
            "memory_score": int(out.get("memory_score") or 3),
            "feels_remembered": out.get("feels_remembered") or "partial",
            "expected_reply": out.get("expected_reply") or "",
            "routing_appropriate": bool(out.get("routing_appropriate")),
            "reason": out.get("reason") or "",
        }
    except Exception as e:  # noqa: BLE001
        return {"memory_score": 0, "feels_remembered": "judge_error",
                "expected_reply": "", "routing_appropriate": False, "reason": f"{type(e).__name__}: {e}"}


async def main_async(args):
    import os
    print(f"OPENAI_API_KEY set? {'yes' if os.getenv('OPENAI_API_KEY') else 'NO'}", file=sys.stderr)
    graph_mod.route = _traced_route
    followup_repo.save_followup = _stub_save

    def _reg(rc):
        return (rc["category"], rc["utterance"], rc["context"],
                rc.get("last_media_summary", ""), rc.get("check", ""))

    if args.only_regression:
        cases = [_reg(rc) for rc in (REGRESSION_CASES + P1_CASES + P2_CASES + P3_CASES)]
    else:
        cases = [(c, u, CONTEXTS[c], CATEGORY_MEDIA.get(c, ""), "") for c in UTTERANCES for u in UTTERANCES[c]]
        cases += [_reg(rc) for rc in (REGRESSION_CASES + P1_CASES + P2_CASES + P3_CASES)]
    print(f"▶ {len(cases)}개 케이스 실행(순차 run_turn → 동시 judge)", file=sys.stderr)

    # 1) run_turn은 전역 _routed 공유라 순차 실행(라우팅 캡처 안전).
    recs = []
    for i, (c, u, ctx_hist, lms, chk) in enumerate(cases, 1):
        rec = await _run_one(c, u, ctx_hist, lms, chk)
        recs.append(rec)
        leak = " ⚠clarify" if rec["clarify_leak"] else ""
        leak += " ⚠no_photo" if rec["no_photo_leak"] else ""
        if rec["p2_pass"] is False:
            leak += " ✗P2"
        print(f"  [{i:3d}/{len(cases)}] {c} · route={rec['routed']}{leak} :: {u[:24]} → {rec['reply'][:40]}",
              file=sys.stderr)

    # 2) judge는 동시 실행.
    sem = asyncio.Semaphore(args.concurrency)

    async def guarded(rec):
        async with sem:
            j = await _judge(rec)
            rec.update(j)
            return rec

    recs = await asyncio.gather(*(guarded(r) for r in recs))

    # 집계
    by_cat = defaultdict(list)
    for r in recs:
        by_cat[r["category"]].append(r)
    cat_summary = {}
    for c, rs in by_cat.items():
        scored = [r["memory_score"] for r in rs if r["memory_score"] > 0]
        cat_summary[c] = {
            "n": len(rs),
            "avg_memory": round(sum(scored) / max(len(scored), 1), 2),
            "feels": dict(Counter(r["feels_remembered"] for r in rs)),
            "route_ok": sum(1 for r in rs if r["route_ok"]),
            "clarify_leak": sum(1 for r in rs if r["clarify_leak"]),
            "no_photo_leak": sum(1 for r in rs if r.get("no_photo_leak")),
            "obs_ending": sum(1 for r in rs if r.get("obs_ending")),
            "p2_pass": sum(1 for r in rs if r.get("p2_pass") is True),
            "p2_total": sum(1 for r in rs if r.get("p2_pass") is not None),
            "routed_dist": dict(Counter(r["routed"] for r in rs)),
        }
    all_scored = [r["memory_score"] for r in recs if r["memory_score"] > 0]
    reply_kinds = Counter(r.get("reply_kind") for r in recs if r.get("reply_kind"))
    overall = {
        "cases": len(recs),
        "avg_memory": round(sum(all_scored) / max(len(all_scored), 1), 2),
        "feels": dict(Counter(r["feels_remembered"] for r in recs)),
        "low_memory": sum(1 for r in recs if 0 < r["memory_score"] <= 2),
        "clarify_leak": sum(1 for r in recs if r["clarify_leak"]),
        "no_photo_leak": sum(1 for r in recs if r.get("no_photo_leak")),
        "obs_ending": sum(1 for r in recs if r.get("obs_ending")),
        "reply_kind_dist": dict(reply_kinds),
    }
    repetition = await run_repetition()
    report = {"meta": {"generated_at_unix": int(time.time()), "pet": PET},
              "overall": overall, "by_category": cat_summary,
              "repetition_check": repetition, "cases": recs}

    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.html:
        Path(args.html).write_text(render_html(report), encoding="utf-8")
    graph_mod.route = _orig_route

    print("\n=== 카테고리별 메모리 점수(1~5) ===", file=sys.stderr)
    for c in [*UTTERANCES, "P0 회귀", "P1 사진후속", "P2 예약병원", "P2 취소문의", "P2 취소실행",
              "P3 관리방법", "P3 감정"]:
        if c not in cat_summary:
            continue
        s = cat_summary[c]
        p2 = f"  P2/P3통과 {s['p2_pass']}/{s['p2_total']}" if s["p2_total"] else ""
        print(f"  {c:>9}: 평균 {s['avg_memory']}  feels={s['feels']}  route_ok {s['route_ok']}/{s['n']}"
              f"  clarify누수 {s['clarify_leak']}  obs종결 {s.get('obs_ending', 0)}{p2}", file=sys.stderr)
    print(f"\n전체 평균 메모리 {overall['avg_memory']}/5 · 낮음(≤2) {overall['low_memory']}건 "
          f"· clarify누수 {overall['clarify_leak']}건 · no_photo누수 {overall['no_photo_leak']}건 "
          f"· obs종결 {overall['obs_ending']}건", file=sys.stderr)
    print(f"reply_kind 분포: {overall['reply_kind_dist']}", file=sys.stderr)
    print(f"4턴 반복 테스트: {'통과' if repetition['passed'] else '실패'} "
          f"(관찰종결 {repetition['obs_ending_count']}/4)", file=sys.stderr)
    print(f"✓ {args.out}" + (f" · {args.html}" if args.html else ""), file=sys.stderr)


def render_html(report: dict) -> str:
    data = json.dumps(report, ensure_ascii=False)
    return """<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<title>대화 메모리 평가</title><style>
*{box-sizing:border-box;margin:0;padding:0}body{font-family:-apple-system,'Apple SD Gothic Neo',sans-serif;background:#f6f7f9;color:#1a1a1a;font-size:14px;line-height:1.5;padding:24px;max-width:1080px;margin:0 auto}
h1{font-size:22px}.sub{color:#6b7280;margin:4px 0 16px;font-size:13px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:16px}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:12px 14px}.card .n{font-size:22px;font-weight:700}.card .l{font-size:12px;color:#6b7280}
.card.good .n{color:#16a34a}.card.warn .n{color:#d97706}.card.bad .n{color:#dc2626}
h2{font-size:16px;margin:22px 0 8px}.catrow{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px}
.chip{font-size:12px;padding:4px 10px;border-radius:999px;font-weight:600;border:1px solid #e5e7eb;background:#fff;cursor:pointer}
.chip.on{background:#111827;color:#fff;border-color:#111827}
.case{background:#fff;border:1px solid #e5e7eb;border-radius:10px;margin-bottom:8px;padding:12px 14px}
.case.s12{border-left:4px solid #dc2626}.case.s3{border-left:4px solid #d97706}.case.s45{border-left:4px solid #16a34a}
.row{margin:3px 0}.who{font-weight:700;font-size:11px;color:#9ca3af;margin-right:6px}
.usr{color:#111827}.bot{color:#1d4ed8}.exp{color:#047857}
.meta{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;align-items:center}
.b{font-size:11px;padding:2px 8px;border-radius:999px;font-weight:600}
.bl{background:#eff6ff;color:#2563eb}.gy{background:#f3f4f6;color:#6b7280}.gr{background:#f0fdf4;color:#16a34a}.am{background:#fffbeb;color:#d97706}.rd{background:#fef2f2;color:#dc2626}
.pill{background:#eef2ff;color:#4f46e5;border:1px solid #c7d2fe;border-radius:999px;padding:2px 9px;font-size:11px;margin-right:4px}
.ctx{font-size:12px;color:#6b7280;background:#fafafa;border-radius:6px;padding:6px 8px;margin-bottom:6px;white-space:pre-wrap}
.reason{font-size:12px;color:#6b7280;margin-top:4px}
</style></head><body>
<h1>대화 메모리 평가 — "이 챗봇이 내 이전 말을 기억한다고 느끼는가"</h1>
<div class="sub" id="meta"></div><div id="cards" class="cards"></div>
<div class="catrow" id="cats"></div><div id="root"></div>
<script>const DATA=""" + data + """;
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function sc(v){return v<=2?'rd':v===3?'am':'gr'}
function scls(v){return v<=2?'s12':v===3?'s3':'s45'}
function fcls(f){return f==='yes'?'gr':f==='partial'?'am':'rd'}
const o=DATA.overall;
document.getElementById('meta').textContent=`${o.cases}개 케이스 · 전체 평균 메모리 ${o.avg_memory}/5 · 낮음(≤2) ${o.low_memory}건 · feels ${JSON.stringify(o.feels)}`;
let cards=`<div class="card ${o.avg_memory>=4?'good':o.avg_memory>=3?'warn':'bad'}"><div class="n">${o.avg_memory}</div><div class="l">전체 평균 메모리 /5</div></div>`;
cards+=`<div class="card ${o.low_memory>0?'bad':'good'}"><div class="n">${o.low_memory}</div><div class="l">메모리 낮음(≤2)</div></div>`;
for(const [c,s] of Object.entries(DATA.by_category))cards+=`<div class="card ${s.avg_memory>=4?'good':s.avg_memory>=3?'warn':'bad'}"><div class="n">${s.avg_memory}</div><div class="l">${esc(c)} (route_ok ${s.route_ok}/${s.n})</div></div>`;
document.getElementById('cards').innerHTML=cards;
const cats=['(전체)'].concat(Object.keys(DATA.by_category));
let active='(전체)';
function chips(){document.getElementById('cats').innerHTML=cats.map(c=>`<span class="chip ${c===active?'on':''}" onclick="pick('${c}')">${esc(c)}</span>`).join('')}
function pick(c){active=c;chips();render()}
function ctxText(cat){const C=DATA.cases.find(x=>x.category===cat);return ''}
function render(){
 const root=document.getElementById('root');let h='';
 let cur=null;
 DATA.cases.filter(c=>active==='(전체)'||c.category===active).forEach(c=>{
  if(c.category!==cur){cur=c.category;h+=`<h2>${esc(c.category)} — 평균 ${DATA.by_category[c.category].avg_memory}/5</h2>`;}
  h+=`<div class="case ${scls(c.memory_score)}">`;
  h+=`<div class="row"><span class="who">🧑</span><span class="usr">${esc(c.utterance)}</span></div>`;
  h+=`<div class="row"><span class="who">🤖</span><span class="bot">${esc(c.reply)}</span></div>`;
  if(c.quick_replies&&c.quick_replies.length)h+='<div class="row">'+c.quick_replies.map(p=>`<span class="pill">${esc(p)}</span>`).join('')+'</div>';
  if(c.expected_reply)h+=`<div class="row"><span class="who">기대</span><span class="exp">${esc(c.expected_reply)}</span></div>`;
  h+=`<div class="meta"><span class="b ${sc(c.memory_score)}">메모리 ${c.memory_score}/5</span>`;
  h+=`<span class="b ${fcls(c.feels_remembered)}">기억느낌: ${esc(c.feels_remembered)}</span>`;
  h+=`<span class="b ${c.route_ok?'gy':'rd'}">route: ${esc(c.routed)} ${c.route_ok?'':'(기대 '+esc(c.expected_route)+')'}</span>`;
  if(c.events&&c.events.length)h+=`<span class="b gr">${c.events.join(',')}</span>`;
  h+=`</div><div class="reason">${esc(c.reason)}</div></div>`;
 });
 root.innerHTML=h;
}
chips();render();
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--html", default=str(DEFAULT_HTML))
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--only-regression", action="store_true", help="P0 회귀 6케이스만 빠르게 실행")
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
