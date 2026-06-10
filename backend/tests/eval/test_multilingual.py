"""[정량 평가 5] 다국어 — 언어 라우팅 + 번역 증상어 보존 + 표시 커버리지.

MediPaw 보호자 챗봇은 ko/en/ja/zh 를 지원한다(chat.py):
  · 입력경로: 비한글 입력 → 한국어로 번역 → 결정론 트리아지 엔진이 처리.
  · 표시경로: 한국어 답변/pill → 사용자 UI 언어로 번역해 스트리밍.

신뢰 설계(‘AI가 AI를 평가’ 회피):
  A. 언어 라우팅은 `_has_hangul`(정규식) — **LLM-free·결정론**.
  B. 입력경로 평가는 '번역(실제)' 후 **핵심 증상 키워드가 보존됐는지**를
     결정론 문자열 매칭으로 본다. 번역 품질을 LLM이 채점하지 않는다. 측정 대상은
     "번역이 트리아지 라우팅에 필요한 증상어를 잃지 않는가"라는 객관적 보존율이다.
  C. 표시경로는 '번역이 일어났고(원문과 다름) 비지 않는가'의 커버리지 + 실측 지연.

A는 항상 실행(무료). B/C 는 RUN_LIVE_EVAL=1 일 때만(OpenAI 호출).
산출물: backend/eval_multilingual.json
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

try:
    import pytest
except ModuleNotFoundError:
    class _PytestShim:
        class mark:
            @staticmethod
            def skipif(*a, **k):
                def deco(fn):
                    return fn
                return deco
    pytest = _PytestShim()  # type: ignore

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root

_OUT = Path(__file__).resolve().parents[2] / "eval_multilingual.json"

# 같은 증상을 4개 언어로. keyword_any = 한국어 번역에 반드시 남아야 할 증상어(동의어 허용).
_SCENARIOS = [
    {"keyword_any": ["구토", "토하", "토해", "토"], "ko": "강아지가 계속 토해요",
     "en": "My dog keeps vomiting", "ja": "犬が吐き続けています", "zh": "我的狗一直呕吐"},
    {"keyword_any": ["설사"], "ko": "설사를 해요",
     "en": "He has diarrhea", "ja": "下痢をしています", "zh": "它拉肚子"},
    {"keyword_any": ["기침"], "ko": "기침을 계속 해요",
     "en": "My cat keeps coughing", "ja": "猫が咳をし続けています", "zh": "我的猫一直咳嗽"},
    {"keyword_any": ["숨", "호흡", "헐떡"], "ko": "숨을 헐떡이고 힘들어해요",
     "en": "He is panting and struggling to breathe", "ja": "呼吸が苦しそうです", "zh": "它呼吸困难"},
    {"keyword_any": ["피", "출혈"], "ko": "상처에서 피가 나요",
     "en": "There is bleeding from the wound", "ja": "傷口から出血しています", "zh": "伤口在出血"},
    {"keyword_any": ["다리", "절뚝", "절"], "ko": "다리를 절뚝거려요",
     "en": "limping on one leg", "ja": "足を引きずっています", "zh": "一条腿瘸了"},
]

_NON_KO = ("en", "ja", "zh")


# ── A. 언어 라우팅 (LLM-free) ───────────────────────────────────────
def _routing_eval() -> dict:
    from app.api.chat import _has_hangul

    # (input, should_be_translated) — 한글이면 번역 불필요(False), 그 외면 번역 대상(True).
    cases = []
    for s in _SCENARIOS:
        cases.append((s["ko"], False))
        for lang in _NON_KO:
            cases.append((s[lang], True))
    cases += [("12345 !!!", True), ("강아지 3살", False)]  # 경계 케이스

    correct = 0
    rows = []
    for text, expect_translate in cases:
        # _has_hangul True → 번역 불필요. expect_translate True → 한글 없어야 함.
        routed_translate = not _has_hangul(text)
        ok = routed_translate == expect_translate
        correct += int(ok)
        rows.append({"text": text, "expect_translate": expect_translate,
                     "routed_translate": routed_translate, "ok": ok})
    return {"n": len(cases), "accuracy": round(correct / len(cases), 4), "rows": rows}


# ── B. 입력경로 — 번역 후 증상어 보존 (LIVE) ─────────────────────────
async def _input_preservation() -> dict:
    from app.api.chat import _translate_batch

    total = 0
    kept = 0
    rows = []
    for s in _SCENARIOS:
        for lang in _NON_KO:
            translated = (await _translate_batch([s[lang]], "ko"))[0]
            hit = any(k in translated for k in s["keyword_any"])
            total += 1
            kept += int(hit)
            rows.append({"lang": lang, "src": s[lang], "ko": translated,
                         "expected_any": s["keyword_any"], "preserved": hit})
    return {"pairs": total, "preserved": kept,
            "preservation_rate": round(kept / total, 4) if total else 0.0, "rows": rows}


# ── C. 표시경로 — 번역 커버리지 + 지연 (LIVE) ────────────────────────
async def _display_coverage() -> dict:
    from app.api.chat import _translate_batch

    rows = []
    ok = 0
    total = 0
    latencies = []
    for s in _SCENARIOS:
        for lang in _NON_KO:
            start = time.perf_counter()
            out = (await _translate_batch([s["ko"]], lang))[0]
            latencies.append(time.perf_counter() - start)
            changed = bool(out and out.strip() and out.strip() != s["ko"])
            total += 1
            ok += int(changed)
            rows.append({"lang": lang, "ko": s["ko"], "translated": out, "changed": changed})
    avg_lat = round(sum(latencies) / len(latencies), 4) if latencies else None
    return {"n": total, "translated_ok": ok,
            "coverage_rate": round(ok / total, 4) if total else 0.0,
            "avg_latency_sec": avg_lat, "rows": rows}


async def _run_live() -> dict:
    routing = _routing_eval()
    preservation = await _input_preservation()
    display = await _display_coverage()
    return {"language_routing": routing, "input_preservation": preservation,
            "display_coverage": display}


# ── pytest 진입점 ───────────────────────────────────────────────────
def test_language_routing_deterministic():
    """비한글 입력 → 번역 대상으로 정확히 분류돼야 한다(LLM-free)."""
    r = _routing_eval()
    assert r["accuracy"] == 1.0, [x for x in r["rows"] if not x["ok"]]


@pytest.mark.skipif(os.environ.get("RUN_LIVE_EVAL") != "1",
                    reason="LIVE 평가: RUN_LIVE_EVAL=1 일 때만 실행(OpenAI 비용)")
def test_multilingual_live_measured():
    report = asyncio.run(_run_live())
    _OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    # 증상어 보존율은 핵심 안전 지표 — 너무 낮으면(번역이 증상을 잃음) 실패로 간주.
    assert report["input_preservation"]["preservation_rate"] >= 0.8, report["input_preservation"]


if __name__ == "__main__":
    rep = asyncio.run(_run_live())
    _OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    rt, ip, dc = rep["language_routing"], rep["input_preservation"], rep["display_coverage"]
    print(f"[A 언어 라우팅] 정확도 {rt['accuracy']*100:.1f}% (LLM-free)")
    print(f"[B 증상어 보존] {ip['preserved']}/{ip['pairs']} = {ip['preservation_rate']*100:.1f}%")
    print(f"[C 표시 커버리지] {dc['translated_ok']}/{dc['n']} = {dc['coverage_rate']*100:.1f}%, "
          f"평균 {dc['avg_latency_sec']}s")
    print(f"→ {_OUT}")
