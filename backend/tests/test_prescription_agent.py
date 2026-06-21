"""처방 초안 에이전트(generate) 단위 테스트 (LLM 스텁).

검증: ① medication 출력 계약(drug_name/form/dosage/frequency/duration_days)
② duration 정수화 ③ 이름 없는 항목 제거 ④ 후보 없으면 LLM 미호출
⑤ LLM 실패 시 빈 리스트(엔드포인트가 빈 처방으로 처리).
"""
import asyncio

import ai.agents.prescription.agent as agent_mod
from ai.agents.prescription import PrescriptionAgent

_CANDS = [
    {"name": "아목시클라정", "ingredient_kr": "아목시실린", "ingredient_en": "amoxicillin"},
    {"name": "메로페넴주", "ingredient_kr": "메로페넴", "ingredient_en": "meropenem"},
]


def _run(coro):
    return asyncio.run(coro)


def _stub(payload):
    async def fake(prompt, schema, temperature=0):
        return payload
    return fake


def test_output_contract(monkeypatch):
    monkeypatch.setattr(agent_mod, "call_llm_structured", _stub({
        "medications": [
            {"name": "아목시클라정", "form": "PO(경구)", "dosage": "10mg/kg",
             "frequency": "BID(하루 2회)", "duration": 7},
        ],
    }))
    out = _run(PrescriptionAgent().generate(
        pet={"species": "강아지", "weight_kg": 5, "age": 3},
        drug_candidates=_CANDS, symptoms=["구토"], suspected_diseases=["위염"],
        doctor_notes="탈수 동반"))
    assert len(out) == 1
    rec = out[0]
    assert set(rec.keys()) == {"drug_name", "form", "dosage", "frequency", "duration_days"}
    assert rec["drug_name"] == "아목시클라정"
    assert rec["duration_days"] == 7 and isinstance(rec["duration_days"], int)


def test_duration_coerced_to_int(monkeypatch):
    # 스키마가 정수를 강제하지만, 혹시 문자열/None이 와도 0 이상 정수로.
    monkeypatch.setattr(agent_mod, "call_llm_structured", _stub({
        "medications": [{"name": "메로페넴주", "form": "IV(정맥)", "dosage": "1ml",
                         "frequency": "SID(하루 1회)", "duration": None}],
    }))
    out = _run(PrescriptionAgent().generate(pet={}, drug_candidates=_CANDS))
    assert out[0]["duration_days"] == 0


def test_drops_nameless_items(monkeypatch):
    monkeypatch.setattr(agent_mod, "call_llm_structured", _stub({
        "medications": [
            {"name": "  ", "form": "PO", "dosage": "1정", "frequency": "SID", "duration": 3},
            {"name": "아목시클라정", "form": "PO", "dosage": "1정", "frequency": "SID", "duration": 3},
        ],
    }))
    out = _run(PrescriptionAgent().generate(pet={}, drug_candidates=_CANDS))
    assert [r["drug_name"] for r in out] == ["아목시클라정"]


def test_empty_candidates_short_circuits(monkeypatch):
    called = {"n": 0}
    async def fake(prompt, schema, temperature=0):
        called["n"] += 1
        return {"medications": []}
    monkeypatch.setattr(agent_mod, "call_llm_structured", fake)
    out = _run(PrescriptionAgent().generate(pet={}, drug_candidates=[]))
    assert out == [] and called["n"] == 0


def test_llm_failure_returns_empty(monkeypatch):
    async def boom(prompt, schema, temperature=0):
        raise RuntimeError("LLM down")
    monkeypatch.setattr(agent_mod, "call_llm_structured", boom)
    out = _run(PrescriptionAgent().generate(pet={}, drug_candidates=_CANDS))
    assert out == []
