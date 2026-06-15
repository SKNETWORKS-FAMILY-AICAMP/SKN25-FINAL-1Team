from sqlalchemy import select, or_, and_, case
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime, timedelta, timezone, date as _date_type
from app.models.guardian import Guardian
from app.models.hospital import Hospital
from app.models.schedule import Schedule
from app.models.master import CategoryMaster
from app.models.pet import Pet
from app.models.doctor import Doctor
from app.models.vet_schedule import VetSchedule
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


def _is_legal_holiday(d: _date_type) -> bool:
    """법정공휴일이면 True. (주말은 주간 스케줄 설정으로 제어)"""
    return d.isoformat() in _HOLIDAYS


async def _get_hours_for_date(
    db: AsyncSession, doctorid: int, target_date: _date_type
) -> tuple[str, str, str, str] | None:
    """(op_start, op_end, lunch_start, lunch_end) 반환. 휴진이면 None.

    우선순위: 특정일 오버라이드 > 주간 템플릿 > 기본값(평일만 영업)
    """
    # 1. 특정일 오버라이드 확인
    date_result = await db.execute(
        select(VetSchedule).where(
            VetSchedule.doctorid == doctorid,
            VetSchedule.date == target_date,
            VetSchedule.day_of_week.is_(None),
        )
    )
    date_record = date_result.scalar_one_or_none()
    if date_record is not None:
        if not date_record.is_open:
            return None
        if date_record.start_time and date_record.end_time:
            return (
                date_record.start_time.strftime("%H:%M"),
                date_record.end_time.strftime("%H:%M"),
                date_record.lunch_start.strftime("%H:%M") if date_record.lunch_start else "12:00",
                date_record.lunch_end.strftime("%H:%M") if date_record.lunch_end else "13:00",
            )

    # 2. 주간 템플릿 확인 (0=월 ... 6=일)
    dow = target_date.weekday()
    dow_result = await db.execute(
        select(VetSchedule).where(
            VetSchedule.doctorid == doctorid,
            VetSchedule.day_of_week == dow,
        )
    )
    dow_record = dow_result.scalar_one_or_none()
    if dow_record is not None:
        if not dow_record.is_open:
            return None
        if dow_record.start_time and dow_record.end_time:
            return (
                dow_record.start_time.strftime("%H:%M"),
                dow_record.end_time.strftime("%H:%M"),
                dow_record.lunch_start.strftime("%H:%M") if dow_record.lunch_start else "12:00",
                dow_record.lunch_end.strftime("%H:%M") if dow_record.lunch_end else "13:00",
            )

    # 3. 기본값: 평일만 영업
    if target_date.weekday() >= 5:
        return None
    return ("09:00", "18:00", "12:00", "13:00")



async def has_time_overlap(
    db: AsyncSession,
    doctorid: int,
    new_start: datetime,
    new_end: datetime,
    exclude_schedule_id: int | None = None,
) -> bool:
    # 새 예약 구간 [new_start, new_end)이 같은 의사의 기존 활성 예약과 겹치는지 검사
    ns = to_kst(new_start)
    ne = to_kst(new_end)
    target_date = ns.date()

    stmt = (
        select(Schedule).where(
            Schedule.confirmed_time.isnot(None),
            Schedule.deleted_at.is_(None),
            Schedule.status != "CANCELLED",
            Schedule.doctorid == doctorid,
        )
    )
    if exclude_schedule_id is not None:
        stmt = stmt.where(Schedule.scheduleid != exclude_schedule_id)

    result = await db.execute(stmt)
    for s in result.scalars().all():
        ct = to_kst(s.confirmed_time)
        if not ct or ct.date() != target_date:
            continue
        et = to_kst(s.confirmed_end_time) if s.confirmed_end_time else ct + timedelta(minutes=s.duration_min or 30)
        if ns < et and ne > ct:
            return True
    return False


# 정기검진 예약 생성
async def create_checkup_schedule(db: AsyncSession, pet_id: int, date: str, time: str, memo: str, doctorid: int, category_code: int = 1):

    result = await db.execute(
        select(CategoryMaster).where(CategoryMaster.code == category_code)
    )
    category = result.scalar_one_or_none()
    if not category:
        result = await db.execute(select(CategoryMaster))
        category = result.scalars().first()

    # 예약 시간 설정 — 입력은 KST 기준
    kst_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M").replace(tzinfo=KST)

    # 슬롯 충돌 체크 — Guardian 생성 전에 먼저 확인
    # 구간 겹침으로 판정: 기존 예약의 소요시간(50분 등)을 정확히 반영해 이중 예약 방지
    if await has_time_overlap(db, doctorid, kst_dt, kst_dt + timedelta(minutes=30)):
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
    # 동시성 race로 사전 검사를 통과한 겹침은 DB의 no_overlap_schedule 제약이 막음
    # 500 대신 깔끔한 충돌(None)로 변환해 호출부에서 409 처리.
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return None, None
    await db.refresh(schedule)
    return schedule, guardian


# 예약 상세 조회
async def get_schedule_by_id(db: AsyncSession, schedule_id: int):
    result = await db.execute(
        select(Schedule).where(Schedule.scheduleid == schedule_id)
    )
    return result.scalar_one_or_none()


