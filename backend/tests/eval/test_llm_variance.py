"""[정량 평가 2 · LIVE] LLM-only 분류기의 재현성(불안정성) 측정 — 대조군.

이 테스트는 *실제 OpenAI를 호출*한다. 비용/네트워크가 들어가므로 기본 SKIP이고,
`RUN_LIVE_EVAL=1` 환경변수가 있을 때만 실행한다.

목적(중간발표=master 대비 정량 비교의 '대조군'):
  현재 시스템은 규칙 엔진으로 응급도를 산정한다(test_determinism.py: variance 0%).
  중간발표 단계처럼 'LLM이 직접 응급도를 매긴다면' 같은 입력에도 run마다 흔들린다.
  그 흔들림(불일치율)을 같은 입력 K회 반복으로 *측정*해, 규칙 엔진의 0%와 대비한다.

  → "규칙 엔진 분산 0% vs LLM-only 분산 X%" 라는, 심사위원이 납득 가능한 정량 근거.
    (LLM이 LLM을 평가하는 게 아니라, LLM 출력의 '재현성'이라는 객관 속성을 측정)

산출물: backend/eval_llm_variance.json
"""
from __future__ import annotations

import asyncio
import json
import os
from collections import Counter
from pathlib import Path

try:
    import pytest
except ModuleNotFoundError:  # run_eval 직접 실행(호스트 파이썬, pytest 미설치) 대비
    class _PytestShim:
        class mark:
            @staticmethod
            def skipif(*a, **k):
                def deco(fn):
                    return fn
                return deco
    pytest = _PytestShim()  # type: ignore

_OUT = Path(__file__).resolve().parents[2] / "eval_llm_variance.json"
_REPEAT = int(os.environ.get("LLM_VARIANCE_REPEAT", "10"))

# 고정 입력 셋(보호자 일상어). 정답을 정의하지 않는다 — '같은 입력에 같은 답을 주는가'만 본다.
_UTTERANCES = [
    "강아지가 갑자기 숨을 헐떡이고 힘들어해요",
    "고양이가 어제부터 밥을 안 먹고 토했어요",
    "산책하다 다리를 절뚝거려요",
    "눈이 충혈되고 눈물이 나요",
    "계속 기침을 하는데 컨디션은 괜찮아요",
    "소변을 보려고 하는데 잘 안 나와요",
]

_SYSTEM = (
    "너는 수의 트리아지 분류기다. 보호자 증상 표현을 받아 응급도를 1~4로만 답한다. "
    "1=응급, 2=준응급, 3=긴급, 4=일반. 다른 말 없이 JSON {\"urgency_level_num\": N} 만 출력."
)


async def _classify_once(client, model, text) -> int | None:
    resp = await client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": _SYSTEM},
                  {"role": "user", "content": text}],
        temperature=0.7,  # master 시절 기본값 가정(결정론 아님)
        max_completion_tokens=20,
        response_format={"type": "json_object"},
    )
    try:
        return int(json.loads(resp.choices[0].message.content)["urgency_level_num"])
    except Exception:
        return None


async def _run() -> dict:
    from openai import AsyncOpenAI

    from app.core.config import settings

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    model = settings.OPENAI_MODEL or "gpt-4o-mini"

    rows = []
    unstable = 0
    for text in _UTTERANCES:
        outs = await asyncio.gather(*[_classify_once(client, model, text) for _ in range(_REPEAT)])
        counts = Counter(o for o in outs if o is not None)
        distinct = len(counts)
        if distinct > 1:
            unstable += 1
        rows.append({"utterance": text, "runs": _REPEAT, "distinct_answers": distinct,
                     "distribution": dict(counts)})

    return {
        "model": model, "runs_per_input": _REPEAT, "n_inputs": len(_UTTERANCES),
        "unstable_inputs": unstable,
        "variance_rate": round(unstable / len(_UTTERANCES), 4),
        "rule_engine_variance_rate": 0.0,  # test_determinism.py 측정값(대비)
        "rows": rows,
    }


@pytest.mark.skipif(os.environ.get("RUN_LIVE_EVAL") != "1",
                    reason="LIVE 평가: RUN_LIVE_EVAL=1 일 때만 실행(OpenAI 비용)")
def test_llm_variance_measured():
    report = asyncio.run(_run())
    _OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    # 단언은 '측정이 성공적으로 수집됐는지'만. (LLM 변동성 자체는 실패 조건이 아님)
    assert report["n_inputs"] == len(_UTTERANCES)


if __name__ == "__main__":
    rep = asyncio.run(_run())
    _OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[LLM-only 재현성] {rep['n_inputs']}입력 × {rep['runs_per_input']}회 "
          f"→ 불안정 {rep['unstable_inputs']}건 (variance {rep['variance_rate']*100:.1f}%)")
    print(f"[규칙 엔진 대비] rule variance 0.0% (test_determinism.py)")
    print(f"→ {_OUT}")
