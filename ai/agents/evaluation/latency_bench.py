"""
Latency & Token Usage Benchmark
================================
모든 에이전트의 LLM 호출 latency와 token 사용량을 측정한다.
DB/세션 없이 프롬프트 레벨에서 직접 측정 (독립 실행 가능).

실행:
    cd SKN25-FINAL-1Team
    python -m ai.agents.evaluation.latency_bench

결과:
    - 터미널에 에이전트별 요약 출력
    - latency_results.csv 저장 (ai/agents/evaluation/ 폴더)
"""
from __future__ import annotations

import asyncio
import csv
import json
import os
import time
from pathlib import Path

# 환경 변수 로드 
from dotenv import load_dotenv
load_dotenv()

# LLM 클라이언트 
from ai.llm import get_llm

# 에이전트별 프롬프트 빌더
from ai.agents.triage.prompts import build_extraction_prompt
from ai.agents.followup_filter.prompts import build_classification_prompt
from ai.agents.chart.prompts import CHART_PROMPT
from ai.agents.schedule.prompts import DURATION_PROMPT
from ai.agents.reception.prompts import build_reception_prompt
from ai.agents.prescription.prompts import GENERATE_PROMPT

# 테스트 케이스 로드
_CASES_PATH = Path(__file__).parent.parent / "eval_cases" / "latency_test_cases.json"
_OUTPUT_CSV = Path(__file__).parent / "latency_results.csv"

# GPT-5.4 mini 기준 가격 (2026-06)
_PRICE_INPUT_PER_1K = 0.00075   # $0.75 / 1M input tokens
_PRICE_OUTPUT_PER_1K = 0.0045   # $4.50 / 1M output tokens


def _load_cases() -> dict:
    with open(_CASES_PATH, encoding="utf-8") as f:
        return json.load(f)


def _fmt_history(history: list[dict]) -> str:
    if not history:
        return ""
    lines = ["\n[최근 대화]"]
    for m in history:
        role = "보호자" if m.get("role") == "user" else "챗봇"
        lines.append(f"{role}: {m.get('content', '')}")
    return "\n".join(lines)


# 프롬프트 빌더 (테스트케이스 → 프롬프트 문자열) 

def _build_router_prompt(case: dict) -> str:
    from ai.orchestrator.router import _AGENT_DESC
    phase = case.get("phase", "PRE_BOOKING")
    candidates = ["reception", "followup_filter"] if phase == "BOOKED" else ["reception", "triage", "redirect"]
    desc = "\n".join(f"- {n}: {_AGENT_DESC[n]}" for n in candidates if n in _AGENT_DESC)
    recent = "\n".join(
        f"{m.get('role')}: {m.get('content')}" for m in (case.get("history") or [])[-5:]
    )
    phase_hint = (
        "지금은 '예약 후'야. 아이 상태 관련 대화는 followup_filter. 병원 정보만 reception."
        if phase == "BOOKED"
        else "지금은 '예약 전'이야. 증상 문진은 triage, 병원 정보는 reception."
    )
    return (
        f"동물병원 챗봇의 라우터야. 아래 보호자 발화를 '누가' 처리해야 할지 후보 중 하나의 이름만 골라.\n"
        f"{phase_hint}\n\n[후보 에이전트]\n{desc}\n\n"
        f"[최근 대화]\n{recent}\n[이번 발화] {case['user_message']}\n\n"
        '{"agent": "후보 이름 중 하나"}'
    )


def _build_triage_prompt(case: dict) -> str:
    history = case.get("history") or []
    return build_extraction_prompt(
        history=history,
        user_message=case["user_message"],
        section_id=case.get("prev_section"),
        collected=case.get("extracted") or {},
        vision_note="",
    )


def _build_followup_prompt(case: dict) -> str:
    return build_classification_prompt(
        pet_info=case.get("pet_info"),
        followup_summary=case.get("followup_summary", ""),
        history=case.get("history") or [],
        user_message=case["user_message"],
        attachment_count=0,
        vision_findings="",
        vision_relevant=None,
        last_reply_kind=None,
        asked_fields=[],
        prev_question="",
        last_media_summary="",
    )


