from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact_inquiry import ContactInquiry


async def create_contact(db: AsyncSession, name: str, phone: str, email: str, user_type: str, message: str) -> ContactInquiry:
    row = ContactInquiry(name=name, phone=phone, email=email, user_type=user_type, message=message)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_contacts(db: AsyncSession) -> list[ContactInquiry]:
    result = await db.execute(select(ContactInquiry).order_by(ContactInquiry.created_at.desc()))
    return list(result.scalars().all())


async def get_contact(db: AsyncSession, contact_id: int) -> ContactInquiry | None:
    return await db.get(ContactInquiry, contact_id)


async def mark_replied(db: AsyncSession, contact_id: int) -> ContactInquiry | None:
    row = await db.get(ContactInquiry, contact_id)
    if not row:
        return None
    row.is_replied = True
    await db.commit()
    await db.refresh(row)
    return row


def to_out(row: ContactInquiry) -> dict:
    return {
        "id":         row.id,
        "name":       row.name,
        "phone":      row.phone,
        "email":      row.email,
        "user_type":  row.user_type,
        "message":    row.message,
        "is_replied": row.is_replied,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
