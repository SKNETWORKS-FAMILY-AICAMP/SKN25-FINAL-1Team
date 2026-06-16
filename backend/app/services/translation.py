import json
import logging

from langchain_openai import ChatOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

# 지원 언어 코드 → 영문 언어명 (번역 프롬프트용)
LANG_NAMES = {
    "ko": "Korean",
    "en": "English",
    "ja": "Japanese",
    "zh": "Simplified Chinese",
}


# 문구 일괄 번역
async def translate_batch(texts: list[str], target: str) -> list[str]:
    """주어진 문구들을 target 언어로 일괄 번역한다. 실패 시 원문을 그대로 반환."""
    target = target if target in LANG_NAMES else "en"
    items = [(i, text) for i, text in enumerate(texts) if text and text.strip()]
    translations: list[str] = list(texts)
    if not items:
        return translations

    try:
        llm = ChatOpenAI(
            model=settings.OPENAI_MODEL or "gpt-4o-mini",
            api_key=settings.OPENAI_API_KEY,
            temperature=0.0,
            timeout=30.0,
            max_retries=1,
            model_kwargs={"response_format": {"type": "json_object"}},
        )
        numbered = "\n".join(f'{i}: {text}' for i, text in items)
        response = await llm.ainvoke(
            [
                {
                    "role": "system",
                    "content": (
                        f"You are a translation engine. Translate each numbered line into {LANG_NAMES[target]}. "
                        "Keep meaning, tone, emojis, numbers, dates and times unchanged. "
                        "If a line is already in the target language, return it unchanged. "
                        'Return ONLY a JSON object of the form {"translations": {"<index>": "<translated text>"}} '
                        "using the same indices you were given."
                    ),
                },
                {"role": "user", "content": numbered},
            ],
            config={"run_name": "chat_translate"},
        )
        raw = response.content if isinstance(response.content, str) else "{}"
        parsed = json.loads(raw or "{}")
        mapping = parsed.get("translations", parsed)
        if isinstance(mapping, dict):
            for i, _ in items:
                value = mapping.get(str(i), mapping.get(i))
                if isinstance(value, str) and value.strip():
                    translations[i] = value
    except Exception as exc:
        # 번역 실패 시 원문을 그대로 반환 — 화면이 비지 않도록 한다.
        logger.warning("[Translate] failed target=%s: %s", target, exc, exc_info=True)

    return translations
