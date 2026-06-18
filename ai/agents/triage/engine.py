"""문진 점수 엔진 (경량) — vet_triage.json 점수표를 읽어 결정론으로 채점.

옛 scoring.py(삭제됨)를 되살린 게 아니라, JSON의 field_scoring / urgency_rules만
직접 읽는 새 경량 버전이다. LLM은 '슬롯 추출·질문'만 하고, 점수/등급은 여기서 정한다.
"""
from __future__ import annotations

import functools
import json
from pathlib import Path

# vet_triage.json 위치 후보(실행 cwd가 backend거나 repo 루트일 수 있어 여러 곳 시도)
_CANDIDATES = [
    Path(__file__).resolve().parents[3] / "backend" / "data" / "triage" / "vet_triage.json",
    Path("backend/data/triage/vet_triage.json"),
    Path("data/triage/vet_triage.json"),
]

_URG_NUM = {"RED": 1, "ORANGE": 2, "YELLOW": 3, "GREEN": 4}


@functools.lru_cache(maxsize=1)
def _kb() -> dict:
    for p in _CANDIDATES:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    raise FileNotFoundError("vet_triage.json 을 찾을 수 없습니다.")


@functools.lru_cache(maxsize=1)
def _sections() -> dict[str, dict]:
    return {s["id"]: s for s in _kb().get("sections", [])}


def section_reference() -> str:
    """LLM에게 줄 '무엇을 물을 수 있는지' 요약 — 섹션별 항목(enum) + 핵심필드."""
    lines = []
    for s in _kb().get("sections", []):
        fs = s.get("field_schema") or {}
        fields = "; ".join(
            f"{f}[{'|'.join(v)}]" if isinstance(v, list) else f"{f}"
            for f, v in fs.items()
        )
        comp = ", ".join(s.get("completion_fields") or [])
        lines.append(f"- {s['id']} ({s.get('label', '')}): {fields}  ※핵심: {comp}")
    return "\n".join(lines)


def completion_fields(section_id: str) -> list[str]:
    return (_sections().get(section_id) or {}).get("completion_fields") or []


def score(section_id: str, fields: dict) -> int:
    """field_scoring으로 합산. 미수집/모르는 값은 무시(=0 가산 안 함)."""
    sec = _sections().get(section_id) or {}
    table = sec.get("field_scoring") or {}
    total = 0
    for f, v in (fields or {}).items():
        col = table.get(f)
        if col and v in col:
            total += col[v]
    return total


def urgency(section_id: str, total: int, red_flag: bool) -> str:
    """urgency_rules를 위에서부터 평가해 첫 일치 등급. RED는 red_flag에서만."""
    sec = _sections().get(section_id) or {}
    for rule in sec.get("urgency_rules") or []:
        cond = rule.get("condition", "")
        if cond == "red_flag == true":
            if red_flag:
                return rule["urgency"]
        elif ">=" in cond:
            try:
                if total >= int(cond.split(">=")[1]):
                    return rule["urgency"]
            except ValueError:
                continue
        elif "<" in cond:
            try:
                if total < int(cond.split("<")[1]):
                    return rule["urgency"]
            except ValueError:
                continue
    return "GREEN"


def urgency_num(u: str) -> int:
    return _URG_NUM.get(u, 4)
