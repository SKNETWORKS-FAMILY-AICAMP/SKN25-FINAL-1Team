"""[정량 평가 1] 트리아지 엔진 — 명세 일치도 + 결정론(재현성).

이 테스트는 **LLM을 전혀 호출하지 않는다.** 따라서 항상 실행 가능하고(무료),
같은 입력이면 항상 같은 결과가 나온다는 것을 *측정으로* 보인다.

두 가지를 정량화한다:
  (A) 명세 일치도(accuracy vs spec): KB 모든 섹션에서 자동 열거한 경로마다
      실제 엔진(engine.compute_urgency) 결과 == 독립 레퍼런스 채점기 결과 인지.
      → "사람이 쓴 명세대로 엔진이 동작하는가"의 차등 검증(self-eval 아님).
  (B) 결정론(variance=0): 동일 입력을 N회 반복 실행해 출력이 100% 동일한지.
      → LLM-only 분류기의 run간 흔들림(test_llm_variance.py)과 대비되는 핵심 지표.

산출물: backend/eval_determinism.json (run_eval.py 가 리포트로 취합).
"""
from __future__ import annotations

import json
from pathlib import Path

from ai.triage import engine as te

from . import reference_scorer as ref
from ._walker import enumerate_paths, walk

# 반복 실행 횟수(결정론 측정용). 순수 함수라 커도 빠름.
_REPEAT = 100
_OUT = Path(__file__).resolve().parents[2] / "eval_determinism.json"


def _engine_urgency(answers, section, species, gender):
    u = te.compute_urgency(answers, species, section, gender)
    return u["urgency"], u["urgency_level_num"]


def _eval_all() -> dict:
    cases = enumerate_paths(max_per_section=4)
    rows = []
    match = 0
    for c in cases:
        answers, section = walk(c["path"])  # species/gender 기본(dog/None)
        eng_u, eng_n = _engine_urgency(answers, section, "dog", None)
        r = ref.score(answers, "dog", section, None)
        ok = (eng_u == r["urgency"])
        match += int(ok)
        rows.append({
            "section": c["section"], "path": c["path"],
            "engine": eng_u, "reference": r["urgency"], "score": r["total_score"],
            "match": ok,
        })
    accuracy = round(match / len(rows), 4) if rows else 0.0
    return {"n_cases": len(rows), "spec_match_accuracy": accuracy, "rows": rows}


def _measure_determinism(cases) -> dict:
    """각 경로를 _REPEAT회 실행해 출력이 모두 동일한지 측정 → 불일치 건수 집계."""
    unstable = 0
    for c in cases:
        answers, section = walk(c["path"])
        outs = {
            _engine_urgency(answers, section, "dog", None)
            for _ in range(_REPEAT)
        }
        if len(outs) != 1:
            unstable += 1
    return {
        "runs_per_case": _REPEAT,
        "n_cases": len(cases),
        "unstable_cases": unstable,
        "variance_rate": round(unstable / len(cases), 4) if cases else 0.0,
    }


def run_and_dump() -> dict:
    spec = _eval_all()
    cases = enumerate_paths(max_per_section=4)
    det = _measure_determinism(cases)
    report = {"spec_consistency": spec, "determinism": det}
    _OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


# ── pytest 진입점 ────────────────────────────────────────────────
def test_engine_matches_spec_reference():
    """엔진 결과가 독립 레퍼런스 채점기와 100% 일치해야 한다(명세 정확도)."""
    spec = _eval_all()
    mism = [r for r in spec["rows"] if not r["match"]]
    assert not mism, f"명세 불일치 {len(mism)}건: {mism[:3]}"
    assert spec["spec_match_accuracy"] == 1.0


def test_engine_is_deterministic():
    """동일 입력 {_REPEAT}회 반복 시 출력이 100% 동일해야 한다(variance=0)."""
    cases = enumerate_paths(max_per_section=4)
    det = _measure_determinism(cases)
    assert det["unstable_cases"] == 0, det
    assert det["variance_rate"] == 0.0


if __name__ == "__main__":
    rep = run_and_dump()
    s, d = rep["spec_consistency"], rep["determinism"]
    print(f"[명세 일치도] {s['n_cases']}경로 중 정확도 {s['spec_match_accuracy']*100:.1f}%")
    print(f"[결정론] {d['n_cases']}경로 × {d['runs_per_case']}회 → 불안정 {d['unstable_cases']}건 "
          f"(variance {d['variance_rate']*100:.1f}%)")
    print(f"→ {_OUT}")
