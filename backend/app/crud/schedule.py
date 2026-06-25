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
from app.models.vet_schedule import HospitalClosedDate, HospitalWeeklySchedule, VetWeeklySchedule
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

    우선순위:
    1. 병원 특정일 휴진(hospital_closed_datesDB) → None
    2. 의사 주간 스케줄(vet_weekly_scheduleDB) → 의사 근무 시간
    3. 병원 주간 스케줄(hospital_weekly_scheduleDB) → 폴백
    4. 기본값: 평일만 영업
    """
    # 1. 의사 소속 병원 조회
    doctor_result = await db.execute(
        select(Doctor.hospitalid).where(Doctor.doctorid == doctorid)
    )
    hospitalid = doctor_result.scalar_one_or_none()

    # 2. 병원 특정일 휴진 확인
    if hospitalid is not None:
        closed_result = await db.execute(
            select(HospitalClosedDate).where(
                HospitalClosedDate.hospitalid == hospitalid,
                HospitalClosedDate.date == target_date,
            )
        )
        if closed_result.scalar_one_or_none() is not None:
            return None

    dow = target_date.weekday()

    # 3. 의사 주간 스케줄 확인
    vet_result = await db.execute(
        select(VetWeeklySchedule).where(
            VetWeeklySchedule.doctorid == doctorid,
            VetWeeklySchedule.day_of_week == dow,
        )
    )
    vet_record = vet_result.scalar_one_or_none()
    if vet_record is not None:
        if not vet_record.is_open:
            return None
        if vet_record.start_time and vet_record.end_time:
            return (
                vet_record.start_time.strftime("%H:%M"),
                vet_record.end_time.strftime("%H:%M"),
                vet_record.lunch_start.strftime("%H:%M") if vet_record.lunch_start else "12:00",
                vet_record.lunch_end.strftime("%H:%M") if vet_record.lunch_end else "13:00",
            )

    # 4. 병원 주간 스케줄 폴백
    if hospitalid is not None:
        hosp_result = await db.execute(
            select(HospitalWeeklySchedule).where(
                HospitalWeeklySchedule.hospitalid == hospitalid,
                HospitalWeeklySchedule.day_of_week == dow,
            )
        )
        hosp_record = hosp_result.scalar_one_or_none()
        if hosp_record is not None:
            if not hosp_record.is_open:
                return None
            if hosp_record.start_time and hosp_record.end_time:
                return (
                    hosp_record.start_time.strftime("%H:%M"),
                    hosp_record.end_time.strftime("%H:%M"),
                    hosp_record.lunch_start.strftime("%H:%M") if hosp_record.lunch_start else "12:00",
                    hosp_record.lunch_end.strftime("%H:%M") if hosp_record.lunch_end else "13:00",
                )

    # 5. 기본값: 평일만 영업
    if dow >= 5:
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

    # confirmed_time(timestamptz)을 '그 날(KST) 범위'로 SQL에서 미리 좁힌다.
    # 예전엔 의사의 전 기간 확정예약을 모두 로드해 Python에서 날짜로 거른 탓에,
    # 예약이력이 쌓일수록(의사당 수천~수만 행) 매 충돌검사가 선형으로 느려졌다.
    # ct.date() == target_date 와 정확히 같은 집합만 조회한다(겹침은 같은 날에서만 발생).
    day_start = datetime.combine(target_date, datetime.min.time(), tzinfo=KST)
    day_end = day_start + timedelta(days=1)

    stmt = (
        select(Schedule).where(
            Schedule.confirmed_time >= day_start,
            Schedule.confirmed_time < day_end,
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
async def get_schedules_by_userid(db: AsyncSession, userid: int, page: int, size: int, filter: str = "all", pet_id: int | None = None):
    offset = (page - 1) * size

    now = datetime.now(timezone.utc)

    conditions = [Pet.userid == userid]

    # 반려동물별 필터: 보호자가 특정 반려동물의 예약만 보고 싶을 때
    if pet_id is not None:
        conditions.append(Pet.petid == pet_id)

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
        # "all": 보호자 예약내역에 표시되는 상태만 페이지네이션한다.
        conditions.append(
            or_(
                Schedule.status.in_(["CONFIRMED", "COMPLETED", "CANCELLED"]),
                Schedule.deleted_at.isnot(None),
            )
        )

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


# 단일 원장의 해당 날짜 빈 슬롯 계산 (휴진이면 빈 리스트)
async def _slots_for_doctor(db: AsyncSession, doctor, target_date, duration_min: int, now_kst):
    hours = await _get_hours_for_date(db, doctor.doctorid, target_date)
    if hours is None:
        return []

    op_start, op_end, lunch_start, lunch_end = hours
    vet_time_slots = _generate_time_slots(op_start, op_end, lunch_start, lunch_end)

    # 해당 날짜에 이미 활성 예약된 시작 시간 수집
    sched_result = await db.execute(
        select(Schedule).where(
            Schedule.confirmed_time.isnot(None),
            Schedule.deleted_at.is_(None),
            Schedule.status != "CANCELLED",
            Schedule.doctorid == doctor.doctorid,
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
    starts = []
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
            starts.append(AvailableSlot(
                start_time=t,
                end_time=end_dt.strftime("%H:%M"),
                doctorid=doctor.doctorid,
                doctor_name=doctor.doctor_name,
            ))
    return starts


# 빈 슬롯 조회 (vet_scheduleDB 운영시간 기반 동적 계산)
# doctorid 지정 시 그 원장만, hospitalid 지정 시 그 병원의 전 원장 슬롯을 합쳐 반환.
async def get_available_slots(
    db: AsyncSession,
    date: str,
    duration_min: int,
    doctorid: int = None,
    hospitalid: int = None,
):
    target_date = datetime.strptime(date, "%Y-%m-%d").date()
    now_kst = datetime.now(KST)

    # 법정공휴일: 무조건 휴무
    if _is_legal_holiday(target_date):
        return [], "해당 날짜는 휴일(법정 공휴일)로 진료가 없습니다."

    # 대상 원장 집합: doctorid 지정 > hospitalid 전체 > (호환) 첫 원장
    # 비활성 원장(is_active=False)은 신규 예약 대상에서 제외(보호자 UI 숨김 + API 방어).
    if doctorid:
        doc_result = await db.execute(
            select(Doctor).where(Doctor.doctorid == doctorid, Doctor.is_active == True)  # noqa: E712
        )
        doctor = doc_result.scalar_one_or_none()
        doctors = [doctor] if doctor else []
    elif hospitalid:
        doc_result = await db.execute(
            select(Doctor)
            .where(Doctor.hospitalid == hospitalid, Doctor.is_active == True)  # noqa: E712
            .order_by(Doctor.doctorid)
        )
        doctors = list(doc_result.scalars().all())
    else:
        doc_result = await db.execute(
            select(Doctor).where(Doctor.is_active == True)  # noqa: E712
        )
        first = doc_result.scalars().first()
        doctors = [first] if first else []

    if not doctors:
        return [], "예약 가능한 수의사가 없습니다."

    all_starts = []
    for doctor in doctors:
        all_starts.extend(await _slots_for_doctor(db, doctor, target_date, duration_min, now_kst))

    if not all_starts:
        return [], "예약 가능한 시간이 모두 마감되었습니다."

    all_starts.sort(key=lambda s: (s.start_time, s.doctorid))
    return all_starts, ""


# 응급도 기반 '가장 빠른 빈 슬롯' 탐색 (MCP 예약 오케스트레이션의 핵심)
# 응급도 3버킷 → 탐색 시작 오프셋(영업일). 급할수록 이른 날부터 스캔하여
# 응급 환자에게 가장 빠른 시간을 우선 추천한다. 일반은 뒤로 미뤄 이른 슬롯을 비워둠
#   응급(RED, num1)        → 오늘부터
#   준응급(ORANGE, num2)   → +1 영업일부터
#   일반(YELLOW·GREEN, num3~) → +2 영업일부터
_URGENCY_START_OFFSET_DAYS = {"emergency": 0, "semi": 1, "normal": 2}


def _urgency_bucket(urgency_level_num: int) -> str:
    """urgency_level_num → 3버킷. RED(1)=응급 / ORANGE(2)=준응급 / YELLOW(3)·GREEN(4)=일반. (표시 라벨과 동일)"""
    if urgency_level_num <= 1:
        return "emergency"   # 응급
    if urgency_level_num == 2:
        return "semi"        # 준응급(ORANGE)
    return "normal"          # 일반(YELLOW·GREEN)


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


# ── 응급도 기반 슬롯 추천 (3모드, 결정론) ─────────────────────────────────────
# triage 응급도로 추천 분배를 정한다. LLM 없이 vet_scheduleDB 운영시간만으로 계산.
# find_earliest_slots._urgency_bucket과 동일한 3버킷 기준으로 통일.
#   응급(RED, num1)        → 가장 빠른 운영일 2개 + 다음 운영일 1개
#   준응급(ORANGE, num2)   → 가장 빠른 운영일 1개 + 다음 운영일 2개
#   일반(YELLOW·GREEN)     → 운영일 3일에 1개씩(오늘·내일·모레), 휴진/마감이면 다음 운영일로 밀기.

# 버킷별 운영일 quota (fill-forward)
_BUCKET_DAY_QUOTAS = {
    "emergency": [2, 1],
    "semi": [1, 2],
    "normal": [1, 1, 1],
}


def _recommend_bucket(urgency) -> str:
    """triage urgency(라벨 'RED'/'ORANGE'/'YELLOW'/'GREEN' 또는 숫자 1~5) → 3버킷.

    find_earliest_slots._urgency_bucket과 동일 기준: RED(1)=emergency / ORANGE(2)=semi / 그외=normal.
    """
    if isinstance(urgency, (int, float)):
        return _urgency_bucket(int(urgency))
    label = str(urgency).strip().upper()
    if label == "RED":
        return "emergency"
    if label == "ORANGE":
        return "semi"
    return "normal"


# AvailableSlot → 응답용 dict
def _slot_to_dict(d, slot: "AvailableSlot") -> dict:
    return {
        "date": d.isoformat(),
        "start_time": slot.start_time,
        "end_time": slot.end_time,
        "doctorid": slot.doctorid,
        "doctor_name": slot.doctor_name,
    }


# 슬롯 목록에서 count개를, 의사가 골고루 섞이도록 고른다 (recommended 모드 분산용).
# used: 누적 선택 횟수(의사별). 호출 간 공유하면 날짜를 넘나들며 한 의사 쏠림을 막는다.
# slots는 (start_time, doctorid) 오름차순 전제 → 같은 사용횟수면 가장 이른 슬롯이 잡힌다.
def _pick_diverse(slots: list, count: int, used: dict[int, int]) -> list:
    chosen: list = []
    pool = list(slots)
    while len(chosen) < count and pool:
        min_used = min(used.get(s.doctorid, 0) for s in pool)
        i = next(idx for idx, s in enumerate(pool) if used.get(s.doctorid, 0) == min_used)
        s = pool.pop(i)
        used[s.doctorid] = used.get(s.doctorid, 0) + 1
        chosen.append(s)
    chosen.sort(key=lambda s: (s.start_time, s.doctorid))  # 표시용 시간순 복원
    return chosen


# 운영일마다 정해진 개수(quota)씩 가장 빠른 슬롯 수집 (휴진은 건너뜀 = fill-forward)
async def _collect_by_day_quota(
    db: AsyncSession,
    day_quotas: list[int],
    duration_min: int,
    hospitalid: int | None,
    doctorid: int | None,
    max_scan_days: int = 21,
    diversify: bool = False,
) -> list[dict]:
    """day_quotas=[2,1] → '첫 운영일 2개, 다음 운영일 1개'.

    휴진/마감으로 빈 날은 quota를 소비하지 않고 다음 운영일로 넘어간다(fill-forward).
    diversify=True면 한 의사 쏠림을 줄여 여러 의사를 골고루 추천한다(병원 전체 조회 시).
    """
    today = datetime.now(KST).date()
    collected: list[dict] = []
    used: dict[int, int] = {}  # 의사별 누적 선택 횟수 (날짜 넘나들며 공유)
    quota_idx = 0
    for day_index in range(max_scan_days):
        if quota_idx >= len(day_quotas):
            break
        d = today + timedelta(days=day_index)
        slots, _ = await get_available_slots(db, d.isoformat(), duration_min, doctorid, hospitalid)
        if not slots:
            continue  # 휴진/마감 → 다음 운영일
        q = day_quotas[quota_idx]
        picked = _pick_diverse(slots, q, used) if diversify else slots[:q]
        for s in picked:
            collected.append(_slot_to_dict(d, s))
        quota_idx += 1
    return collected


# 응급도 기반 3모드 슬롯 추천 (추천시간 / 가장 가까운 시간 / 수의사별)
async def recommend_slots(
    db: AsyncSession,
    *,
    urgency,
    duration_min: int,
    hospitalid: int | None = None,
    doctorid: int | None = None,
) -> dict:
    """3모드를 한 번에 계산 — 프론트가 칩 전환 시 재요청 없이 쓰도록.

    반환: {bucket, recommended[], earliest[], by_doctor{docid: {doctor_name, slots[]}}}
    """
    bucket = _recommend_bucket(urgency)
    # 응급=오늘2+내일1 / 준응급=오늘1+내일2 / 일반=오늘1·내일1·모레1
    rec_quota = _BUCKET_DAY_QUOTAS.get(bucket, _BUCKET_DAY_QUOTAS["normal"])

    # 추천시간: 의사 골고루(diversify). 특정 원장 지정(doctorid) 시엔 의사 1명뿐이라 분산 무의미.
    recommended = await _collect_by_day_quota(
        db, rec_quota, duration_min, hospitalid, doctorid, diversify=True
    )
    # 가장 가까운 시간: 의사 무관 '순수 가장 이른' 순서 유지(분산 안 함)
    earliest = await _collect_by_day_quota(db, [3], duration_min, hospitalid, doctorid)

    by_doctor: dict[int, dict] = {}
    # 수의사별: 병원 전체 조회일 때만 원장 각각에 추천 분배 적용
    if hospitalid and not doctorid:
        docs = (await db.execute(
            select(Doctor)
            .where(Doctor.hospitalid == hospitalid, Doctor.is_active == True)  # noqa: E712
            .order_by(Doctor.doctorid)
        )).scalars().all()
        for doc in docs:
            slots = await _collect_by_day_quota(db, rec_quota, duration_min, None, doc.doctorid)
            by_doctor[doc.doctorid] = {"doctor_name": doc.doctor_name, "slots": slots}

    return {"bucket": bucket, "recommended": recommended, "earliest": earliest, "by_doctor": by_doctor}


# 챗봇 예약 확정
async def confirm_schedule(db: AsyncSession, emrid: int, doctorid: int, confirmed_time: str, duration_min: int):
    new_time = datetime.fromisoformat(confirmed_time)
    new_end_time = new_time + timedelta(minutes=duration_min)

    doctor_result = await db.execute(
        select(Doctor).where(Doctor.doctorid == doctorid, Doctor.is_active == True)  # noqa: E712
    )
    if doctor_result.scalar_one_or_none() is None:
        return None

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
