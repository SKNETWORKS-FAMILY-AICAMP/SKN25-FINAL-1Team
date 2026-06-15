"""테스트 계정 생성 스크립트.

사용법:
  cd backend
  DATABASE_URL=postgresql://medipaw:medipaw_secret@localhost:5432/medipaw \
    python scripts/create_test_accounts.py

생성 계정:
  보호자(guardian): guardian_test / Test1234!
  병원(hospital):   admin / Test1234!
  의사 1:           관리자 (license: 3-4070)
  의사 2:           김수의 (license: 3-9999)
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, text

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://medipaw:medipaw_secret@localhost:5432/medipaw")
ASYNC_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://").replace("postgresql+psycopg2://", "postgresql+asyncpg://")

from app.core.security import hash_password


async def main():
    engine = create_async_engine(ASYNC_URL, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        # ── 보호자 계정 ──────────────────────────────
        result = await db.execute(text('SELECT userid FROM "userDB" WHERE loginid = :id'), {"id": "guardian_test"})
        if result.fetchone():
            await db.execute(text("""
                UPDATE "userDB"
                SET password = :pw, name = :name, phone = :phone, updated_at = now()
                WHERE loginid = :loginid
            """), {
                "loginid": "guardian_test",
                "pw": hash_password("Test1234!"),
                "name": "테스트보호자",
                "phone": "010-0000-0001",
            })
            await db.commit()
            print("✅ 보호자 계정 비밀번호 갱신 완료: guardian_test")
        else:
            await db.execute(text("""
                INSERT INTO "userDB" (loginid, password, name, phone, created_at, updated_at)
                VALUES (:loginid, :pw, :name, :phone, now(), now())
            """), {
                "loginid": "guardian_test",
                "pw": hash_password("Test1234!"),
                "name": "테스트보호자",
                "phone": "010-0000-0001",
            })
            await db.commit()
            print("✅ 보호자 계정 생성: guardian_test / Test1234!")

        # ── 반려동물 (보호자에 연결) ─────────────────
        user_row = (await db.execute(
            text('SELECT userid FROM "userDB" WHERE loginid = :id'), {"id": "guardian_test"}
        )).fetchone()
        uid = user_row[0]

        pet_row = (await db.execute(
            text('SELECT petid FROM "petDB" WHERE userid = :uid AND petname = :name'), {"uid": uid, "name": "뽀미"}
        )).fetchone()

        if pet_row:
            print("✅ 반려동물 이미 존재: 뽀미")
        else:
            await db.execute(text("""
                INSERT INTO "petDB" (userid, petname, species, breed, gender, weight_kg, birth_date, is_neutered)
                VALUES (:uid, '뽀미', 'dog', '말티즈', 'female', 3.2, '2021-03-15', true)
            """), {"uid": uid})
            await db.commit()
            print("✅ 반려동물 생성: 뽀미 (말티즈 / 3.2kg)")

        # ── vet_test 계정 삭제 ───────────────────────
        vet_test_row = (await db.execute(
            text('SELECT doctorid FROM "doctorDB" WHERE license_number = :lnum'), {"lnum": "vet_test_license"}
        )).fetchone()
        if vet_test_row:
            await db.execute(text('DELETE FROM "doctorDB" WHERE license_number = :lnum'), {"lnum": "vet_test_license"})
            await db.commit()
            print("🗑️  vet_test 계정 삭제 완료")

        # ── MediPaw 병원 seed (loginid/password 포함) ──
        HOSPITAL_BNUM = "000-00-00001"
        hosp_row = (await db.execute(
            text('SELECT hospitalid FROM "hospitalDB" WHERE business_number = :bnum'),
            {"bnum": HOSPITAL_BNUM},
        )).fetchone()

        if hosp_row:
            hospital_id = hosp_row[0]
            await db.execute(text("""
                UPDATE "hospitalDB"
                SET loginid = :loginid, password = :pw, is_initial_password = false, updated_at = now()
                WHERE hospitalid = :hid
            """), {
                "loginid": "admin",
                "pw": hash_password("Test1234!"),
                "hid": hospital_id,
            })
            await db.commit()
            print(f"✅ 병원 계정 갱신: MediPaw 동물병원 (hospitalid={hospital_id})")
        else:
            result = await db.execute(text("""
                INSERT INTO "hospitalDB"
                  (hospital_name, hospital_address, hospital_number, business_number,
                   loginid, password, is_initial_password, created_at, updated_at)
                VALUES
                  ('MediPaw 동물병원', '서울시 강남구 테스트로 1', '02-0000-0001', :bnum,
                   :loginid, :pw, false, now(), now())
                RETURNING hospitalid
            """), {
                "bnum": HOSPITAL_BNUM,
                "loginid": "admin",
                "pw": hash_password("Test1234!"),
            })
            await db.commit()
            hospital_id = result.fetchone()[0]
            print(f"✅ 병원 생성: MediPaw 동물병원 (hospitalid={hospital_id})")

        # ── 수의사 1: 관리자 ───────────────────────────
        doc1_row = (await db.execute(
            text('SELECT doctorid FROM "doctorDB" WHERE license_number = :lnum AND hospitalid = :hid'),
            {"lnum": "3-4070", "hid": hospital_id},
        )).fetchone()

        if doc1_row:
            await db.execute(text("""
                UPDATE "doctorDB"
                SET doctor_name = :dname, license_number = :lnum,
                    email = :email, updated_at = now()
                WHERE doctorid = :did
            """), {
                "dname": "관리자",
                "lnum": "3-4070",
                "email": "aoj.medipaw@gmail.com",
                "did": doc1_row[0],
            })
            await db.commit()
            print(f"✅ 수의사1 갱신: 관리자 (doctorid={doc1_row[0]})")
        else:
            result = await db.execute(text("""
                INSERT INTO "doctorDB" (hospitalid, doctor_name, license_number, email, created_at, updated_at)
                VALUES (:hid, :dname, :lnum, :email, now(), now())
                RETURNING doctorid
            """), {
                "hid": hospital_id,
                "dname": "관리자",
                "lnum": "3-4070",
                "email": "aoj.medipaw@gmail.com",
            })
            await db.commit()
            did1 = result.fetchone()[0]
            print(f"✅ 수의사1 생성: 관리자 (doctorid={did1})")

        # ── 수의사 2: 김수의 ───────────────────────────
        doc2_row = (await db.execute(
            text('SELECT doctorid FROM "doctorDB" WHERE license_number = :lnum AND hospitalid = :hid'),
            {"lnum": "3-9999", "hid": hospital_id},
        )).fetchone()

        if doc2_row:
            print(f"✅ 수의사2 이미 존재: 김수의 (doctorid={doc2_row[0]})")
        else:
            result = await db.execute(text("""
                INSERT INTO "doctorDB" (hospitalid, doctor_name, license_number, email, created_at, updated_at)
                VALUES (:hid, :dname, :lnum, :email, now(), now())
                RETURNING doctorid
            """), {
                "hid": hospital_id,
                "dname": "김수의",
                "lnum": "3-9999",
                "email": "vet2.medipaw@gmail.com",
            })
            await db.commit()
            did2 = result.fetchone()[0]
            print(f"✅ 수의사2 생성: 김수의 (doctorid={did2})")

    await engine.dispose()
    print("\n완료! 아래 계정으로 로그인하세요:")
    print("  보호자: http://localhost:5173  →  guardian_test / Test1234!")
    print("  병원:   http://localhost:5174  →  admin / Test1234!")
    print("           소속 수의사: 관리자 (면허 3-4070), 김수의 (면허 3-9999)")


if __name__ == "__main__":
    asyncio.run(main())
