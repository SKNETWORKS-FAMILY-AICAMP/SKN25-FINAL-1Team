"""gzip JSONL 덤프 → triage_rag_documents 적재 (임베딩 포함, OpenAI 불필요).

docker 기동 시 자동 적재용. 안전장치:
  - 테이블에 이미 데이터가 있으면 스킵(중복방지). 강제 재적재는 --force.
  - 덤프 파일이 없으면 에러 없이 스킵(원본 임베딩은 build_triage_pgvector_index.py로 별도 생성).

사용:
    python scripts/load_triage_rag.py                    # data/triage/triage_rag_export.jsonl.gz
    python scripts/load_triage_rag.py --in 경로.jsonl.gz --force
"""
import argparse
import asyncio
import gzip
import json
import os
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.models.triage_rag_document import TriageRagDocument  # noqa: E402

DEFAULT_IN = Path(__file__).parents[1] / "data" / "triage" / "triage_rag_export.jsonl.gz"
BATCH_SIZE = 500


def _maybe_fetch_from_s3(dest: Path) -> bool:
    """로컬 덤프가 없을 때 S3에서 받아온다(임베딩 포함 덤프 → OpenAI 호출 불필요).

    SEED_RAG_S3_BUCKET 가 설정됐을 때만 동작한다(전용 opt-in). 미설정이면 False 를 돌려
    호출부가 기존처럼 '파일 없음 → 무해 스킵' 으로 흐르게 한다(dev/로컬엔 영향 없음).
    git/이미지에 못 넣는 632MB 덤프를, 신규 EC2 프로비저닝 시에도 사람 손 없이 채우기 위한 경로.
    """
    bucket = os.getenv("SEED_RAG_S3_BUCKET")
    if not bucket:
        return False
    key = os.getenv("SEED_RAG_S3_KEY", "seed/triage_rag_export.jsonl.gz")
    try:
        import boto3

        s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "ap-northeast-2"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"[s3] 로컬 덤프 없음 → 다운로드: s3://{bucket}/{key} → {dest}")
        s3.download_file(bucket, key, str(dest))
        return dest.exists()
    except Exception as e:  # 자격증명/키 없음 등 → 무해 스킵(배포 안 깨짐)
        print(f"[s3] 다운로드 실패(스킵): {e}")
        return False


async def _count_rows() -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(func.count()).select_from(TriageRagDocument))
        return int(result.scalar_one())


async def _upsert_batch(rows: list[dict[str, Any]]) -> None:
    stmt = insert(TriageRagDocument).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[TriageRagDocument.source_file],
        set_={
            "department": stmt.excluded.department,
            "disease": stmt.excluded.disease,
            "life_cycle": stmt.excluded.life_cycle,
            "input_text": stmt.excluded.input_text,
            "output_text": stmt.excluded.output_text,
            "embedding": stmt.excluded.embedding,
        },
    )
    async with AsyncSessionLocal() as db:
        await db.execute(stmt)
        await db.commit()


async def load_dump(in_path: Path, force: bool) -> None:
    existing = await _count_rows()
    if existing > 0 and not force:
        print(f"[skip] triage_rag_documents에 이미 {existing}개 있음 → 덤프 적재 건너뜀 (강제: --force)")
        return

    if not in_path.exists():
        # 마운트된 로컬 덤프가 없으면 S3 폴백을 시도(신규 EC2 자동 복구).
        s3_dest = Path("/tmp/_seed_rag_dump.jsonl.gz")
        if _maybe_fetch_from_s3(s3_dest):
            in_path = s3_dest
        else:
            print(f"[skip] 덤프 파일 없음: {in_path} → 적재 건너뜀 "
                  f"(임베딩 생성은 build_triage_pgvector_index.py 사용)")
            return

    if force and existing > 0:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(TriageRagDocument))
            await db.commit()
        print(f"--force: 기존 {existing}개 삭제 후 재적재")

    batch: list[dict[str, Any]] = []
    total = 0
    with gzip.open(in_path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            batch.append(json.loads(line))
            if len(batch) >= BATCH_SIZE:
                await _upsert_batch(batch)
                total += len(batch)
                print(f"적재 {total}...")
                batch = []
    if batch:
        await _upsert_batch(batch)
        total += len(batch)
    print(f"Done. 덤프에서 {total}개 적재 완료 (현재 행수: {await _count_rows()})")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Load triage_rag_documents from gzip JSONL dump.")
    parser.add_argument("--in", dest="in_path", default=str(DEFAULT_IN), help="입력 경로(.jsonl.gz)")
    parser.add_argument("--force", action="store_true", help="기존 데이터 삭제 후 재적재")
    args = parser.parse_args()
    try:
        await load_dump(Path(args.in_path), args.force)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
