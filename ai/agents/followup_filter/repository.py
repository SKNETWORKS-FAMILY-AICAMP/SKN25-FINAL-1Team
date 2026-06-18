"""경과(followupDB) 저장 로직.  담당: B

실제 모델: app.models.followup.Followup  (table "followupDB")
컬럼: followupid(PK) / emrid(FK guardianDB.emrid, NOT NULL) / userid(NOT NULL)
      / images(JSON, NOT NULL) / message(Text) / ai_summary(Text)
      / emergency_alert(Boolean) / created_at

★ FK 기준은 emrid 다. (scheduleid 컬럼은 followupDB에 없음 — 저장에 안 씀)
★ category / severity_hint 전용 컬럼이 없어, 분류 메타는 아직 DB에 저장하지 못한다.
  - 누적 경과 요약 → ai_summary
  - severity_hint == urgent_possible → emergency_alert=True
  자세한 한계는 TODO 참고.
"""
from __future__ import annotations

from typing import Any


async def save_followup(
    db: Any,
    *,
    emrid: int,
    userid: int,
    message: str,
    images: list[str] | None,
    ai_summary: str,
    emergency_alert: bool,
):
    """followupDB에 경과 한 행 적재. 성공 시 ORM row, 실패/스킵 시 None.

    emrid / userid 는 NOT NULL FK 라 둘 다 있어야 저장한다.
    """
    if db is None or emrid is None or userid is None:
        return None

    # 기존 인라인 저장(agent.py)과 동일하게, 모델은 호출 시점에 import.
    from app.models.followup import Followup

    row = Followup(
        emrid=emrid,
        userid=userid,
        images=images or [],
        message=message,
        ai_summary=ai_summary or None,
        emergency_alert=emergency_alert,
    )
    try:
        db.add(row)
        await db.commit()
        return row
    except Exception:
        await db.rollback()
        return None