def _build_chart_prompt(case: dict) -> str:
    pet = case["pet"]
    triage = case["triage"]
    chat_history = case.get("chat_history") or []
    rag_context = case.get("rag_context") or []

    pet_info = (
        f"이름: {pet.get('name')} / 품종: {pet.get('breed', '알 수 없음')} / "
        f"나이: {pet.get('age', '?')}세 / 성별: {pet.get('gender', '미상')} / "
        f"체중: {pet.get('weight', '?')}kg"
    )
    triage_section = "\n".join([
        f"응급도: {triage.get('urgency_level')} (VTL Level {triage.get('urgency_level_num')})",
        f"주요증상: {', '.join(triage.get('symptom_keywords') or [])}",
        f"증상시작: {triage.get('symptom_onset', '')}",
        f"의심질환: {', '.join(triage.get('suspected_diseases') or [])}",
        f"Red Flags: {', '.join(triage.get('red_flags') or []) or '없음'}",
        f"문진요약: {triage.get('symptom_summary', '')}",
    ])
    cnn_section = "없음"
    lines = ["[챗봇 전체 문진 대화]"]
    for idx, m in enumerate(chat_history[-14:], 1):
        role = "보호자" if m.get("role") == "user" else "챗봇"
        lines.append(f"{idx}. {role}: {m.get('content', '')[:500]}")
    chat_section = "\n".join(lines)
    rag_section = "[유사 상담사례 참고] 없음" if not rag_context else "[유사 상담사례 참고]"
    history_section = "[과거 진료 기록 없음 - 초진으로 간주]"

    return CHART_PROMPT.format(
        pet_info=pet_info,
        triage_section=triage_section,
        cnn_section=cnn_section,
        chat_section=chat_section,
        history_section=history_section,
        rag_section=rag_section,
    )


def _build_schedule_prompt(case: dict) -> str:
    import json as _json
    pet = case["pet"]
    triage = case["triage"]
    is_initial = bool(triage.get("is_initial_visit", True))
    triage_view = {
        "urgency": triage.get("urgency"),
        "score": triage.get("score"),
        "chief_complaints": triage.get("chief_complaints"),
        "suspected_conditions": triage.get("suspected_conditions"),
        "summary": triage.get("triage_summary"),
    }
    return DURATION_PROMPT.format(
        pet=_json.dumps(pet, ensure_ascii=False),
        triage=_json.dumps(triage_view, ensure_ascii=False),
        visit_type="초진" if is_initial else "재진",
    )


def _build_reception_prompt(case: dict) -> str:
    history_block = _fmt_history(case.get("history") or [])
    return build_reception_prompt(
        facts=case.get("hospital_facts", "병원명: 테스트 동물병원"),
        pet_name=case.get("pet_name", "아이"),
        history_block=history_block,
        streak_hint="",
        user_message=case["question"],
    )


def _build_prescription_prompt(case: dict) -> str:
    import json as _json
    pet = case["pet"]
    drug_candidates = case.get("drug_candidates") or []
    drug_list = "\n".join(
        f"- {d.get('name')}: {d.get('form')} / {d.get('indication')}" for d in drug_candidates
    )
    return GENERATE_PROMPT.format(
        doctor_notes=case.get("doctor_notes", "없음"),
        pet_info=(
            f"이름: {pet.get('name')}, 종: {pet.get('species')}, 품종: {pet.get('breed')}, "
            f"나이: {pet.get('age')}세, 체중: {pet.get('weight')}kg, 성별: {pet.get('gender')}"
        ),
        symptoms=", ".join(case.get("symptoms") or []),
        suspected=", ".join(case.get("suspected") or []),
        drug_list=drug_list,
    )


# 에이전트 → 프롬프트 빌더 매핑 
_BUILDERS = {
    "router":       _build_router_prompt,
    "triage":       _build_triage_prompt,
    "followup":     _build_followup_prompt,
    "chart":        _build_chart_prompt,
    "schedule":     _build_schedule_prompt,
    "reception":    _build_reception_prompt,
    "prescription": _build_prescription_prompt,
}


# 단일 LLM 호출 측정
async def _measure_one(agent: str, case: dict) -> dict:
    builder = _BUILDERS.get(agent) # 프롬프트 생성
    if not builder:
        return {"agent": agent, "case_id": case.get("id"), "error": "no builder"}
    try:
        prompt = builder(case) # llm 호출
    except Exception as e:
        return {"agent": agent, "case_id": case.get("id"), "error": f"prompt build failed: {e}"}

    llm = get_llm(temperature=0)
    try:
        t0 = time.perf_counter()
        response = await llm.ainvoke(prompt)
        latency_ms = (time.perf_counter() - t0) * 1000

        usage = getattr(response, "usage_metadata", None) or {}
        input_tokens  = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        total_tokens  = usage.get("total_tokens", input_tokens + output_tokens)

        cost_usd = (input_tokens / 1000 * _PRICE_INPUT_PER_1K
                    + output_tokens / 1000 * _PRICE_OUTPUT_PER_1K)

        return {
            "agent":         agent,
            "case_id":       case.get("id", "?"),
            "latency_ms":    round(latency_ms, 1),
            "input_tokens":  input_tokens,
            "output_tokens": output_tokens,
            "total_tokens":  total_tokens,
            "cost_usd":      round(cost_usd, 6),
            "error":         None,
        }
    except Exception as e:
        return {"agent": agent, "case_id": case.get("id"), "error": str(e)}


