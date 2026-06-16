import base64
import json
import logging

from langchain_openai import ChatOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pet import Pet
from app.schemas.chat import ChatMessageRequest
from app.crud.chat import (
    get_chat_session,
    add_message,
    update_session_complete,
)
from app.core.config import settings
from app.utils.s3 import read_object_bytes_from_url
from app.services.translation import translate_batch

from ai.agents.triage.agent import TriageAgent

logger = logging.getLogger(__name__)


# 이미지 확장자 → MIME 타입
def _mime_type_from_url(image_url: str) -> str:
    lower = image_url.lower().split("?", 1)[0]
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


# OpenAI vision 
async def _describe_photo_openai(image_url: str, image_bytes: bytes, user_text: str) -> dict | None:
    try:
        encoded = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{_mime_type_from_url(image_url)};base64,{encoded}"
        llm = ChatOpenAI(
            model=settings.OPENAI_VISION_MODEL or settings.OPENAI_MODEL,
            api_key=settings.OPENAI_API_KEY,
            temperature=0.0,
            timeout=45.0,
            max_retries=0,
            model_kwargs={"response_format": {"type": "json_object"}},
        )
        response = await llm.ainvoke([
            {
                "role": "system",
                "content": (
                    "당신은 반려동물 사진에서 보이는 특징만 관찰하는 보조 모델입니다. "
                    "진단명이나 확정 판단은 하지 마세요. 한국어 JSON만 출력하세요."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"보호자 말: {user_text or '첨부 사진만 전달됨'}\n"
                            "사진에서 명확히 보이는 변화만 적어주세요. "
                            "붉은 부위, 돌출, 털 빠짐, 상처, 진물/출혈처럼 보이는 흔적이 있으면 포함하세요.\n"
                            '형식: {"visible_changes":["..."],"lesion_location":"...","question_focus":"..."}'
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
                ],
            },
        ])
        raw = response.content if isinstance(response.content, str) else "{}"
        return json.loads(raw or "{}")
    except Exception as exc:
        logger.warning("[Vision/OpenAI] 관찰 실패 image_url=%s: %s", image_url, exc)
        return None


# 이미지 첨부 시 3개 모델(피부 CNN · 안구 CNN · OpenAI vision) 모두 실행
async def analyze_image(image_url: str, user_text: str) -> dict | None:
    try:
        image_bytes = read_object_bytes_from_url(image_url)
    except Exception as exc:
        logger.warning("[Vision] 이미지 로드 실패 image_url=%s: %s", image_url, exc)
        return None

    analysis: dict = {}

    # 피부·안구 CNN (torch 미설치 환경에서는 건너뜀)
    try:
        from ai.services.vision_model import vision_service
        analysis["skin"] = vision_service.analyze_skin(image_bytes)
        analysis["eye"] = vision_service.analyze_eye(image_bytes)
    except Exception as exc:
        logger.warning("[Vision/CNN] 건너뜀: %s", exc)

    observation = await _describe_photo_openai(image_url, image_bytes, user_text)
    if observation:
        analysis["visual_observation"] = observation

    return analysis or None


# 상담 제목(주요증상) 언어 고정 — 완료 시점 UI 언어로 번역해 DB에 박제. 이후 언어를 바꿔도 재번역 안 함.
async def _localize_title_keywords(keywords: list[str], lang: str) -> list[str]:
    # 한국어면 원문 그대로 (트리아지 결과가 이미 한국어라 번역 불필요)
    if not keywords or (lang or "ko") == "ko":
        return keywords
    return await translate_batch(keywords, lang)


async def process_chat_message(
    db: AsyncSession,
    session_id: int,
    userid: int,
    request: ChatMessageRequest,
):

    session = await get_chat_session(
        db,
        session_id,
        userid,
    )

    if not session:
        raise ValueError("상담 세션을 찾을 수 없습니다.")

    # 사용자 메시지 저장
    await add_message(
        db,
        session,
        "user",
        request.content,
        request.image_url,
    )

    # 이미지 첨부 시 분석 (피부·안구·OpenAI vision)
    image_analysis = None
    if request.image_url:
        # 진행 상태 알림: 이미지 분석중
        yield {"type": "status", "phase": "image_analysis"}
        image_analysis = await analyze_image(request.image_url, request.content or "")

    # 최신 대화 다시 조회
    session = await get_chat_session(
        db,
        session_id,
        userid,
    )

    # 반려동물 정보 조회
    pet_result = await db.execute(
        select(Pet).where(
            Pet.petid == session.petid
        )
    )

    pet = pet_result.scalar_one()

    pet_info = {
        "species": pet.species,
        "breed": pet.breed,
        "gender": pet.gender,
        # Numeric(Decimal) → float: json 직렬화 가능하도록
        "weight": float(pet.weight_kg) if pet.weight_kg is not None else None,
    }

    # 진행 상태 알림: 질문(응답) 생성중
    yield {"type": "status", "phase": "generating"}

    # Triage Agent 실행
    triage_agent = TriageAgent()

    result = await triage_agent.process_message(
        user_message=request.content,
        messages=session.messages or [],
        pet_info=pet_info,
        image_analysis=image_analysis,
    )

    # 응급 상황
    if result.get("red_flag"):

        await add_message(
            db,
            session,
            "assistant",
            result["reply"],
            meta=result.get("state"),
        )

        # 상담 제목 = 응급 주증상(명사형) → 완료 시점 언어로 번역해 저장, 완료 처리
        chief = result.get("chief_complaints") or []
        title_keywords = await _localize_title_keywords(chief[:2], request.lang)
        await update_session_complete(db, session, title_keywords)

        # 최종 결과 전달
        yield {
            "type": "result",
            "result": {
                "reply": result["reply"],
                "red_flag": True,
                "urgency": result.get(
                    "urgency",
                    "RED",
                ),
                "is_complete": True,
                "keywords": title_keywords,
            },
        }
        return

    # 문진 완료
    if result.get("is_complete"):

        await add_message(
            db,
            session,
            "assistant",
            "문진이 완료되었습니다.",
            meta=result.get("state"),
        )

        # 상담 제목 = 주요 증상 2개(명사형 키워드) → 완료 시점 언어로 번역해 저장
        chief = result.get("chief_complaints") or []
        title_keywords = await _localize_title_keywords(chief[:2], request.lang)
        await update_session_complete(db, session, title_keywords)

        # 최종 결과 전달
        yield {
            "type": "result",
            "result": {
                "reply": "문진이 완료되었습니다.",
                "is_complete": True,
                "urgency": result["urgency"],
                "score": result["score"],
                "triage_summary": result["triage_summary"],
                # 다운스트림(차트·RAG)용은 한국어 원본 유지, 제목용 keywords만 번역
                "chief_complaints": result["chief_complaints"],
                "suspected_conditions": result["suspected_conditions"],
                "keywords": title_keywords,
            },
        }
        return

    # 일반 문진 진행
    await add_message(
        db,
        session,
        "assistant",
        result["reply"],
        meta=result.get("state"),
    )

    # 최종 결과 전달
    yield {
        "type": "result",
        "result": {
            "reply": result["reply"],
            "is_complete": False,
            "quick_replies": result.get("quick_replies", []),
        },
    }