from sqlalchemy import Boolean, Column, DateTime, Integer, Date, Time, ForeignKey, PrimaryKeyConstraint
from sqlalchemy.sql import func
from app.db.base import Base


class HospitalWeeklySchedule(Base):
    __tablename__ = "hospital_weekly_scheduleDB"
    __table_args__ = (PrimaryKeyConstraint("hospitalid", "day_of_week"),)

    hospitalid  = Column(Integer, ForeignKey("hospitalDB.hospitalid"), nullable=False)
    day_of_week = Column(Integer, nullable=False)
    is_open     = Column(Boolean, nullable=False, default=True)
    start_time  = Column(Time, nullable=True)
    end_time    = Column(Time, nullable=True)
    lunch_start = Column(Time, nullable=True)
    lunch_end   = Column(Time, nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at  = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class HospitalClosedDate(Base):
    __tablename__ = "hospital_closed_datesDB"
    __table_args__ = (PrimaryKeyConstraint("hospitalid", "date"),)

    hospitalid = Column(Integer, ForeignKey("hospitalDB.hospitalid"), nullable=False)
    date       = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class VetWeeklySchedule(Base):
    __tablename__ = "vet_weekly_scheduleDB"
    __table_args__ = (PrimaryKeyConstraint("doctorid", "day_of_week"),)

    doctorid    = Column(Integer, ForeignKey("doctorDB.doctorid"), nullable=False)
    day_of_week = Column(Integer, nullable=False)
    is_open     = Column(Boolean, nullable=False, default=True)
    start_time  = Column(Time, nullable=True)
    end_time    = Column(Time, nullable=True)
    lunch_start = Column(Time, nullable=True)
    lunch_end   = Column(Time, nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at  = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
