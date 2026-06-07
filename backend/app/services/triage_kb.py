"""Triage Knowledge Base — vet_triage.json 단일 로더.

`backend/data/triage/vet_triage.json`(수의 트리아지 decision tree·red flag·VTL 감별
기준의 단일 출처)을 메모리에 올려 캐싱하고, red flag 감지에 필요한 접근자를 제공한다.

설계:
- 모든 트리아지 지식(질문/pill/red_flag/scoring)을 코드에 하드코딩하지 않고
  이 JSON 하나에서만 읽는다(단일 출처). 로더는 lru_cache로 1회만 파싱한다.
- red flag 감지(결정론): pill 라벨 정확/포함 매칭 — pill 클릭은 라벨이 그대로
  전송되므로 신뢰 가능. 자유 텍스트의 의미 감지는 chat.py의 LLM 분류가 보완한다.
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

# backend/app/services/triage_kb.py → parents[2] == backend
_KB_PATH = Path(__file__).resolve().parents[2] / "data" / "triage" / "vet_triage.json"


@lru_cache(maxsize=1)
def load_triage_kb() -> dict:
    """vet_triage.json 전체를 dict로 로드(캐싱). 실패 시 빈 dict."""
    try:
        with open(_KB_PATH, encoding="utf-8") as f:
            kb = json.load(f)
        logger.info("[TriageKB] loaded %s (sections=%d, red_flags=%d)",
                    _KB_PATH.name,
                    len(kb.get("sections", [])),
                    len(kb.get("red_flags", {}).get("flags", [])))
        return kb
    except (OSError, json.JSONDecodeError) as e:
        logger.error("[TriageKB] load failed (%s): %s", _KB_PATH, e)
        return {}


def get_red_flags() -> dict:
    """red_flags 섹션(description/trigger_mode/on_trigger/flags) 반환."""
    return load_triage_kb().get("red_flags", {})


def red_flag_trigger() -> dict:
    """red flag 발동 시 동작 정의(urgency/chatbot_message/action). 기본값 포함."""
    on_trigger = get_red_flags().get("on_trigger") or {}
    return {
        "urgency": on_trigger.get("urgency", "RED"),
        "chatbot_message": on_trigger.get(
            "chatbot_message",
            "⚠️ 지금 바로 병원에 연락하거나 내원해 주세요. 생명에 위협이 될 수 있는 응급 상황입니다.",
        ),
        "action": on_trigger.get("action", ""),
    }


# ── red flag 라벨 인덱스 (결정론적 매칭용) ──────────────────────────────
# 상위 red_flags.flags(15개) + sections 내 red_flag:true pill을 모두 모은다.

_EMOJI_RE = re.compile(r"[^\w가-힣]+")
_PAREN_RE = re.compile(r"[\(（].*?[\)）]")


def _normalize(text: str) -> str:
    """이모지·공백·괄호주석 제거 후 비교용 정규화 문자열 반환."""
    if not text:
        return ""
    text = _PAREN_RE.sub("", text)
    text = _EMOJI_RE.sub("", text.lower())
    return text.strip()


@lru_cache(maxsize=1)
def _red_flag_label_index() -> tuple[tuple[str, str, str], ...]:
    """(flag_id, normalized_label, raw_label) 튜플 인덱스 — 상위 flags + section pills."""
    kb = load_triage_kb()
    index: list[tuple[str, str, str]] = []

    for f in kb.get("red_flags", {}).get("flags", []):
        label = f.get("label", "")
        norm = _normalize(label)
        if norm:
            index.append((f.get("id", "RF-?"), norm, label))

    for section in kb.get("sections", []):
        for q in section.get("questions", []):
            for pill in q.get("pills", []):
                if pill.get("red_flag"):
                    label = pill.get("label", "")
                    norm = _normalize(label)
                    if norm:
                        fid = pill.get("vtl_discriminator_id") or f"{section.get('id', '?')}:{pill.get('value', '?')}"
                        index.append((fid, norm, label))

    return tuple(index)


@lru_cache(maxsize=1)
def _red_flag_keyword_index() -> tuple[tuple[str, str, str], ...]:
    """(flag_id, normalized_keyword, raw_label) — red_flags.flags[].keywords.

    KB scoring_engine step1의 'free_text matches red_flags[].keywords → RED'를 구현한다.
    영어 임상용어 키워드는 한국어 발화에 거의 안 잡히고, 한국어 트리거(초콜릿·쥐약 등)만
    실효적으로 매칭된다. 오탐 방지로 정규화 길이 2 이상만 인덱싱한다.
    """
    kb = load_triage_kb()
    index: list[tuple[str, str, str]] = []
    for f in kb.get("red_flags", {}).get("flags", []):
        label = f.get("label", "")
        fid = f.get("id", "RF-?")
        for kw in f.get("keywords", []) or []:
            norm = _normalize(str(kw))
            if len(norm) >= 2:
                index.append((fid, norm, label))
    return tuple(index)


@lru_cache(maxsize=1)
def _flag_meta_by_id() -> dict:
    """flag_id → {chief(명사형 주증상), suspected(의심질환 목록)} (상위 flags 한정)."""
    kb = load_triage_kb()
    return {
        f.get("id"): {"chief": f.get("chief"), "suspected": f.get("suspected") or []}
        for f in kb.get("red_flags", {}).get("flags", [])
    }


def _red_flag_hit(fid: str, raw_label: str, source: str) -> dict:
    """감지 결과 dict — 상위 flag면 chief/suspected를 함께 실어 EMR 요약을 풍부하게 한다."""
    meta = _flag_meta_by_id().get(fid) or {}
    return {
        "id": fid,
        "label": raw_label,
        "source": source,
        "chief": meta.get("chief"),
        "suspected": meta.get("suspected") or [],
    }


def detect_red_flag(text: str) -> dict | None:
    """결정론적 red flag 감지 — 사용자 발화/선택 텍스트를 라벨·키워드 인덱스와 매칭.

    1) red flag 라벨(긴 문장)이 발화에 통째로 포함 → {"source": "deterministic"}
    2) red_flags[].keywords(초콜릿 등 한국어 트리거)가 발화에 포함 → {"source": "keyword"}
    매칭 시 {"id", "label", "source", "chief", "suspected"} 반환, 없으면 None.
    """
    norm_text = _normalize(text)
    if not norm_text:
        return None

    # 1) 라벨 매칭 — "red flag 라벨(긴 문장)이 사용자 발화에 통째로 포함"될 때만.
    #    역방향(발화가 라벨의 부분문자열)은 카테고리 발화("쓰러졌어요")가 더 긴
    #    red flag 라벨("잇몸이 창백하고 쓰러졌어요")에 걸리는 오탐을 일으켜 제외한다.
    #    pill을 그대로 클릭하면 라벨==발화라 forward 매칭으로 정상 동작.
    if len(norm_text) >= 4:
        for fid, norm_label, raw_label in _red_flag_label_index():
            if len(norm_label) < 4:
                continue
            if norm_label in norm_text:
                return _red_flag_hit(fid, raw_label, "deterministic")

    # 2) 키워드 매칭 — KB red_flags[].keywords (초콜릿·쥐약·자일리톨 등)
    for fid, norm_kw, raw_label in _red_flag_keyword_index():
        if norm_kw in norm_text:
            return _red_flag_hit(fid, raw_label, "keyword")
    return None


def red_flag_ids() -> set[str]:
    """유효한 red flag id 집합."""
    return {fid for fid, _, _ in _red_flag_label_index()}


def find_red_flag_label(flag_id: str) -> str | None:
    """flag_id로 라벨 조회."""
    for fid, _, raw_label in _red_flag_label_index():
        if fid == flag_id:
            return raw_label
    return None
