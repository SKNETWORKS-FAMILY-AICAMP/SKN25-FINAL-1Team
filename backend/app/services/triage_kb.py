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


def detect_red_flag(text: str) -> dict | None:
    """결정론적 red flag 감지 — 사용자 발화/선택 텍스트를 라벨 인덱스와 매칭.

    pill 클릭(라벨 그대로 전송) 또는 자유 텍스트가 red flag 라벨과 정확/포함
    일치하면 {"id", "label", "source": "deterministic"} 반환, 아니면 None.
    오탐 방지: 정규화된 라벨 전체가 발화에 포함될 때만 매칭.
    """
    norm_text = _normalize(text)
    if len(norm_text) < 4:
        return None

    for fid, norm_label, raw_label in _red_flag_label_index():
        if len(norm_label) < 4:
            continue
        if norm_label in norm_text or norm_text in norm_label:
            return {"id": fid, "label": raw_label, "source": "deterministic"}
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
