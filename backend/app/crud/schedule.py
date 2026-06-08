from sqlalchemy import select, or_, and_, case, text
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime, timedelta, timezone, date as _date_type
from app.models.guardian import Guardian
from app.models.schedule import Schedule
from app.models.master import CategoryMaster
from app.models.pet import Pet
from app.models.doctor import Doctor
from app.utils.timezone import to_kst, KST

# 병원 휴무일: 주말 + 법정 공휴일 (2026~2027)
_HOLIDAYS: frozenset[str] = frozenset({
    "2026-01-01", "2026-02-16", "2026-02-17", "2026-02-18",
    "2026-03-01", "2026-03-02", "2026-05-01", "2026-05-05",
    "2026-05-24", "2026-05-25", "2026-06-03", "2026-06-06",
    "2026-07-17", "2026-08-15", "2026-08-17", "2026-09-24",
    "2026-09-25", "2026-09-26", "2026-10-03", "2026-10-05",
    "2026-10-09", "2026-12-25",
    "2027-01-01", "2027-02-06", "2027-02-07", "2027-02-08",
    "2027-02-09", "2027-03-01", "2027-05-01", "2027-05-05",
    "2027-05-13", "2027-06-06", "2027-07-17", "2027-08-15",
    "2027-08-16", "2027-09-14", "2027-09-15", "2027-09-16",
    "2027-10-03", "2027-10-04", "2027-10-09", "2027-10-11",
    "2027-12-25", "2027-12-27",
})


def _is_clinic_closed(d: _date_type) -> bool:
    """토요일·일요일·법정공휴일이면 True."""
    if d.weekday() >= 5:  # 5=토, 6=일
        return True
    return d.isoformat() in _HOLIDAYS


async def _lock_slot(db: AsyncSession, doctorid: int, slot_dt: datetime) -> None:
    """동일 (의사, 시각) 슬롯에 대한 동시 예약을 직렬화한다.

    select-then-insert race(빈 슬롯이라 row lock 불가)를 막기 위해
    PostgreSQL advisory transaction lock을 사용한다. 트랜잭션 커밋/롤백 시 자동 해제된다.
    두 요청이 같은 슬롯을 노리면 한쪽이 커밋(예약 생성)할 때까지 다른 쪽이 대기 →
    뒤 요청의 충돌 검사가 앞 예약을 보게 되어 이중 예약이 방지된다.

    키: (doctorid:int4, 분 단위 epoch:int4) — pg_advisory_xact_lock(int4, int4)

    advisory lock은 PostgreSQL 전용이다. SQLite 등 다른 dialect에서는 no-op로 건너뛴다.
    (SQLite는 쓰기를 자체 직렬화하므로 로컬/데모에선 기능적으로 안전하다.)
    """
    try:
        dialect = db.bind.dialect.name
    except Exception:
        try:
            dialect = db.get_bind().dialect.name
        except Exception:
            dialect = ""
    if dialect != "postgresql":
        return

    slot_key = int(slot_dt.timestamp()) // 60  # 분 단위 (int4 범위 내)
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:d, :s)"),
        {"d": int(doctorid), "s": slot_key},
    )