# emrid 소유자(보호자 userid) 조회 
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

    now = datetime.now(timezone.utc)

    conditions = [Pet.userid == userid]

    if filter == "upcoming":
        conditions.append(Schedule.status == "CONFIRMED")
        conditions.append(Schedule.confirmed_time > now)
        conditions.append(Schedule.deleted_at.is_(None))
    elif filter == "past":
        conditions.append(Schedule.deleted_at.is_(None))
        conditions.append(
            or_(
                Schedule.status == "COMPLETED",
                and_(Schedule.status == "CONFIRMED", Schedule.confirmed_time <= now)
            )
        )
    elif filter == "cancelled":
        conditions.append(
            or_(Schedule.status == "CANCELLED", Schedule.deleted_at.isnot(None))
        )
    else:
        pass  # "all": CONFIRMED + COMPLETED + CANCELLED + soft-deleted 전부 포함

    # 탭별 정렬 방향: 미래(다가오는 예약)는 임박순(ASC), 과거(지난 상담)는 최신순(DESC)
    if filter == "upcoming":
        # 가장 가까운 예약이 맨 위
        order_clause = [Schedule.confirmed_time.asc()]
    elif filter in ("past", "cancelled"):
        # 가장 최근에 한 상담/취소가 맨 위
        order_clause = [Schedule.confirmed_time.desc()]
    else:
        # "all": 다가오는 예약(임박순) 묶음을 위로, 지난/완료/취소(최신순) 묶음을 아래로
        past_cond = or_(
            Schedule.status == "COMPLETED",
            Schedule.status == "CANCELLED",
            Schedule.deleted_at.isnot(None),
            and_(Schedule.status == "CONFIRMED", Schedule.confirmed_time <= now),
        )
        is_past = case((past_cond, 1), else_=0)
        upcoming_sort = case((past_cond, None), else_=Schedule.confirmed_time)  # 미래 묶음만 값
        past_sort = case((past_cond, Schedule.confirmed_time))                  # 과거 묶음만 값
        order_clause = [is_past.asc(), upcoming_sort.asc(), past_sort.desc()]

    # N+1 방지: 목록에 필요한 Pet / Doctor / Hospital / Category 를 한 번의 쿼리로 함께 로드
    stmt = (
        select(Schedule, Pet, Doctor, CategoryMaster, Hospital)
        .join(Guardian, Schedule.emrid == Guardian.emrid)
        .join(Pet, Guardian.petid == Pet.petid)
        .outerjoin(Doctor, Schedule.doctorid == Doctor.doctorid)
        .outerjoin(Hospital, Doctor.hospitalid == Hospital.hospitalid)
        .outerjoin(CategoryMaster, Guardian.category_id == CategoryMaster.id)
        .where(*conditions)
        .order_by(*order_clause)
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

    # Schedule 테이블 기반 구간 겹침 충돌 검증 (본인 예약 제외)
    if await has_time_overlap(
        db, schedule.doctorid, new_time, new_end_time,
        exclude_schedule_id=schedule.scheduleid,
    ):
        return None  # 충돌

    schedule.confirmed_time = new_time
    schedule.confirmed_end_time = new_end_time
    schedule.duration_min = duration_min
    # 동시성 race 대비: DB no_overlap_schedule 제약 위반을 충돌(None)로 변환
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return None
    await db.refresh(schedule)
    return schedule


def _to_minutes(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m


def _generate_time_slots(
    start: str,
    end: str,
    lunch_start: str,
    lunch_end: str,
    interval_min: int = 30,
) -> list[str]:
    """운영시간 내 예약 가능 슬롯 목록 생성.

    마감 1시간 전이 마지막 시작 슬롯 (예: 19:00 마감 → 18:00 마지막).
    점심시간과 겹치는 슬롯은 제외.
    """
    start_min = _to_minutes(start)
    end_min = _to_minutes(end)
    lunch_s = _to_minutes(lunch_start)
    lunch_e = _to_minutes(lunch_end)
    last_start = end_min - 60  # 마감 1시간 전까지만 예약 가능

    slots = []
    cur = start_min
    while cur <= last_start:
        slot_end = cur + interval_min
        # 슬롯이 점심시간과 겹치면 제외
        if not (cur < lunch_e and slot_end > lunch_s):
            slots.append(f"{cur // 60:02d}:{cur % 60:02d}")
        cur += interval_min
    return slots


class AvailableSlot:
    def __init__(self, start_time: str, end_time: str, doctorid: int, doctor_name: str = None):
        self.start_time = start_time
        self.end_time = end_time
        self.doctorid = doctorid
        self.doctor_name = doctor_name


# 빈 슬롯 조회 (vet_scheduleDB 운영시간 기반 동적 계산)
async def get_available_slots(db: AsyncSession, date: str, duration_min: int, doctorid: int = None):
    target_date = datetime.strptime(date, "%Y-%m-%d").date()
    now_kst = datetime.now(KST)

    # 법정공휴일: 무조건 휴무
    if _is_legal_holiday(target_date):
        return [], "해당 날짜는 휴일(법정 공휴일)로 진료가 없습니다."

    # 의사 확인
    if doctorid:
        doc_result = await db.execute(select(Doctor).where(Doctor.doctorid == doctorid))
        doctor = doc_result.scalar_one_or_none()
    else:
        doc_result = await db.execute(select(Doctor))
        doctor = doc_result.scalars().first()

    if not doctor:
        return [], "예약 가능한 수의사가 없습니다."

    resolved_doctorid = doctor.doctorid

    # 운영시간 조회 (특정일 오버라이드 > 주간 템플릿 > 기본값)
    hours = await _get_hours_for_date(db, resolved_doctorid, target_date)
    if hours is None:
        return [], "해당 날짜는 병원 휴무일(휴진)입니다."

    op_start, op_end, lunch_start, lunch_end = hours

    vet_time_slots = _generate_time_slots(op_start, op_end, lunch_start, lunch_end)

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
        t for t in vet_time_slots
        if t not in booked and (not is_today or t > current_hhmm)
    ]

    # duration_min 기반 연속 슬롯 계산 (30분 간격 기준)
    needed = max(1, -(-duration_min // 30))
    available_starts = []

    for i in range(len(avail) - needed + 1):
        consecutive = True
        for j in range(1, needed):
            if _to_minutes(avail[i + j]) != _to_minutes(avail[i + j - 1]) + 30:
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

    if not available_starts:
        if is_today and current_hhmm >= op_end:
            return [], "금일 진료가 마감되었습니다."
        return [], "예약 가능한 시간이 모두 마감되었습니다."

    return available_starts, ""


# 응급도 기반 '가장 빠른 빈 슬롯' 탐색 (MCP 예약 오케스트레이션의 핵심)
# 응급도 3버킷 → 탐색 시작 오프셋(영업일). 급할수록 이른 날부터 스캔하여
# 응급 환자에게 가장 빠른 시간을 우선 추천한다. 일반은 뒤로 미뤄 이른 슬롯을 비워둠
#   응급(RED, num1)        → 오늘부터
#   준응급(num2~3)         → +1 영업일부터
#   일반(num4~5)           → +2 영업일부터
_URGENCY_START_OFFSET_DAYS = {"emergency": 0, "semi": 1, "normal": 2}


def _urgency_bucket(urgency_level_num: int) -> str:
    """urgency_level_num(1~5) → 3버킷. (표시 라벨 3버킷과 동일 기준)"""
    if urgency_level_num <= 1:
        return "emergency"   # 응급
    if urgency_level_num <= 3:
        return "semi"        # 준응급
    return "normal"          # 일반


async def find_earliest_slots(
    db: AsyncSession,
    *,
    urgency_level_num: int,
    duration_min: int,
    limit: int = 3,
    doctorid: int | None = None,
    max_scan_days: int = 21,
) -> list[dict]:
    """응급도에 따라 시작일을 정하고, 오늘 기준 '가장 이른' 빈 슬롯을 limit개 모은다.

    급할수록(응급) 이른 날부터 스캔 → 응급에 가장 빠른 시간을 우선한다.
    read-only(조회만) — 실제 예약 확정은 confirm_schedule(락·overlap 제약)이 따로 처리한다.
    각 슬롯은 dict: {date, start_time, end_time, doctorid, doctor_name}. 날짜·시간 오름차순.
    """
    try:
        num = int(urgency_level_num)
    except (TypeError, ValueError):
        num = 3
    start_offset = _URGENCY_START_OFFSET_DAYS[_urgency_bucket(num)]
    today = datetime.now(KST).date()

    collected: list[dict] = []
    for day_index in range(start_offset, start_offset + max_scan_days):
        if len(collected) >= limit:
            break
        d = today + timedelta(days=day_index)
        # 휴무(공휴일·주말·휴진)는 get_available_slots 가 내부에서 빈 리스트로 처리하므로
        # 별도 사전 체크 없이 호출한다(닫힌 날은 자연히 건너뛰어짐).
        slots, _ = await get_available_slots(db, d.isoformat(), duration_min, doctorid)
        for s in slots:
            collected.append({
                "date": d.isoformat(),
                "start_time": s.start_time,
                "end_time": s.end_time,
                "doctorid": s.doctorid,
                "doctor_name": s.doctor_name,
            })
            if len(collected) >= limit:
                break
    return collected


# 챗봇 예약 확정
async def confirm_schedule(db: AsyncSession, emrid: int, doctorid: int, confirmed_time: str, duration_min: int):
    new_time = datetime.fromisoformat(confirmed_time)
    new_end_time = new_time + timedelta(minutes=duration_min)

    # 슬롯 충돌 체크 — INSERT 전 구간 겹침 검증 (챗봇 추천 후 confirm 직전 선점 방지)
    # 소요시간(50분 등)을 반영한 구간 겹침으로 판정해 30분 격자에 어긋난 이중 예약 방지
    if await has_time_overlap(db, doctorid, new_time, new_end_time):
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

    # 동시성 race 대비: DB no_overlap_schedule 제약 위반을 충돌(None)로 변환
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return None
    await db.refresh(schedule)
    return schedule
