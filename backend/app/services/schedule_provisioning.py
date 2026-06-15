from sqlalchemy.ext.asyncio import AsyncSession


def provision_doctor_weekly_schedule(
    db: AsyncSession,
    doctorid: int,
    hours: dict | None,
) -> None:
    """Future hook for onboarding hours -> schedule storage.

    Onboarding keeps the submitted hours in clinic_signup_requestDB.hours and
    doctors[].hours. The actual schedule write is intentionally disabled in
    this PR because vet scheduling is being split into hospital defaults,
    doctor overrides, and date exceptions by another task.
    """
    _ = (db, doctorid, hours)
    return None
