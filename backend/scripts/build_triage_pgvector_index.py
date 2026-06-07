import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from openai import OpenAI
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.core.config import settings  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.models.triage_rag_document import TriageRagDocument  # noqa: E402


DEFAULT_MODEL = "text-embedding-3-small"
DEFAULT_BATCH_SIZE = 100
TRIAGE_RAW_DIR = Path(__file__).parents[1] / "data" / "triage" / "raw"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _normalize_json(path: Path) -> dict[str, str] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[skip] invalid json: {path} ({exc})")
        return None

    meta = data.get("meta") or {}
    qa = data.get("qa") or {}
    input_text = _clean(qa.get("input"))
    output_text = _clean(qa.get("output"))

    if not input_text or not output_text:
        print(f"[skip] empty input/output: {path}")
        return None

    return {
        "source_file": path.name,
        "department": _clean(meta.get("department")) or "기타",
        "disease": _clean(meta.get("disease")) or "기타",
        "life_cycle": _clean(meta.get("lifeCycle")) or "기타",
        "input_text": input_text,
        "output_text": output_text,
    }


def _iter_documents(raw_dir: Path, limit: int | None) -> list[dict[str, str]]:
    paths = sorted(raw_dir.glob("*/*.json"))
    docs: list[dict[str, str]] = []

    for path in paths:
        doc = _normalize_json(path)
        if doc is None:
            continue
        docs.append(doc)
        if limit is not None and len(docs) >= limit:
            break

    return docs


def _embed_batch(client: OpenAI, model: str, texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(
        model=model,
        input=texts,
        dimensions=1536,
    )
    return [item.embedding for item in response.data]


async def _reset_table() -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(TriageRagDocument))
        await db.commit()


async def _upsert_batch(rows: list[dict[str, Any]]) -> None:
    stmt = insert(TriageRagDocument).values(rows)
    update_cols = {
        "department": stmt.excluded.department,
        "disease": stmt.excluded.disease,
        "life_cycle": stmt.excluded.life_cycle,
        "input_text": stmt.excluded.input_text,
        "output_text": stmt.excluded.output_text,
        "embedding": stmt.excluded.embedding,
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=[TriageRagDocument.source_file],
        set_=update_cols,
    )

    async with AsyncSessionLocal() as db:
        await db.execute(stmt)
        await db.commit()


async def _count_rows() -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(func.count()).select_from(TriageRagDocument))
        return int(result.scalar_one())


async def build_index(args: argparse.Namespace) -> None:
    # 중복방지: 이미 적재돼 있으면 재임베딩 건너뜀(비용·시간 절약). docker가 매번 실행해도
    # 안전하고, 키/원본데이터 없이도 깔끔히 종료된다. 강제 재생성은 --reset.
    existing = await _count_rows()
    if existing > 0 and not args.reset:
        print(f"[skip] triage_rag_documents에 이미 {existing}개 문서가 있습니다 → 재임베딩 건너뜀 (강제 재생성: --reset)")
        return

    api_key = settings.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required to build triage RAG embeddings")

    raw_dir = Path(args.raw_dir)
    if not raw_dir.exists():
        raise FileNotFoundError(f"triage raw dir not found: {raw_dir}")

    if args.reset:
        print("Resetting triage_rag_documents...")
        await _reset_table()

    docs = _iter_documents(raw_dir, args.limit)
    if not docs:
        print("No documents to index.")
        return

    client = OpenAI(api_key=api_key)
    total = len(docs)
    batch_size = args.batch_size

    for start in range(0, total, batch_size):
        batch_docs = docs[start : start + batch_size]
        embeddings = _embed_batch(
            client,
            args.model,
            [doc["input_text"] for doc in batch_docs],
        )
        rows = [
            {
                **doc,
                "embedding": embedding,
            }
            for doc, embedding in zip(batch_docs, embeddings, strict=True)
        ]
        await _upsert_batch(rows)
        print(f"Indexed {min(start + batch_size, total)}/{total}")

    row_count = await _count_rows()
    print(f"Done. triage_rag_documents rows: {row_count}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build pgvector index for triage Q&A JSON data.")
    parser.add_argument(
        "--raw-dir",
        default=str(TRIAGE_RAW_DIR),
        help="Directory containing department subdirectories with triage JSON files.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("TRIAGE_EMBEDDING_MODEL", DEFAULT_MODEL),
        help="OpenAI embedding model.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.environ.get("TRIAGE_EMBEDDING_BATCH_SIZE", DEFAULT_BATCH_SIZE)),
        help="Number of documents to embed per API request.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Index only the first N valid documents. Useful for smoke tests.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete all existing triage RAG documents before indexing.",
    )
    return parser.parse_args()


async def main() -> None:
    try:
        await build_index(parse_args())
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
