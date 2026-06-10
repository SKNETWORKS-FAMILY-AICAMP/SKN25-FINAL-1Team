"""트리아지 decision tree walk 헬퍼 + 경로 열거기 (eval 공용).

엔진 내부 구현에 의존하지 않고, 공개 API(get_node/advance/compute_urgency)만 써서
- 특정 pill 경로를 따라 walk 하고(walk),
- KB의 모든 섹션을 훑어 root→leaf 경로를 자동 열거한다(enumerate_paths).

이 모듈 자체는 '정답'을 정의하지 않는다. 정답(레퍼런스)은 reference_scorer.py가,
실제 구현(SUT)은 ai.triage.engine 이 담당하며, test_determinism.py 가 둘을 대조한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

# app(backend/) 과 ai(repo root) 둘 다 import 가능하도록 경로 추가.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root (ai 패키지)

from ai.triage import engine as te  # noqa: E402


def walk(path: list[str], species: str | None = None, gender: str | None = None):
    """START_NODE에서 path(=pill value/label 순서)를 따라 walk.

    Returns: (answers, section). answers는 선택된 pill dict 리스트(레퍼런스/엔진 공용 입력).
    """
    answers: list[dict] = []
    cur = te.START_NODE
    section = te.get_node(cur).get("section_id")
    for step in path:
        node = te.get_node(cur)
        pill = next(
            (p for p in node["pills"] if p.get("value") == step or p.get("label") == step),
            None,
        )
        if pill is None:
            raise AssertionError(f"{cur}에 '{step}' pill 없음")
        answers.append(pill)
        if cur == te.START_NODE:
            section = pill.get("next_section") or pill.get("value")
        nxt = te.advance(cur, [pill])
        if nxt is None:
            break
        cur = nxt
    return answers, section


def _section_entry(section_value: str) -> str | None:
    """START에서 섹션 pill을 골라 진입 노드 id 반환."""
    start = te.get_node(te.START_NODE)
    pill = next((p for p in start["pills"] if p.get("value") == section_value), None)
    if pill is None:
        return None
    return te.advance(te.START_NODE, [pill])


def enumerate_paths(max_per_section: int = 4, max_depth: int = 8) -> list[dict]:
    """KB 모든 섹션을 DFS 하여 root→leaf pill-value 경로를 자동 수집한다.

    leaf = pill에 'next'가 없거나 red_flag(엔진이 즉시 종료)인 지점.
    각 경로는 {section, path:[section_value, ...pill_values]} 형태로, walk()에 바로 투입 가능.
    무한 트리 방지를 위해 섹션당 max_per_section개, 깊이 max_depth로 제한한다.
    """
    from ai.triage.kb import load_triage_kb

    kb = load_triage_kb()
    sections = [s.get("id") for s in kb.get("sections", [])]
    collected: list[dict] = []

    for sec in sections:
        entry = _section_entry(sec)
        if not entry:
            continue
        found: list[list[str]] = []

        def dfs(node_id: str, acc: list[str], depth: int):
            if len(found) >= max_per_section or depth > max_depth:
                return
            node = te.get_node(node_id)
            if not node:
                found.append(list(acc))
                return
            for pill in node.get("pills", []):
                if len(found) >= max_per_section:
                    return
                val = pill.get("value")
                new_acc = acc + [val]
                # 종료 조건: red_flag(즉시 종료) 또는 next 없음(leaf)
                if pill.get("red_flag") or not pill.get("next"):
                    found.append(new_acc)
                else:
                    dfs(pill["next"], new_acc, depth + 1)

        dfs(entry, [], 0)
        for p in found:
            collected.append({"section": sec, "path": [sec, *p]})

    return collected
