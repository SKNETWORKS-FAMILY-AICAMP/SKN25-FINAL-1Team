"""실DB 기반 예약/병원/수의사 맥락 평가 (코드 수정 없음 — 관찰/검증 전용).

DB-less memory_eval은 db=None이라 confirmed_time·hospital_name·doctor_name을 실제로 못 읽어
예약/병원/수의사 질문이 낮게 나온다. 이 스크립트는 '예약 확정(BOOKED)' 세션을 실제 DB에 구성해
같은 질문을 process_turn()로 태우고, DB 조회가 실제로 일어나는지/맥락을 기억하는지 검증한다.

구성: Hospital(메디포동물병원)·Doctor(김메디)·User·Pet·GuardianHospital(primary)
      ·Guardian(emrid)·Schedule(confirmed_time=+2일, status=예약확정) → phase=BOOKED.
각 케이스마다: route / events / pending / confirmed_time·hospital_name·doctor_name 조회 여부
      / 실제 reply / 메모리 1~5(LLM judge). 끝나면 만든 행을 모두 삭제.

Part B: 애매질문/감정/잡담(P4 후보)은 DB와 무관하므로 DB-less로 '최근 증상 맥락'을 깔고 관찰만 한다.

실행(도커):
  docker cp backend/scripts/run_realdb_context_eval.py docker-backend-1:/app/backend/scripts/
  docker exec -w /app/backend docker-backend-1 python scripts/run_realdb_context_eval.py --out /tmp/realdb.json
  docker cp docker-backend-1:/tmp/realdb.json backend/data/validation/
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))          # backend/
sys.path.insert(0, str(HERE.parent.parent))   # repo root (ai.*)

if os.environ.get("DEBUG", "").lower() in {"release", "prod", "production"}:
    os.environ["DEBUG"] = "false"

from sqlalchemy import delete, select  # noqa: E402

import ai.orchestrator.graph as graph_mod  # noqa: E402
from app.crud.chat import create_chat_session  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.chat_history import ChatHistory  # noqa: E402
from app.models.doctor import Doctor  # noqa: E402
from app.models.followup import Followup  # noqa: E402
from app.models.guardian import Guardian  # noqa: E402
from app.models.guardian_hospital import GuardianHospital  # noqa: E402
from app.models.hospital import Hospital  # noqa: E402
from app.models.pet import Pet  # noqa: E402
from app.models.schedule import Schedule  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.orchestrator_service import process_turn  # noqa: E402

# 식별용 distinctive 값 — reply에 이 값이 들어오면 'DB를 실제로 읽었다'고 본다.
HOSPITAL_NAME = "메디포동물병원"
HOSPITAL_ADDR = "서울특별시 강남구 테스트로 42"
HOSPITAL_TEL = "02-1234-5678"
DOCTOR_NAME = "김메디"

# 실DB 검증 케이스 — (발화, 분류태그)
REALDB_CASES = [
    ("내 예약 언제였죠?", "time"),
    ("내일 맞죠 예약?", "time"),
    ("지금은 어느 병원 예약이야?", "hospital"),
    ("예약한 병원 이름이 뭐야?", "hospital"),
    ("누구 의사지?", "vet"),
    ("그 의사 친절해?", "vet"),
    ("예약 시간 바꾸고 싶어요", "rebook"),
    ("더 빠른 시간 없어요?", "rebook"),
    ("예약 취소돼요?", "cancel_inquiry"),
    ("취소하면 다시 예약할 수 있죠?", "cancel_inquiry"),
]

# Part B — DB 무관 품질(P4 후보). 최근 증상 맥락을 깔고 관찰.
P4_CTX = [
    {"role": "user", "content": "어제 산책하다 다리를 살짝 절었어요."},
    {"role": "assistant", "content": "다리를 살짝 절었군요. 지금도 절뚝이거나 아파 보이는지 살펴봐 주세요."},
    {"role": "user", "content": "지금은 그냥 누워 있어요."},
    {"role": "assistant", "content": "지금은 누워 쉬고 있군요."},
]
P4_CASES = {
    "애매질문": ["이거 괜찮은 거죠?", "별일 아니겠죠?", "이 정도면 괜찮나요?", "그냥 둬도 돼요?"],
    "감정": ["너무 걱정돼", "신경 쓰여", "불안해", "별일 아니었으면 좋겠어"],
    "잡담경계": ["아니 근데 얘 왜 이래", "진짜 당황스럽네", "갑자기 이러니까 무섭다"],
}


# ── 라우팅 가로채기 ──
_routed = {"agent": None}
_orig_route = graph_mod.route


async def _traced_route(ctx):
    agent = await _orig_route(ctx)
    _routed["agent"] = agent
    return agent


async def _make_booked_subject(db, run_id: str, idx: int) -> dict:
    """BOOKED 세션 1건 구성. 반환: ids 묶음."""
    hospital = Hospital(
        hospital_name=HOSPITAL_NAME, hospital_address=HOSPITAL_ADDR, hospital_number=HOSPITAL_TEL,
        business_number=f"RT{run_id}{idx}", loginid=f"rt_hos_{run_id}_{idx}", password="x",
    )
    db.add(hospital)
    await db.commit()
    await db.refresh(hospital)

    doctor = Doctor(hospitalid=hospital.hospitalid, doctor_name=DOCTOR_NAME)
    db.add(doctor)
    await db.commit()
    await db.refresh(doctor)

    user = User(loginid=f"rt_{run_id}_{idx}", password="x", name="실DB평가", phone="010-0000-0000")
    db.add(user)
    await db.commit()
    await db.refresh(user)

    pet = Pet(userid=user.userid, petname="뽀미", species="dog", breed="Mixed",
              gender="male", weight_kg=4.5, is_neutered=True)
    db.add(pet)
    await db.commit()
    await db.refresh(pet)

    db.add(GuardianHospital(userid=user.userid, hospitalid=hospital.hospitalid, is_primary=True))
    guardian = Guardian(petid=pet.petid, category_id=1)
    db.add(guardian)
    await db.commit()
    await db.refresh(guardian)

    confirmed = datetime.now(timezone.utc) + timedelta(days=2)
    sched = Schedule(emrid=guardian.emrid, doctorid=doctor.doctorid, duration_min=30,
                     confirmed_time=confirmed, status="예약확정")
    db.add(sched)

    session = await create_chat_session(db, user.userid, pet.petid)
    session.emrid = guardian.emrid
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return {"hospitalid": hospital.hospitalid, "doctorid": doctor.doctorid,
            "userid": user.userid, "petid": pet.petid, "emrid": guardian.emrid,
            "session_id": session.id, "confirmed": confirmed}


async def _cleanup(db, ids: dict) -> None:
    await db.execute(delete(Followup).where(Followup.emrid == ids["emrid"]))
    await db.execute(delete(Schedule).where(Schedule.emrid == ids["emrid"]))
    await db.execute(delete(ChatHistory).where(ChatHistory.id == ids["session_id"]))
    await db.execute(delete(Guardian).where(Guardian.emrid == ids["emrid"]))
    await db.execute(delete(GuardianHospital).where(GuardianHospital.userid == ids["userid"]))
    await db.execute(delete(Pet).where(Pet.petid == ids["petid"]))
    await db.execute(delete(User).where(User.userid == ids["userid"]))
    await db.execute(delete(Doctor).where(Doctor.doctorid == ids["doctorid"]))
    await db.execute(delete(Hospital).where(Hospital.hospitalid == ids["hospitalid"]))
    await db.commit()


async def _judge_memory(utterance: str, reply: str, extra: str) -> dict:
    from ai.llm import call_llm_json
    prompt = f"""너는 반려동물 챗봇 평가자다. 보호자 입장에서 이 답변이 '내 예약을 기억한다'고 느껴지는지 1~5로 매겨라.
