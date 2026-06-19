import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.models.chat_history import ChatHistory  # noqa: E402
from app.models.triage_result import TriageResult  # noqa: E402


def _json_default(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _triage_to_dict(row: TriageResult | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "emrid": row.emrid,
        "urgency_level": row.urgency_level,
        "urgency_level_num": row.urgency_level_num,
        "vtl_basis": row.vtl_basis,
        "red_flags": row.red_flags,
        "chief_complaint": row.chief_complaint,
        "symptom_onset": row.symptom_onset,
        "symptom_keywords": row.symptom_keywords,
        "suspected_diseases": row.suspected_diseases,
        "symptom_summary": row.symptom_summary,
        "recommended_action": row.recommended_action,
        "matched_discriminators": row.matched_discriminators,
        "extracted_variables": row.extracted_variables,
        "vision_evidence": row.vision_evidence,
        "created_at": row.created_at,
    }


def _last_assistant_meta(session: ChatHistory | None) -> dict[str, Any] | None:
    if session is None:
        return None
    for message in reversed(session.messages or []):
        if message.get("role") == "assistant" and isinstance(message.get("meta"), dict):
            return message["meta"]
    return None


async def _load_session(args: argparse.Namespace) -> ChatHistory | None:
    async with AsyncSessionLocal() as db:
        if args.session_id:
            result = await db.execute(
                select(ChatHistory).where(ChatHistory.id == args.session_id)
            )
            return result.scalar_one_or_none()

        if args.emrid:
            result = await db.execute(
                select(ChatHistory)
                .where(ChatHistory.emrid == args.emrid)
                .order_by(desc(ChatHistory.updated_at))
                .limit(1)
            )
            return result.scalar_one_or_none()

        result = await db.execute(
            select(ChatHistory)
            .where(ChatHistory.emrid.is_not(None))
            .order_by(desc(ChatHistory.updated_at))
            .limit(1)
        )
        return result.scalar_one_or_none()


async def _load_triage(emrid: int | None) -> TriageResult | None:
    if emrid is None:
        return None
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(TriageResult)
            .where(TriageResult.emrid == emrid)
            .order_by(desc(TriageResult.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()


async def inspect_payload(args: argparse.Namespace) -> None:
    session = await _load_session(args)
    if session is None:
        print("No matching chat session found.")
        return

    triage = await _load_triage(session.emrid)
    meta = _last_assistant_meta(session)

    payload = {
        "chat_session": {
            "session_id": session.id,
            "userid": session.userid,
            "petid": session.petid,
            "emrid": session.emrid,
            "is_complete": session.is_complete,
            "keywords": session.keywords,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        },
        "triage_result_for_chart_or_schedule": _triage_to_dict(triage),
        "last_assistant_meta": meta,
        "rag_context_from_meta": (meta or {}).get("rag_context"),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect stored triage payload values passed toward chart/schedule agents."
    )
    parser.add_argument("--session-id", type=int, default=None)
    parser.add_argument("--emrid", type=int, default=None)
    return parser.parse_args()


async def main() -> None:
    try:
        await inspect_payload(parse_args())
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