# 정기검진 예약 생성
async def create_checkup_schedule(db: AsyncSession, pet_id: int, date: str, time: str, memo: str, doctorid: int, category_code: int = 1):

    result = await db.execute(
        select(CategoryMaster).where(CategoryMaster.code == category_code)
    )
    category = result.scalar_one_or_none()
    if not category:
        result = await db.execute(select(CategoryMaster))
        category = result.scalars().first()

    # 예약 시간 설정 — 입력은 KST 기준, KST-aware datetime으로 만들어야 PostgreSQL이 UTC로 변환 저장
    kst_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M").replace(tzinfo=KST)

    # 동시 예약 직렬화 (advisory lock) — 충돌 검사 전에 슬롯을 잠근다
    await _lock_slot(db, doctorid, kst_dt)

    # 슬롯 충돌 체크 — Guardian 생성 전에 먼저 확인 (race condition 방지)
    conflict_result = await db.execute(
        select(Schedule).where(
            Schedule.confirmed_time == kst_dt,
            Schedule.doctorid == doctorid,
            Schedule.status != "CANCELLED",
            Schedule.deleted_at.is_(None),
        )
    )
    if conflict_result.scalar_one_or_none():
        return None, None  # 슬롯 충돌 — 호출부에서 409 처리

    # guardianDB 생성
    guardian = Guardian(
        petid=pet_id,
        category_id=category.id,
        date=datetime.strptime(date, "%Y-%m-%d").date(),
        memo=memo
    )
    db.add(guardian)
    await db.flush()

    confirmed_end_time = kst_dt + timedelta(minutes=30)

    # scheduleDB 생성
    schedule = Schedule(
        emrid=guardian.emrid,
        doctorid=doctorid,
        duration_min=30,
        confirmed_time=kst_dt,
        confirmed_end_time=confirmed_end_time,
        status="CONFIRMED"
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    return schedule, guardian


# 예약 상세 조회
async def get_schedule_by_id(db: AsyncSession, schedule_id: int):
    result = await db.execute(
        select(Schedule).where(Schedule.scheduleid == schedule_id)
    )
    return result.scalar_one_or_none()


# emrid 소유자(보호자 userid) 조회 — 소유권 검증용
# 경로: guardianDB.emrid → guardianDB.petid → petDB.userid
async def get_emrid_owner_userid(db: AsyncSession, emrid: int) -> int | None:
    result = await db.execute(
        select(Pet.userid)
        .join(Guardian, Guardian.petid == Pet.petid)
        .where(Guardian.emrid == emrid)
    )
    return result.scalar_one_or_none()


# 예약 목록 조회 (페이지네이션)
async def get_schedules_by_userid(db: AsyncSession, userid: int, page: int, size: int, filter: str = "all"):
    offset = (page - 1) * size

    conditions = [Pet.userid == userid]

    if filter == "upcoming":
        conditions.append(Schedule.status == "CONFIRMED")
        conditions.append(Schedule.confirmed_time > datetime.now(timezone.utc))
        conditions.append(Schedule.deleted_at.is_(None))
    elif filter == "past":
        conditions.append(Schedule.deleted_at.is_(None))
        conditions.append(
            or_(
                Schedule.status == "COMPLETED",
                and_(Schedule.status == "CONFIRMED", Schedule.confirmed_time <= datetime.now(timezone.utc))
            )
        )
    elif filter == "cancelled":
        conditions.append(
            or_(Schedule.status == "CANCELLED", Schedule.deleted_at.isnot(None))
        )
    else:
        pass  # "all": CONFIRMED + COMPLETED + CANCELLED + soft-deleted 전부 포함

    cancelled_last = case(
        (or_(
            Schedule.status == "CANCELLED",
            Schedule.deleted_at.isnot(None),
            and_(Schedule.status == "CONFIRMED", Schedule.confirmed_time <= datetime.now(timezone.utc))
        ), 1),
        else_=0
    )

    # N+1 방지: 목록에 필요한 Pet / Doctor / Category 를 한 번의 쿼리로 함께 로드한다.
    stmt = (
        select(Schedule, Pet, Doctor, CategoryMaster)
        .join(Guardian, Schedule.emrid == Guardian.emrid)
        .join(Pet, Guardian.petid == Pet.petid)
        .outerjoin(Doctor, Schedule.doctorid == Doctor.doctorid)
        .outerjoin(CategoryMaster, Guardian.category_id == CategoryMaster.id)
        .where(*conditions)
        .order_by(cancelled_last.asc(), Schedule.confirmed_time.asc())
        .offset(offset).limit(size + 1)
    )
    result = await db.execute(stmt)
    rows = list(result.all())

    has_next = len(rows) > size
    if has_next:
        rows = rows[:size]

    return rows, has_next


# 예약 취소 (soft cancel)
async def cancel_schedule(db: AsyncSession, schedule: Schedule):
    schedule.status = "CANCELLED"
    await db.commit()
    await db.refresh(schedule)
    return schedule


# 예약 변경
async def update_schedule_time(db: AsyncSession, schedule: Schedule, confirmed_time: str, duration_min: int):
    new_time = datetime.fromisoformat(confirmed_time)
    new_end_time = new_time + timedelta(minutes=duration_min)
    new_kst = to_kst(new_time) if new_time.tzinfo else new_time.replace(tzinfo=KST)
    new_date = new_kst.date()
    new_hhmm = new_kst.strftime("%H:%M")

    # 동시 예약 직렬화 (advisory lock) — 충돌 검사 전에 변경 대상 슬롯을 잠근다
    await _lock_slot(db, schedule.doctorid, new_time)

    # Schedule 테이블 기반 충돌 검증 (본인 예약 제외)
    conflict_result = await db.execute(
        select(Schedule).where(
            Schedule.scheduleid != schedule.scheduleid,
            Schedule.confirmed_time.isnot(None),
            Schedule.deleted_at.is_(None),
            Schedule.status != "CANCELLED",
            Schedule.doctorid == schedule.doctorid,
        )
    )
    for s in conflict_result.scalars().all():
        ct = to_kst(s.confirmed_time)
        if ct and ct.date() == new_date and ct.strftime("%H:%M") == new_hhmm:
            return None  # 충돌

    schedule.confirmed_time = new_time
    schedule.confirmed_end_time = new_end_time
    schedule.duration_min = duration_min
    await db.commit()
    await db.refresh(schedule)
    return schedule


# 수의사 운영 시간 슬롯 (30분 단위, 점심 12:00~13:00 제외)
_VET_TIME_SLOTS = [
    "09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
    "13:00", "13:30", "14:00", "14:30", "15:00", "15:30",
    "16:00", "16:30", "17:00",
]


class AvailableSlot:
    def __init__(self, start_time: str, end_time: str, doctorid: int, doctor_name: str = None):
        self.start_time = start_time
        self.end_time = end_time
        self.doctorid = doctorid
        self.doctor_name = doctor_name


# 빈 슬롯 조회 (Schedule 테이블 기반 동적 계산 — VetSchedule 의존 없음)
async def get_available_slots(db: AsyncSession, date: str, duration_min: int, doctorid: int = None):
    target_date = datetime.strptime(date, "%Y-%m-%d").date()
    now_kst = datetime.now(KST)

    # 주말·공휴일: 병원 휴무 — 빈 슬롯 없음
    if _is_clinic_closed(target_date):
        return []

    # 의사 확인
    if doctorid:
        doc_result = await db.execute(select(Doctor).where(Doctor.doctorid == doctorid))
        doctor = doc_result.scalar_one_or_none()
    else:
        doc_result = await db.execute(select(Doctor))
        doctor = doc_result.scalars().first()

    if not doctor:
        return []

    resolved_doctorid = doctor.doctorid

    # 해당 날짜에 이미 활성 예약된 시작 시간 수집
    sched_result = await db.execute(
        select(Schedule).where(
            Schedule.confirmed_time.isnot(None),
            Schedule.deleted_at.is_(None),
            Schedule.status != "CANCELLED",
            Schedule.doctorid == resolved_doctorid,
        )
    )
    booked = set()
    for s in sched_result.scalars().all():
        ct = to_kst(s.confirmed_time)
        if ct and ct.date() == target_date:
            end_dt = to_kst(s.confirmed_end_time) if s.confirmed_end_time else ct + timedelta(minutes=s.duration_min)
            current = ct
            while current < end_dt:
                booked.add(current.strftime("%H:%M"))
                current += timedelta(minutes=30)

    # 오늘이면 현재 시간 이전 슬롯 제외
    is_today = target_date == now_kst.date()
    current_hhmm = now_kst.strftime("%H:%M") if is_today else "00:00"

    avail = [
        t for t in _VET_TIME_SLOTS
        if t not in booked and (not is_today or t > current_hhmm)
    ]

    # duration_min 기반 연속 슬롯 계산
    needed = max(1, -(-duration_min // 30))
    available_starts = []

    for i in range(len(avail) - needed + 1):
        consecutive = True
        for j in range(1, needed):
            if _VET_TIME_SLOTS.index(avail[i + j]) != _VET_TIME_SLOTS.index(avail[i + j - 1]) + 1:
                consecutive = False
                break
        if consecutive:
            t = avail[i]
            h, m = map(int, t.split(":"))
            end_dt = datetime(2000, 1, 1, h, m) + timedelta(minutes=duration_min)
            available_starts.append(AvailableSlot(
                start_time=t,
                end_time=end_dt.strftime("%H:%M"),
                doctorid=resolved_doctorid,
                doctor_name=doctor.doctor_name,
            ))

    return available_starts


# 챗봇 예약 확정
async def confirm_schedule(db: AsyncSession, emrid: int, doctorid: int, confirmed_time: str, duration_min: int):
    new_time = datetime.fromisoformat(confirmed_time)
    new_end_time = new_time + timedelta(minutes=duration_min)

    # 동시 예약 직렬화 (advisory lock) — 충돌 검사 전에 슬롯을 잠근다
    await _lock_slot(db, doctorid, new_time)

    # 슬롯 충돌 체크 — INSERT 전 검증 (챗봇 추천 후 confirm 직전 선점 방지)
    conflict_result = await db.execute(
        select(Schedule).where(
            Schedule.confirmed_time == new_time,
            Schedule.doctorid == doctorid,
            Schedule.status != "CANCELLED",
            Schedule.deleted_at.is_(None),
        )
    )
    if conflict_result.scalar_one_or_none():
        return None  # 슬롯 충돌 — 호출부에서 409 처리

    schedule = Schedule(
        emrid=emrid,
        doctorid=doctorid,
        duration_min=duration_min,
        confirmed_time=new_time,
        confirmed_end_time=new_end_time,
        status="CONFIRMED"
    )
    db.add(schedule)

    await db.commit()
    await db.refresh(schedule)
    return schedule
