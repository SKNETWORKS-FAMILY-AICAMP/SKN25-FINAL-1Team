import json
import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()


def get_llm(
    temperature: float = 0.3,
):
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL"),
        temperature=temperature,
    )


async def call_llm(
    prompt: str,
    temperature: float = 0.3,
):
    llm = get_llm(
        temperature=temperature,
    )

    response = await llm.ainvoke(prompt)

    return response.content


async def call_llm_json(
    prompt: str,
    temperature: float = 0,
):
    text = await call_llm(
        prompt=prompt,
        temperature=temperature,
    )

    return json.loads(text)


# 구조화 출력 — JSON 스키마로 형식·enum 강제 (누락/오염 방지)
async def call_llm_structured(
    prompt: str,
    schema: dict,
    temperature: float = 0,
):
    llm = get_llm(temperature=temperature)

    structured = llm.with_structured_output(
        schema,
        method="json_schema",
        strict=True,
    )

    return await structured.ainvoke(prompt)