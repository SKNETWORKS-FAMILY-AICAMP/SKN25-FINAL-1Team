import asyncio
import csv
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://medipaw:medipaw_secret@localhost:5432/medipaw",
)
ASYNC_URL = (
    DATABASE_URL
    .replace("postgresql://", "postgresql+asyncpg://")
    .replace("postgresql+psycopg2://", "postgresql+asyncpg://")
)

CSV_PATH = Path(__file__).parents[1] / "data" / "pet_drug.csv"


async def main():
    engine = create_async_engine(ASYNC_URL, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        count_row = (await db.execute(text('SELECT COUNT(*) FROM "drugsDB"'))).fetchone()
        if count_row and count_row[0] > 0:
            print(f"✅ drugsDB에 이미 {count_row[0]}개 데이터가 있습니다. 스킵합니다.")
            await engine.dispose()
            return

        rows = []
        with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("품목명", "").strip()
                if not name:
                    continue
                rows.append({
                    "name": name,
                    "ingredient_kr": row.get("성분명(국문)", "").strip() or "-",
                    "ingredient_en": row.get("성분명(영문)", "").strip() or "-",
                })

        for r in rows:
            await db.execute(
                text("""
                    INSERT INTO "drugsDB" (name, ingredient_kr, ingredient_en)
                    VALUES (:name, :ingredient_kr, :ingredient_en)
                """),
                r,
            )

        await db.commit()
        print(f"✅ drugsDB에 {len(rows)}개 약품 데이터 삽입 완료!")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
