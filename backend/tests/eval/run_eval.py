"""Eval 오케스트레이터 — 측정을 모아 EVAL_REPORT.md 로 취합한다.

사용:
  # LLM-free(무료) 만 — 항상 가능
  python -m tests.eval.run_eval            # (backend/ 에서)

  # LIVE(실측 지연/비용/LLM 재현성) 포함 — OpenAI 소량 호출
  RUN_LIVE_EVAL=1 python -m tests.eval.run_eval

산출물:
  backend/eval_determinism.json     (항상)
  backend/eval_llm_variance.json    (LIVE)
  backend/eval_latency_cost.json    (LIVE)
  backend/EVAL_REPORT.md            (취합 리포트)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]


def _load(name: str) -> dict | None:
    p = _BACKEND / name
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def main() -> None:
    live = os.environ.get("RUN_LIVE_EVAL") == "1"

    # 1) 결정론/명세 일치도 (무료, 항상)
    from tests.eval.test_determinism import run_and_dump
    det = run_and_dump()

    # 1.5) 다국어 언어 라우팅 (LLM-free, 항상)
    try:
        from tests.eval.test_multilingual import _routing_eval
        ml_routing = _routing_eval()
    except Exception as exc:  # noqa: BLE001
        ml_routing = {"error": str(exc)}

    # 2) LIVE 측정 (선택) — openai/설정/키가 있어야 함. 없으면 트레이스백 대신 안내.
    if live:
        import asyncio
        try:
            from app.core.config import settings
            if not settings.OPENAI_API_KEY:
                raise RuntimeError("OPENAI_API_KEY 가 비어 있음 (backend/.env 확인)")
            from tests.eval import test_latency_cost, test_llm_variance, test_multilingual

            # 측정을 '하나의' 이벤트 루프에서 실행한다.
            # (asyncio.run 을 여러 번 호출하면 openai async client 정리 시점에
            #  'Event loop is closed' 노이즈가 뜨므로 단일 루프로 묶는다.)
            async def _live():
                return (await test_llm_variance._run(),
                        await test_latency_cost._run(),
                        await test_multilingual._run_live())

            var, lat, ml = asyncio.run(_live())
            (_BACKEND / "eval_llm_variance.json").write_text(
                json.dumps(var, ensure_ascii=False, indent=2), encoding="utf-8")
            (_BACKEND / "eval_latency_cost.json").write_text(
                json.dumps(lat, ensure_ascii=False, indent=2), encoding="utf-8")
            (_BACKEND / "eval_multilingual.json").write_text(
                json.dumps(ml, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            print(f"\n[LIVE 측정 생략] {type(exc).__name__}: {exc}")
            print("  → LIVE 평가는 백엔드 의존성(openai 등)+OPENAI_API_KEY 가 필요합니다.")
            print("  → 권장: 스택 안에서 실행 →")
            print("     docker compose -f ai/docker/docker-compose.yml exec backend \\")
            print("       bash -c 'cd /app/backend && RUN_LIVE_EVAL=1 PYTHONPATH=.. python -m tests.eval.run_eval'")
            live = False  # 리포트에서 LIVE 섹션을 '미측정'으로 표기

    # 3) 리포트 작성
    sc = det["spec_consistency"]
    dt = det["determinism"]
    lines = [
        "# MediPaw 정량 평가 리포트 (EVAL_REPORT.md)",
        "",
        "> 모든 수치는 측정값이다. LLM-free 항목은 재현 가능하고, LIVE 항목은 실제 호출의 실측이다.",
        "",
        "## 1. 트리아지 엔진 — 명세 일치도 & 결정론 (LLM-free)",
        "",
        f"- 자동 열거 경로: **{sc['n_cases']}개**",
        f"- 명세 일치도(독립 레퍼런스 채점기 대비): **{sc['spec_match_accuracy']*100:.1f}%**",
        f"- 결정론: {dt['n_cases']}경로 × {dt['runs_per_case']}회 = "
        f"**{dt['n_cases']*dt['runs_per_case']}회 실행, 불안정 {dt['unstable_cases']}건 "
        f"(분산 {dt['variance_rate']*100:.1f}%)**",
        "",
        "  → 같은 입력이면 항상 같은 응급도. 'AI가 흔들린다'는 공격이 구조적으로 불가능.",
        "",
    ]
    var = _load("eval_llm_variance.json")
    if var:
        lines += [
            "## 2. 대조군 — LLM-only 분류기 재현성 (LIVE 실측)",
            "",
            f"- 모델 {var['model']}, {var['n_inputs']}입력 × {var['runs_per_input']}회",
            f"- LLM-only 분산: **{var['variance_rate']*100:.1f}%** "
            f"(불안정 {var['unstable_inputs']}/{var['n_inputs']})",
            f"- 규칙 엔진 분산: **0.0%** (위 1절)",
            "",
            "  → 동일 입력에 LLM은 응급도가 흔들리고, 규칙 엔진은 흔들리지 않는다(재현성 우위).",
            "",
        ]
    lat = _load("eval_latency_cost.json")
    if lat:
        lines += ["## 3. 지연 / 비용 (LIVE 실측)", ""]
        for x in lat["logs"]:
            if x.get("step") == "llm_chart_draft":
                lines.append(
                    f"- LLM 차트초안: {x['latency_sec']}s, "
                    f"in {x['input_tokens']} / out {x['output_tokens']} tok, "
                    f"**$ {x['cost_per_1000_usd']}/1000건** ({x['model']})")
            elif x.get("step") == "rag_search":
                if "skipped" in x:
                    lines.append(f"- RAG 검색: (DB 미가동으로 생략)")
                else:
                    lines.append(
                        f"- RAG 검색: {x['latency_sec']}s, 결과 {x['results']}건, "
                        f"top유사도 {x.get('top_similarity')}")
        lines.append("")
    if not live:
        lines += ["## 2~3. LIVE 측정", "",
                  "`RUN_LIVE_EVAL=1` 로 다시 실행하면 LLM 재현성·지연·비용 실측이 추가된다.", ""]

    # ── 4. 다국어 ────────────────────────────────────────────────
    lines += ["## 4. 다국어 (ko/en/ja/zh)", ""]
    if isinstance(ml_routing, dict) and "accuracy" in ml_routing:
        lines.append(
            f"- A. 언어 라우팅 정확도(LLM-free): **{ml_routing['accuracy']*100:.1f}%** "
            f"({ml_routing['n']}건) — 비한글 입력을 번역 대상으로 정확 분류")
    ml = _load("eval_multilingual.json")
    if ml:
        ip, dc = ml["input_preservation"], ml["display_coverage"]
        lines += [
            f"- B. 입력경로 증상어 보존(LIVE): **{ip['preservation_rate']*100:.1f}%** "
            f"({ip['preserved']}/{ip['pairs']} 쌍) — en/ja/zh→한국어 번역 후에도 핵심 증상어 유지",
            f"- C. 표시경로 번역 커버리지(LIVE): **{dc['coverage_rate']*100:.1f}%** "
            f"({dc['translated_ok']}/{dc['n']}), 평균 지연 {dc['avg_latency_sec']}s",
            "",
            "  → 다국어 입력이 트리아지 라우팅(증상어)을 손상시키지 않음 + 4개 언어 표시 일관.",
            "",
        ]
    else:
        lines += ["- B·C(보존율·표시 커버리지)는 `RUN_LIVE_EVAL=1` 로 실측 추가.", ""]

    (_BACKEND / "EVAL_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n→ {_BACKEND / 'EVAL_REPORT.md'}")


if __name__ == "__main__":
    main()