5=내 예약(시각/병원/담당의)을 구체적으로 알고 답함, 3=일반적, 1=내 예약을 모름/엉뚱.

[보호자 발화] {utterance}
[챗봇 답변] {reply}
[참고] {extra}

JSON만: {{"memory_score": 1~5, "feels_remembered": "yes|partial|no", "reason": "짧게"}}"""
    try:
        out = await call_llm_json(prompt)
        return {"memory_score": int(out.get("memory_score") or 3),
                "feels_remembered": out.get("feels_remembered") or "partial",
                "reason": out.get("reason") or ""}
    except Exception as e:  # noqa: BLE001
        return {"memory_score": 0, "feels_remembered": "judge_error", "reason": f"{type(e).__name__}: {e}"}


async def run_realdb(run_id: str) -> list[dict]:
    graph_mod.route = _traced_route
    results = []
    try:
        for idx, (utterance, tag) in enumerate(REALDB_CASES):
            async with AsyncSessionLocal() as db:
                ids = await _make_booked_subject(db, run_id, idx)
                _routed["agent"] = None
                events, reply, quick = [], "", []
                req = SimpleNamespace(content=utterance, image_url=None)
                try:
                    async for ev in process_turn(db, ids["session_id"], ids["userid"], req):
                        events.append(ev.get("type"))
                        if ev.get("type") == "result":
                            r = ev.get("result") or {}
                            reply = r.get("reply") or ""
                            quick = r.get("quick_replies") or []
                    sess = (await db.execute(
                        select(ChatHistory).where(ChatHistory.id == ids["session_id"]))).scalar_one()
                    pending = (sess.orch_state or {}).get("pending_confirmation_action", "")
                    err = None
                except Exception as e:  # noqa: BLE001
                    import traceback
                    pending, err = "", f"{type(e).__name__}: {e}"
                    print(traceback.format_exc()[-500:], file=sys.stderr)

                k = ids["confirmed"]
                from app.utils.timezone import to_kst
                kk = to_kst(k)
                time_str = f"{kk.month}월 {kk.day}일"
                ct_read = time_str in reply
                hn_read = HOSPITAL_NAME in reply or HOSPITAL_ADDR in reply or HOSPITAL_TEL in reply
                dn_read = DOCTOR_NAME in reply
                extra = f"실제 예약: {time_str} {kk.hour:02d}:{kk.minute:02d}, 병원={HOSPITAL_NAME}, 담당의={DOCTOR_NAME}"
                judge = await _judge_memory(utterance, reply, extra) if reply and not err else {
                    "memory_score": 0, "feels_remembered": "error", "reason": err or "no reply"}
                await _cleanup(db, ids)

                rec = {
                    "utterance": utterance, "tag": tag, "routed": _routed["agent"],
                    "events": [e for e in events if e and e != "result"],
                    "reply": reply, "quick_replies": quick, "pending": pending,
                    "confirmed_time_read": ct_read, "hospital_name_read": hn_read,
                    "doctor_name_read": dn_read, **judge, "error": err,
                }
                results.append(rec)
                flags = "".join([" T" if ct_read else "", " H" if hn_read else "", " D" if dn_read else ""])
                print(f"  [{tag:>13}] route={rec['routed']} pend={pending or '-'} mem={judge['memory_score']}"
                      f"{flags} :: {utterance[:22]} → {reply[:48]}", file=sys.stderr)
    finally:
        graph_mod.route = _orig_route
    return results


# ── Part B: DB-less 품질(P4 후보) ──
async def run_p4() -> dict:
    from ai.agents.followup_filter import repository as frepo
    from ai.orchestrator.contracts import Flow, Phase, SessionContext

    orig_save = frepo.save_followup
    cnt = {"n": 0}

    async def _stub(db, **kw):
        cnt["n"] += 1
        return SimpleNamespace(followupid=cnt["n"])

    frepo.save_followup = _stub
    graph_mod.route = _traced_route
    out = {}
    try:
        for group, utts in P4_CASES.items():
            rows = []
            for u in utts:
                _routed["agent"] = None
                ctx = SessionContext(
                    session_id=1, userid=1, petid=1, pet_info={"name": "뽀미", "species": "dog"},
                    hospitalid=1, emrid=1, scheduleid=1, user_message=u, attachments=[],
                    history=list(P4_CTX), phase=Phase.BOOKED, active_flow=Flow.IDLE, db=None)
                res = await graph_mod.run_turn(ctx)
                reply = res.reply or ""
                kind = (res.state_patch or {}).get("last_followup_reply_kind", "")
                clarify = any(p in reply for p in ("무엇을 도와드릴까요", "상태를 알려주시는 건", "관리 방법을 묻는"))
                rows.append({"utterance": u, "routed": _routed["agent"], "reply": reply,
                             "reply_kind": kind, "clarify_leak": clarify,
                             "events": [e.get("type") for e in (res.events or [])]})
                print(f"  [{group}] clarify={clarify} kind={kind} :: {u} → {reply[:50]}", file=sys.stderr)
            out[group] = rows
    finally:
        frepo.save_followup = orig_save
        graph_mod.route = _orig_route
    return out


async def main_async(args):
    print(f"OPENAI_API_KEY set? {'yes' if os.getenv('OPENAI_API_KEY') else 'NO'}\n", file=sys.stderr)
    run_id = str(int(time.time()))[-6:]
    print("▶ Part A: 실DB BOOKED 맥락", file=sys.stderr)
    realdb = await run_realdb(run_id)
    print("\n▶ Part B: DB-less 품질(P4 후보)", file=sys.stderr)
    p4 = await run_p4()

    # 집계
    by_tag = {}
    for r in realdb:
        by_tag.setdefault(r["tag"], []).append(r)
    summary = {}
    for tag, rs in by_tag.items():
        summary[tag] = {
            "n": len(rs),
            "avg_memory": round(sum(x["memory_score"] for x in rs) / len(rs), 2),
            "db_read": sum(1 for x in rs if x["confirmed_time_read"] or x["hospital_name_read"] or x["doctor_name_read"]),
        }
    p4_clarify = {g: sum(1 for x in rows if x["clarify_leak"]) for g, rows in p4.items()}
    report = {
        "meta": {"generated_at_unix": int(time.time()),
                 "seed": {"hospital": HOSPITAL_NAME, "doctor": DOCTOR_NAME}},
        "realdb_summary": summary, "realdb": realdb,
        "p4_clarify_counts": p4_clarify, "p4": p4,
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== 실DB 요약 ===", file=sys.stderr)
    for tag, s in summary.items():
        print(f"  {tag:>13}: 메모리 {s['avg_memory']}/5 · DB조회 {s['db_read']}/{s['n']}", file=sys.stderr)
    print(f"=== P4 clarify 누수: {p4_clarify} ===", file=sys.stderr)
    print(f"✓ {args.out}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE.parent / "data" / "validation" / "realdb_context_report.json"))
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
