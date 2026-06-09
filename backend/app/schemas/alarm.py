from typing import Optional
from pydantic import BaseModel


class AlarmItem(BaseModel):
    alarmid: int
    type: str
    contents: str
    scheduleid: Optional[int]
    is_read: bool
    created_at: Optional[str]


class AlarmListResponse(BaseModel):
    alarm_list: list[AlarmItem]
