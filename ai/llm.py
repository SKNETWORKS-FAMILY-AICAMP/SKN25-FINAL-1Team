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