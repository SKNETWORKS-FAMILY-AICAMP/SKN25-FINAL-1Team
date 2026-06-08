import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.services.triage_rag import (  # noqa: E402
    expand_query_llm,
    search_similar_triage_cases,
)


def _clip(text: str, max_len: int) -> str:
    text = " ".join((text or "").split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


async def run_search(args: argparse.Namespace) -> None:
    expanded_query = args.query if args.no_expand else await expand_query_llm(args.query)

    async with AsyncSessionLocal() as db:
        matches = await search_similar_triage_cases(
            db,
            args.query,
            top_k=args.top_k,
            department=args.department,
            expand_query=not args.no_expand,
        )

    if not matches:
        print("No matches found.")
        return

    print(f"Query: {args.query}")
    if expanded_query != args.query:
        print(f"Expanded query: {_clip(expanded_query, args.max_chars)}")
    print(f"Top K: {len(matches)}")
    if args.department:
        print(f"Department filter: {args.department}")
    print()

    for idx, match in enumerate(matches, start=1):
        print(f"[{idx}] similarity={match.similarity:.4f} distance={match.distance:.4f}")
        print(
            "meta: "
            f"department={match.department}, "
            f"disease={match.disease}, "
            f"life_cycle={match.life_cycle}, "
            f"source={match.source_file}"
        )
        print(f"matched input: {_clip(match.input_text, args.max_chars)}")
        print(f"answer output: {_clip(match.output_text, args.max_chars)}")
        print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search triage RAG documents with pgvector.")
    parser.add_argument("query", help="Guardian question or symptom text to search.")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--department", default=None, help="Optional department filter, e.g. 내과.")
    parser.add_argument("--max-chars", type=int, default=500)
    parser.add_argument("--no-expand", action="store_true", help="Disable LLM query expansion.")
    return parser.parse_args()


async def main() -> None:
    try:
        await run_search(parse_args())
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
