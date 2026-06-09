from sqlalchemy import Boolean, Column, Integer, Date, Time, ForeignKey
from app.db.base import Base

class VetSchedule(Base):
    __tablename__ = "vet_scheduleDB"

    vetscheduleid = Column(Integer, primary_key=True, autoincrement=True)
    doctorid = Column(Integer, ForeignKey("doctorDB.doctorid"), nullable=False)
    # date: 특정날짜 레코드는 날짜 지정, 주간 템플릿은 NULL
    date = Column(Date, nullable=True)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    lunch_start = Column(Time, nullable=True)
    lunch_end = Column(Time, nullable=True)
    # day_of_week: 주간 템플릿 0=월...6=일, 특정날짜는 NULL
    day_of_week = Column(Integer, nullable=True)
    is_open = Column(Boolean, nullable=False, default=True)
