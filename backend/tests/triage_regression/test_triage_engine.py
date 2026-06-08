"""triage_engine 결정론 walker 단위테스트.

scoring_engine pseudocode와 walk 결과(점수·urgency)가 일치하는지 고정한다.
pytest 없이도 `python3 tests/triage_regression/test_triage_engine.py` 로 실행 가능.
"""
from __future__ import annotations

from ai.triage import engine as te


def _walk(node_id: str, path: list[str], species: str | None = None,
          gender: str | None = None):
    """node_id에서 시작해 path의 value/label을 순서대로 선택하며 walk."""
    answers: list[dict] = []
    section = te.get_node(node_id).get("section_id")
    cur = node_id
    for step in path:
        node = te.get_node(cur)
        pill = next(
            (p for p in node["pills"] if p.get("value") == step or p.get("label") == step),
            None,
        )
        assert pill is not None, f"{cur}에 '{step}' pill 없음"
        answers.append(pill)
        if cur == te.START_NODE:
            section = pill.get("next_section") or pill.get("value")
        nxt = te.advance(cur, [pill])
        if nxt is None:
            break
        cur = nxt
    return te.compute_urgency(answers, species, section, gender), te.to_collected_info(
        answers, species, section, gender
    )


def test_index_and_start():
    assert te.get_node(te.START_NODE) is not None
    assert te.get_node("Q_RESP_01") is not None
    assert te.advance(te.START_NODE, [{"value": "GI", "next_section": "GI"}]) == "Q_GI_01"
    print("✓ index/start/section-entry")


def test_red_flag_immediate():
    u, ci = _walk(te.START_NODE, ["RESPIRATORY", "severe"])
    assert u["urgency"] == "RED" and u["urgency_level_num"] == 1, u
    assert ci["red_flags"], ci
    print("✓ red_flag → RED(1)")


def test_yellow_path():
    u, _ = _walk(te.START_NODE, ["RESPIRATORY", "cough_only", "occasional", "acute"])
    assert u["total_score"] == 5, u
    assert u["urgency"] == "YELLOW" and u["urgency_level_num"] == 3, u
    print("✓ score=5 → YELLOW(3)")


def test_orange_path():
    u, _ = _walk(te.START_NODE, ["RESPIRATORY", "cough_only", "persistent", "recent"])
    assert u["total_score"] == 7, u
    assert u["urgency"] == "ORANGE" and u["urgency_level_num"] == 2, u
    print("✓ score=7 → ORANGE(2)")


def test_species_modifier_cat_respiratory():
    path = ["RESPIRATORY", "cough_only", "occasional", "acute"]
    dog, _ = _walk(te.START_NODE, path, species="dog")
    cat, _ = _walk(te.START_NODE, path, species="cat")
    assert cat["total_score"] == dog["total_score"] + 1, (dog, cat)
    print(f"✓ cat 보정: dog={dog['total_score']} cat={cat['total_score']}")


def test_match_pill():
    p = te.match_pill("Q_RESP_01", "입을 벌리고 헐떡이거나 거의 못 쉬어요")
    assert p and p["value"] == "severe", p
    assert te.match_pill("Q_RESP_01", "전혀 상관없는 말") is None
    print("✓ match_pill 라벨 정확매칭")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("\n모든 테스트 통과 ✅")