# 에이전트 전체 실행 
async def run_agent(agent: str, cases: list[dict]) -> list[dict]:
    print(f"\n[{agent.upper()}] {len(cases)}개 케이스 측정 중...")
    results = []
    for i, case in enumerate(cases, 1):
        r = await _measure_one(agent, case)
        if r.get("error"):
            print(f"  [{i}/{len(cases)}] {case.get('id')} ❌ {r['error']}")
        else:
            print(f"  [{i}/{len(cases)}] {case.get('id')} — {r['latency_ms']:.0f}ms "
                  f"| in:{r['input_tokens']} out:{r['output_tokens']} "
                  f"| ${r['cost_usd']:.5f}")
        results.append(r)
        await asyncio.sleep(0.3)   # rate limit 방지
    return results


# 요약 출력 
def _print_summary(all_results: list[dict]) -> None:
    from collections import defaultdict
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in all_results:
        if not r.get("error"):
            groups[r["agent"]].append(r)

    print("\n" + "=" * 65)
    print(f"{'Agent':<18} {'Cases':>5} {'Avg(ms)':>8} {'In tok':>8} {'Out tok':>8} {'$/건':>10}")
    print("-" * 65)

    total_cases = 0
    total_cost  = 0.0
    total_lat   = 0.0
    total_in    = 0
    total_out   = 0

    for agent, rows in groups.items():
        n = len(rows)
        avg_lat = sum(r["latency_ms"]   for r in rows) / n
        avg_in  = sum(r["input_tokens"] for r in rows) / n
        avg_out = sum(r["output_tokens"] for r in rows) / n
        avg_cost = sum(r["cost_usd"]    for r in rows) / n
        print(f"{agent:<18} {n:>5} {avg_lat:>8.0f} {avg_in:>8.0f} {avg_out:>8.0f} ${avg_cost:>9.5f}")
        total_cases += n
        total_cost  += sum(r["cost_usd"] for r in rows)
        total_lat   += sum(r["latency_ms"] for r in rows)
        total_in    += sum(r["input_tokens"] for r in rows)
        total_out   += sum(r["output_tokens"] for r in rows)

    print("-" * 65)
    if total_cases:
        print(f"{'전체 평균':<18} {total_cases:>5} {total_lat/total_cases:>8.0f} "
              f"{total_in/total_cases:>8.0f} {total_out/total_cases:>8.0f} "
              f"${total_cost/total_cases:>9.5f}")
    print("=" * 65)
    print(f"\n총 케이스: {total_cases}건 | 총 비용: ${total_cost:.4f}")
    # 참고: 실제 진료 케이스는 여러 에이전트를 거치므로 합산 필요
    agent_order = ["router", "triage", "chart", "schedule", "followup", "reception"]
    per_visit = sum(
        sum(r["cost_usd"] for r in groups.get(a, [])) / max(len(groups.get(a, ["_"])), 1)
        for a in agent_order if a in groups
    )
    print(f"예상 1회 진료 흐름 비용: ${per_visit:.5f} (router→triage→chart→schedule 합산)")


# CSV 저장 
def _save_csv(all_results: list[dict]) -> None:
    fields = ["agent", "case_id", "latency_ms", "input_tokens", "output_tokens", "total_tokens", "cost_usd", "error"]
    with open(_OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_results)
    print(f"\nCSV 저장: {_OUTPUT_CSV}")


# 메인 
async def main(agents: list[str] | None = None) -> None:
    cases_data = _load_cases()
    target_agents = agents or list(_BUILDERS.keys())

    all_results: list[dict] = []
    for agent in target_agents:
        cases = cases_data.get(agent, [])
        if not cases:
            print(f"[{agent}] 케이스 없음, 스킵")
            continue
        results = await run_agent(agent, cases)
        all_results.extend(results)

    _print_summary(all_results)
    _save_csv(all_results)


if __name__ == "__main__":
    import sys
    target = sys.argv[1:] if len(sys.argv) > 1 else None
    asyncio.run(main(agents=target))
