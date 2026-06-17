import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report import Report
from app.models.alarm import DoctorAlarm
from app.models.schedule import Schedule

logger = logging.getLogger(__name__)


# 차트 결과 저장 — reportDB upsert + 수의사 chart_ready 알람
async def save_chart_report(db: AsyncSession, emrid: int, scheduleid: int, result: dict) -> None:
    try:
        # reportDB upsert (emrid, scheduleid 기준)
        existing = await db.execute(
            select(Report).where(Report.emrid == emrid, Report.scheduleid == scheduleid)
        )
        report = existing.scalar_one_or_none()
        if report:
            report.ai_draft_json = result
            report.status = "complete"
        else:
            db.add(Report(emrid=emrid, scheduleid=scheduleid, ai_draft_json=result, status="complete"))

        # 수의사 알람 (미읽음 chart_ready 중복 방지)
        sched = (await db.execute(
            select(Schedule).where(Schedule.scheduleid == scheduleid)
        )).scalar_one_or_none()
        if sched:
            dup = await db.execute(
                select(DoctorAlarm).where(
                    DoctorAlarm.scheduleid == scheduleid,
                    DoctorAlarm.type == "chart_ready",
                    DoctorAlarm.is_read.is_(False),
                )
            )
            if not dup.scalar_one_or_none():
                db.add(DoctorAlarm(
                    doctorid=sched.doctorid,
                    scheduleid=scheduleid,
                    type="chart_ready",
                    contents="새 환자의 AI 차트 초안이 준비되었습니다.",
                ))

        await db.commit()
        logger.info("[Chart] reportDB 저장 emrid=%s scheduleid=%s", emrid, scheduleid)
    except Exception as e:
        await db.rollback()
        logger.error("[Chart] reportDB 저장 실패 emrid=%s: %s", emrid, e)
