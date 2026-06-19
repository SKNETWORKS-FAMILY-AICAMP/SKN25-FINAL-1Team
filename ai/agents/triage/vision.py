"""문진용 이미지 분석 보조 — CNN(피부/안구) + VLM(소견 묘사).

원칙:
 - CNN = 구조화 후보(병명+신뢰도). 피부/안구 키워드가 있으면 해당 CNN을 켠다(둘 다면 둘 다).
 - VLM = 부위 라우팅 보조 + 보이는 소견 자연어 묘사(병명 단정 X).
 - 결과는 '추출 콜에 줄 note' + '저장용 evidence' + 'suspected(후보병명)'로 돌려준다.
 - 전부 fail-open: 실패해도 None/부분값만 반환하고 문진을 막지 않는다.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

_SKIN_KW = ("피부", "긁", "발진", "두드러기", "진드기", "벼룩", "털", "탈모",
            "가려", "딱지", "종기", "농양", "고름", "상처", "붉", "각질", "비듬")
_EYE_KW = ("눈", "안구", "충혈", "눈곱", "눈물", "각막", "시력", "실명", "다래끼",
           "눈꺼풀", "결막", "백내장")


def _regions(text: str, section_id: str | None) -> set[str]:
    """대화/섹션으로 어떤 CNN을 켤지 결정(피부/안구, 둘 다 가능)."""
    regions: set[str] = set()
    t = text or ""
    if section_id == "SKIN" or any(k in t for k in _SKIN_KW):
        regions.add("skin")
    if section_id == "EYE" or any(k in t for k in _EYE_KW):
        regions.add("eye")
    return regions


async def _fetch_bytes(url: str) -> bytes | None:
    try:
        from app.utils.s3 import read_object_from_url
        obj = await asyncio.to_thread(read_object_from_url, url)
        return obj.get("body")
    except Exception as e:
        logger.warning("[triage/vision] 이미지 다운로드 실패: %s", e)
        return None


async def _run_cnn(region: str, image_bytes: bytes) -> dict | None:
    try:
        from ai.services.vision_model import vision_service
        fn = vision_service.analyze_skin if region == "skin" else vision_service.analyze_eye
        res = await asyncio.to_thread(fn, image_bytes)
        if not res or res.get("error"):
            return None
        return {"model": region, "top_class": res.get("top_class"),
                "top_1": res.get("top_1"), "confidence": res.get("top_confidence"),
                "details": res.get("details")}
    except Exception as e:
        logger.warning("[triage/vision] CNN(%s) 실패: %s", region, e)
        return None


async def _run_vlm(url: str) -> str | None:
    """멀티모달 LLM으로 '보이는 소견'만 묘사(병명 단정 X)."""
    try:
        from langchain_core.messages import HumanMessage

        from ai.llm import get_llm

        msg = HumanMessage(content=[
            {"type": "text", "text": (
                "이 반려동물 사진에서 '보이는 것'만 한국어로 간단히 묘사해줘. "
                "병명을 단정하지 말고, 부위·색·붓기·분비물·상처 같은 객관적 소견만 1~2문장으로.")},
            {"type": "image_url", "image_url": {"url": url}},
        ])
        resp = await get_llm(temperature=0.2).ainvoke([msg])
        return (resp.content or "").strip() or None
    except Exception as e:
        logger.warning("[triage/vision] VLM 실패: %s", e)
        return None


async def analyze(attachments: list[str], text: str, section_id: str | None) -> dict | None:
    """이미지가 있으면 CNN(키워드 기반)+VLM 실행. 없으면 None.

    반환: {"note": 추출콜용 텍스트, "evidence": 저장용 dict, "suspected": [병명]} 또는 None
    """
    urls = [u for u in (attachments or []) if u]
    if not urls:
        return None
    url = urls[0]  # 첫 이미지 기준(영상/다중은 추후)

    regions = _regions(text, section_id)
    image_bytes = await _fetch_bytes(url)

    cnn_results: list[dict] = []
    if image_bytes and regions:
        for r in regions:
            res = await _run_cnn(r, image_bytes)
            if res:
                cnn_results.append(res)

    vlm_desc = await _run_vlm(url)

    if not cnn_results and not vlm_desc:
        return None

    # note: 추출 LLM이 variables로 매핑하도록 자연어로
    note_parts = []
    for c in cnn_results:
        note_parts.append(f"{c['model']} CNN: {c.get('top_1') or c.get('top_class')}")
    if vlm_desc:
        note_parts.append(f"이미지 소견: {vlm_desc}")
    note = " | ".join(note_parts)

    # suspected: CNN top_class(정상/보류 제외)
    suspected = [c["top_class"] for c in cnn_results
                 if c.get("top_class") and c["top_class"] not in ("healthy", "정상")
                 and (c.get("confidence") or 0) >= 70.0]

    evidence = {
        "region": sorted(regions) or None,
        "cnn": cnn_results or None,
        "vlm_description": vlm_desc,
    }
    return {"note": note, "evidence": evidence, "suspected": suspected}
