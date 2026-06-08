"""triage_rag_documents → gzip JSONL 익스포트 (팀 공유/적재용 덤프).

임베딩까지 포함해 내보내므로, 받는 쪽은 OpenAI 호출 없이 load_triage_rag.py로 적재할 수 있다.
원본 데이터·임베딩은 git에 커밋하지 않고(.gitignore) 이 덤프 파일로 공유한다.

사용:
    python scripts/export_triage_rag.py                 # data/triage/triage_rag_export.jsonl.gz
    python scripts/export_triage_rag.py --out 경로.jsonl.gz
"""
import argparse
import asyncio
import gzip
import json
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.models.triage_rag_document import TriageRagDocument  # noqa: E402

DEFAULT_OUT = Path(__file__).parents[1] / "data" / "triage" / "triage_rag_export.jsonl.gz"


async def export_dump(out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(TriageRagDocument).order_by(TriageRagDocument.id))
        rows = result.scalars().all()
        with gzip.open(out_path, "wt", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps({
                    "source_file": r.source_file,
                    "department": r.department,
                    "disease": r.disease,
                    "life_cycle": r.life_cycle,
                    "input_text": r.input_text,
                    "output_text": r.output_text,
                    "embedding": [float(x) for x in r.embedding],
                }, ensure_ascii=False) + "\n")
                count += 1
    return count


async def main() -> None:
    parser = argparse.ArgumentParser(description="Export triage_rag_documents to gzip JSONL.")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="출력 경로(.jsonl.gz)")
    args = parser.parse_args()
    try:
        out = Path(args.out)
        n = await export_dump(out)
        print(f"Exported {n} rows → {out}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
