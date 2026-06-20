"""문진용 이미지/영상 분석 보조.

파이프라인:
 1) 미디어 판별(image/video). 영상은 cv2로 3프레임 균등 추출.
 2) VLM(OPENAI_VISION_MODEL)이 먼저 판단 → JSON: relevant(증상 관련?)·region(skin/eye/…)·findings(소견).
 3) relevant=false → 이미지 버림(무관 안내용 플래그).
 4) region=skin/eye → 해당 CNN 한 번 더(보조 병명+신뢰도). (VLM이 라우팅 — 텍스트 키워드 X)
 5) findings + CNN class → RAG 쿼리/suspected에 투입(시각정보 반영).
전부 fail-open: 실패하면 None/부분값만 반환하고 문진을 막지 않는다.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re

logger = logging.getLogger(__name__)

_VIDEO_EXT = (".mp4", ".mov", ".webm", ".quicktime", ".m4v")
_FRAMES = 3

_VLM_PROMPT = """이 반려동물 미디어(사진 또는 영상 프레임 여러 장)를 보고 JSON으로만 판단해.
1) relevant: 반려동물의 '건강 증상'(피부·눈·귀·상처·자세·전신 상태 등)과 관련된 이미지면 true,
   무관(풍경·사람·음식·캡처·텍스트·반려동물이지만 건강과 무관한 일상사진 등)이면 false.
2) region: 가장 두드러진 부위 — "skin" | "eye" | "wound" | "general" | "other".
3) findings: 보이는 객관적 소견 1~2문장(병명 단정 금지. 부위·색·붓기·분비물·상처·자세 등). 영상이면 프레임들을 종합.

JSON: {"relevant": true, "region": "skin", "findings": "..."}"""


def _is_video(url: str) -> bool:
    return (url or "").lower().split("?")[0].endswith(_VIDEO_EXT)


def _to_data_url(jpeg_bytes: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode("ascii")


async def _download(url: str) -> bytes | None:
    try:
        from app.utils.s3 import read_object_from_url
        obj = await asyncio.to_thread(read_object_from_url, url)
        return obj.get("body")
    except Exception as e:
        logger.warning("[triage/vision] 다운로드 실패: %s", e)
        return None


def _extract_frames_sync(video_bytes: bytes, n: int = _FRAMES) -> list[bytes]:
    """영상 bytes → 균등 간격 n프레임(jpeg bytes). cv2는 파일경로가 필요해 임시파일 사용."""
    import tempfile

    import cv2
    frames: list[bytes] = []
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(video_bytes)
            path = f.name
        cap = cv2.VideoCapture(path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        idxs = [int(total * (i + 1) / (n + 1)) for i in range(n)] if total > 0 else list(range(n))
        for idx in idxs:
            if total > 0:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if ok and frame is not None:
                ok2, buf = cv2.imencode(".jpg", frame)
                if ok2:
                    frames.append(buf.tobytes())
        cap.release()
    except Exception as e:
        logger.warning("[triage/vision] 프레임 추출 실패: %s", e)
    finally:
        if path:
            try:
                os.unlink(path)
            except Exception:
                pass
    return frames


def _parse_json(text: str) -> dict:
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", t, re.DOTALL)
    return json.loads(m.group(0)) if m else {}


async def _vlm_judge(image_inputs: list[str]) -> dict | None:
    """멀티모달 LLM(비전 전용 모델)에 이미지/프레임들 → {relevant, region, findings}."""
    try:
        from langchain_core.messages import HumanMessage
        from langchain_openai import ChatOpenAI

        model = os.getenv("OPENAI_VISION_MODEL") or os.getenv("OPENAI_MODEL")
        content: list[dict] = [{"type": "text", "text": _VLM_PROMPT}]
        for src in image_inputs:
            content.append({"type": "image_url", "image_url": {"url": src}})
        resp = await ChatOpenAI(model=model, temperature=0).ainvoke([HumanMessage(content=content)])
        return _parse_json(resp.content or "")
    except Exception as e:
        logger.warning("[triage/vision] VLM 판단 실패: %s", e)
        return None


async def _run_cnn(region: str, image_bytes: bytes) -> dict | None:
    try:
        from ai.services.vision_model import vision_service
        fn = vision_service.analyze_skin if region == "skin" else vision_service.analyze_eye
        res = await asyncio.to_thread(fn, image_bytes)
        if not res or res.get("error"):
            return None
        return {"model": region, "top_class": res.get("top_class"),
                "top_1": res.get("top_1"), "confidence": res.get("top_confidence")}
    except Exception as e:
        logger.warning("[triage/vision] CNN(%s) 실패: %s", region, e)
        return None


async def analyze(attachments: list[str], text: str) -> dict | None:
    """첨부(이미지/영상)가 있으면 분석. 없으면 None.

    반환: {relevant, note(추출콜용), evidence(저장), rag_text(RAG 투입), suspected[병명]} 또는 None.
    """
    urls = [u for u in (attachments or []) if u]
    if not urls:
        return None
    url = urls[0]

    # 1) 미디어별 VLM 입력 + CNN용 bytes 준비
    if _is_video(url):
        vbytes = await _download(url)
        frames = await asyncio.to_thread(_extract_frames_sync, vbytes) if vbytes else []
        if not frames:
            return None
        vlm_inputs = [_to_data_url(f) for f in frames]
        cnn_bytes = frames[0]
        media = "video"
    else:
        vlm_inputs = [url]              # 이미지는 URL 그대로 VLM에
        cnn_bytes = await _download(url)
        media = "image"

    # 2) VLM 판단 (관련성 + 부위 + 소견)
    v = await _vlm_judge(vlm_inputs)
    if not v:
        return None
    relevant = bool(v.get("relevant"))
    findings = (v.get("findings") or "").strip()
    region = (v.get("region") or "").strip().lower()

    # 3) 무관 이미지 → 버림(안내용 플래그만)
    if not relevant:
        return {"relevant": False, "note": "", "rag_text": "", "suspected": [],
                "evidence": {"relevant": False, "media": media, "vlm_description": findings}}

    # 4) VLM 라우팅으로 CNN 보조 (피부/안구만)
    cnn = None
    if region in ("skin", "eye") and cnn_bytes:
        cnn = await _run_cnn(region, cnn_bytes)

    # 5) 출력 조립: note(추출용) + rag_text(RAG 투입) + suspected
    note_parts = []
    if findings:
        note_parts.append(f"이미지 소견: {findings}")
    rag_text = findings
    suspected: list[str] = []
    if cnn:
        note_parts.append(f"{region}CNN: {cnn.get('top_1') or cnn.get('top_class')}")
        cls = cnn.get("top_class")
        if cls and cls not in ("healthy", "정상") and (cnn.get("confidence") or 0) >= 70.0:
            rag_text = f"{rag_text} {cls}".strip()
            suspected.append(cls)

    evidence = {"relevant": True, "media": media, "region": region,
                "cnn": cnn, "vlm_description": findings}
    return {"relevant": True, "note": " | ".join(note_parts),
            "evidence": evidence, "rag_text": rag_text, "suspected": suspected}
