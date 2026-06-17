from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.crud import contact_inquiry as ci_crud

router = APIRouter(prefix="/contact", tags=["contact"])


class ContactIn(BaseModel):
    name: str
    phone: str
    email: EmailStr
    user_type: str
    message: str


@router.post("")
async def submit_contact(body: ContactIn, db: AsyncSession = Depends(get_db)):
    row = await ci_crud.create_contact(
        db,
        name=body.name,
        phone=body.phone,
        email=body.email,
        user_type=body.user_type,
        message=body.message,
    )
    return {"code": 200, "result": {"id": row.id}}
