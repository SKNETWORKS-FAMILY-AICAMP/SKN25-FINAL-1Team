from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_doctor
from app.db.session import get_db
from app.models.doctor import Doctor
from app.crud.alarm import get_alarms, mark_all_read
from app.schemas.alarm import AlarmItem, AlarmListResponse
from app.schemas.common import MessageResponse

router = APIRouter(prefix="/doctor/alarm", tags=["doctor-alarm"])


@router.get("/list", response_model=AlarmListResponse, status_code=200)
async def alarm_list(
    page: int = 1,
    db: AsyncSession = Depends(get_db),
    current_doctor: Doctor = Depends(get_current_doctor),
):
    alarms = await get_alarms(db, current_doctor.doctorid)
    return AlarmListResponse(
        alarm_list=[
            AlarmItem(
                alarmid=a.alarmid,
                type=a.type,
                contents=a.contents,
                scheduleid=a.scheduleid,
                is_read=a.is_read,
                created_at=a.created_at.isoformat() if a.created_at else None,
            )
            for a in alarms
        ]
    )


@router.patch("/read-all", response_model=MessageResponse, status_code=200)
async def alarm_read_all(
    db: AsyncSession = Depends(get_db),
    current_doctor: Doctor = Depends(get_current_doctor),
):
    count = await mark_all_read(db, current_doctor.doctorid)
    return MessageResponse(message=f"{count}건의 알람을 읽음 처리했습니다.")
