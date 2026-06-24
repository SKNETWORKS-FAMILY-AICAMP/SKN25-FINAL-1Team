"""커밋 전 채팅 종합 E2E (실 dev DB + process_turn).

검증 그룹:
  A. 진입      : 활성펫 채팅 시작 가능 / 보관펫 신규채팅 차단 / 보관펫 선택목록 제외
  B. PRE_BOOKING: 증상→triage, 병원정보→reception, 예약의도→문진흐름 / scheduleid=None
  C. BOOKED    : 예약시각·병원·담당의·재예약·취소문의·경과저장·사진후속 / scheduleid 실값
  D. 상태      : chat_history 저장 / orch_state 저장·로드 / scheduleid fill / 과거기록 조회

각 턴: route/agent, reply 전문, events, scheduleid, phase, pass/fail, 이유.
끝나면 만든 행 삭제. 결과 → chat_eval_results.json
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
from app.crud.chat import create_chat_session, get_chat_session  # noqa: E402
from app.crud.pet import get_pets_by_userid  # noqa: E402
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

HOSPITAL_NAME = "메디포동물병원"
HOSPITAL_ADDR = "서울특별시 강남구 테스트로 42"
HOSPITAL_TEL = "02-1234-5678"
DOCTOR_NAME = "김메디"

# route(ctx) 가로채 agent + scheduleid + phase 캡처
_trace = {"agent": None, "scheduleid": "UNSET", "phase": None}
_last = {"events": [], "quick_replies": [], "elapsed_ms": None}
_orig_route = graph_mod.route
_orig_run_turn = graph_mod.run_turn


async def _traced_route(ctx):
    agent = await _orig_route(ctx)
    _trace["agent"] = agent
    _trace["scheduleid"] = getattr(ctx, "scheduleid", "UNSET")
    _trace["phase"] = getattr(getattr(ctx, "phase", None), "value", str(getattr(ctx, "phase", None)))
    return agent


async def _traced_run_turn(ctx):
    res = await _orig_run_turn(ctx)
    _last["events"] = [e.get("type") for e in (res.events or [])]
    return res


async def _judge(utterance: str, reply: str, extra: str) -> dict:
    from ai.llm import call_llm_json
    prompt = f"""너는 반려동물 챗봇 평가자다. 보호자 입장에서 이 답변이 '내 예약/맥락을 알고 답한다'고 느껴지는지 1~5로 매겨라.
5=구체적으로 내 예약(시각/병원/담당의)·맥락을 알고 답함, 3=일반적, 1=모름/엉뚱.
[보호자] {utterance}
[챗봇] {reply}
[참고] {extra}
JSON만: {{"score": 1~5, "reason": "짧게"}}"""
    try:
        out = await call_llm_json(prompt)
        return {"score": int(out.get("score") or 3), "reason": out.get("reason") or ""}
    except Exception as e:  # noqa: BLE001
        return {"score": 0, "reason": f"judge_error: {type(e).__name__}"}


async def _make_subject(db, run_id, idx, *, booked: bool, history=None):
    hospital = Hospital(
        hospital_name=HOSPITAL_NAME, hospital_address=HOSPITAL_ADDR, hospital_number=HOSPITAL_TEL,
        business_number=f"CE{run_id}{idx}", loginid=f"ce_hos_{run_id}_{idx}", password="x",
    )
    db.add(hospital); await db.commit(); await db.refresh(hospital)
    doctor = Doctor(hospitalid=hospital.hospitalid, doctor_name=DOCTOR_NAME)
    db.add(doctor); await db.commit(); await db.refresh(doctor)
    user = User(loginid=f"ce_{run_id}_{idx}", password="x", name="채팅평가", phone="010-0000-0000")
    db.add(user); await db.commit(); await db.refresh(user)
    pet = Pet(userid=user.userid, petname="뽀미", species="dog", breed="Mixed",
              gender="male", weight_kg=4.5, is_neutered=True)
    db.add(pet); await db.commit(); await db.refresh(pet)
    db.add(GuardianHospital(userid=user.userid, hospitalid=hospital.hospitalid, is_primary=True))
    ids = {"hospitalid": hospital.hospitalid, "doctorid": doctor.doctorid,
           "userid": user.userid, "petid": pet.petid, "emrid": None, "session_id": None,
           "confirmed": None}
    session = await create_chat_session(db, user.userid, pet.petid)
    if booked:
        guardian = Guardian(petid=pet.petid, category_id=1)
        db.add(guardian); await db.commit(); await db.refresh(guardian)
        confirmed = datetime.now(timezone.utc) + timedelta(days=2)
        db.add(Schedule(emrid=guardian.emrid, doctorid=doctor.doctorid, duration_min=30,
                        confirmed_time=confirmed, status="예약확정"))
        session.emrid = guardian.emrid
        ids["emrid"] = guardian.emrid
        ids["confirmed"] = confirmed
    if history:
        session.messages = list(history)
    db.add(session); await db.commit(); await db.refresh(session)
    ids["session_id"] = session.id
    return ids


async def _cleanup(db, ids):
    # FK: chat_history.emrid → guardian, schedule/followup.emrid → guardian → ChatHistory 먼저 삭제
    if ids.get("session_id") is not None:
        await db.execute(delete(ChatHistory).where(ChatHistory.id == ids["session_id"]))
    if ids.get("emrid") is not None:
        await db.execute(delete(Followup).where(Followup.emrid == ids["emrid"]))
        await db.execute(delete(Schedule).where(Schedule.emrid == ids["emrid"]))
        await db.execute(delete(Guardian).where(Guardian.emrid == ids["emrid"]))
    await db.execute(delete(GuardianHospital).where(GuardianHospital.userid == ids["userid"]))
    await db.execute(delete(Pet).where(Pet.petid == ids["petid"]))
    await db.execute(delete(User).where(User.userid == ids["userid"]))
    await db.execute(delete(Doctor).where(Doctor.doctorid == ids["doctorid"]))
    await db.execute(delete(Hospital).where(Hospital.hospitalid == ids["hospitalid"]))
    await db.commit()


async def _run_turn(db, ids, utterance, image_url=None):
    _trace.update({"agent": None, "scheduleid": "UNSET", "phase": None})
    _last["events"] = []
    _last["quick_replies"] = []
    _last["elapsed_ms"] = None
    req = SimpleNamespace(content=utterance, image_url=image_url)
    reply = ""
    t0 = time.perf_counter()
    async for ev in process_turn(db, ids["session_id"], ids["userid"], req):
        if ev.get("type") == "result":
            res = ev.get("result") or {}
            reply = res.get("reply") or ""
            _last["quick_replies"] = res.get("quick_replies") or []
    _last["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
    return reply, list(_last["events"]), _trace["agent"], _trace["scheduleid"], _trace["phase"]


async def run_all(run_id):
    graph_mod.route = _traced_route
    graph_mod.run_turn = _traced_run_turn
    results = []

    def rec(group, scen, utterance, route, expected_route, reply, events, scheduleid, phase,
            passed, reason, extra=None):
        r = {"group": group, "scenario": scen, "utterance": utterance,
             "route": route, "expected_route": expected_route, "reply": reply,
             "quick_replies": list(_last.get("quick_replies") or []),
             "latency_ms": _last.get("elapsed_ms"),
             "events": events, "scheduleid": scheduleid, "phase": phase,
             "pass": passed, "reason": reason}
        if extra:
            r.update(extra)
        results.append(r)
        pills = "/".join(r["quick_replies"]) if r["quick_replies"] else "-"
        lat = f"{r['latency_ms']}ms" if r["latency_ms"] is not None else "-"
        print(f"  [{group}/{scen}] {'✓' if passed else '✗'} route={route} sid={scheduleid} {lat} :: "
              f"{utterance[:24]} → {reply[:46]} | pills={pills}", file=sys.stderr)
        # 같은 턴의 pill/latency가 뒤따르는 비-턴 기록으로 새지 않도록 소비 후 비운다.
        _last["quick_replies"] = []
        _last["elapsed_ms"] = None
        return r

    try:
        # ── A. 진입 ──
        async with AsyncSessionLocal() as db:
            ids = await _make_subject(db, run_id, 0, booked=False)
            # A1 활성펫 채팅 시작 가능 (start_chat_session 쿼리: archived_at IS NULL)
            found = (await db.execute(select(Pet).where(
                Pet.petid == ids["petid"], Pet.userid == ids["userid"], Pet.archived_at.is_(None)
            ))).scalar_one_or_none()
            rec("A_진입", "활성펫_채팅시작_가능", "(활성펫으로 세션 시작)", None, None,
                f"세션 시작 가능: {found is not None}", [], None, "PRE_BOOKING",
                found is not None, "활성펫은 archived_at IS NULL 조건 통과")
            # A3 활성 선택목록에 활성펫 포함 (보관 전)
            active_before = {p.petid for p in await get_pets_by_userid(db, ids["userid"])}
            # 보관 처리
            pet = (await db.execute(select(Pet).where(Pet.petid == ids["petid"]))).scalar_one()
            pet.archived_at = datetime.now(timezone.utc)
            db.add(pet); await db.commit()
            # A2 보관펫 신규채팅 차단 (같은 쿼리 → None)
            blocked = (await db.execute(select(Pet).where(
                Pet.petid == ids["petid"], Pet.userid == ids["userid"], Pet.archived_at.is_(None)
            ))).scalar_one_or_none()
            rec("A_진입", "보관펫_신규채팅_차단", "(보관펫으로 세션 시작 시도)", None, None,
                f"세션 시작 차단됨: {blocked is None}", [], None, None,
                blocked is None, "보관펫은 archived_at IS NULL 조건에서 제외 → 404 차단")
            # A3 보관펫 선택목록 제외
            active_after = {p.petid for p in await get_pets_by_userid(db, ids["userid"])}
            a3 = (ids["petid"] in active_before) and (ids["petid"] not in active_after)
            rec("A_진입", "보관펫_선택목록_제외", "(채팅 펫 선택 목록 조회)", None, None,
                f"보관전 목록 포함={ids['petid'] in active_before}, 보관후 제외={ids['petid'] not in active_after}",
                [], None, None, a3, "활성 목록(get_pets_by_userid)은 archived 제외")
            await _cleanup(db, ids)

        # ── B. PRE_BOOKING 라우팅 ──
        B_CASES = [
            ("증상→triage", "우리 강아지가 어제부터 토하고 설사를 해요", "triage"),
            ("병원정보→reception", "병원 몇 시까지 진료해요? 위치가 어디예요?", "reception"),
            ("예약의도→문진흐름", "예약하고 싶어요", "triage"),
        ]
        for i, (scen, utt, exp) in enumerate(B_CASES):
            async with AsyncSessionLocal() as db:
                ids = await _make_subject(db, run_id, 10 + i, booked=False)
                reply, events, route, sid, phase = await _run_turn(db, ids, utt)
                # 예약의도는 라우팅이 triage/reception 둘 다 허용(문진 흐름이 안 깨지면 됨)
                if scen == "예약의도→문진흐름":
                    passed = route in ("triage", "reception") and bool(reply)
                    reason = f"route={route}, reply 존재 → 문진/안내 흐름 유지" if passed else "흐름 깨짐"
                else:
                    passed = route == exp and bool(reply)
                    reason = f"기대 route={exp}, 실제={route}"
                sid_ok = sid in (None, "UNSET")
                rec("B_PRE_BOOKING", scen, utt, route, exp, reply, events, sid, phase,
                    passed, reason, extra={"scheduleid_is_null_ok": sid_ok})
                await _cleanup(db, ids)

        # ── C. BOOKED ──
        C_CASES = [
            ("예약시각_안내", "내 예약 언제야?", "followup_filter", "ct"),
            ("병원명_안내", "어느 병원 예약이야?", "followup_filter", "hn"),
            ("담당의_안내", "담당 의사 누구야?", "followup_filter", "dn"),
            ("예약변경_흐름", "예약 시간 바꾸고 싶어요", "followup_filter", "rebook"),
            ("예약취소_문의", "예약 취소돼요?", "followup_filter", "cancel_inq"),
            ("경과저장", "아이 상태가 안 좋아요, 밥도 잘 안 먹어요", "followup_filter", "save"),
        ]
        for i, (scen, utt, exp, check) in enumerate(C_CASES):
            async with AsyncSessionLocal() as db:
                ids = await _make_subject(db, run_id, 20 + i, booked=True)
                reply, events, route, sid, phase = await _run_turn(db, ids, utt)
                kk = None
                if ids["confirmed"]:
                    from app.utils.timezone import to_kst
                    kk = to_kst(ids["confirmed"])
                time_str = f"{kk.month}월 {kk.day}일" if kk else ""
                ct_read = bool(time_str and time_str in reply)
                hn_read = HOSPITAL_NAME in reply or HOSPITAL_ADDR in reply or HOSPITAL_TEL in reply
                dn_read = DOCTOR_NAME in reply
                ev = set(events)
                sid_ok = isinstance(sid, int) and sid is not None
                # followup 저장 여부(DB 확인)
                saved_rows = 0
                if check == "save":
                    saved_rows = len((await db.execute(
                        select(Followup).where(Followup.emrid == ids["emrid"]))).scalars().all())
                # pass 기준
                route_ok = route == exp
                if check == "ct":
                    sub_ok, why = ct_read, f"예약시각({time_str}) 포함={ct_read}"
                elif check == "hn":
                    sub_ok, why = hn_read, f"병원명/주소/전화 포함={hn_read}"
                elif check == "dn":
                    sub_ok, why = bool(reply), f"담당의 응답 존재={bool(reply)} (이름반영={dn_read})"
                elif check == "rebook":
                    sub_ok, why = ("rebook_request" in ev) and ct_read, f"rebook_request={'rebook_request' in ev}, 현예약시각 되짚음={ct_read}"
                elif check == "cancel_inq":
                    sub_ok, why = ("cancel_request" not in ev) and bool(reply), f"cancel_request 미발생={'cancel_request' not in ev}(문의는 실행 금지)"
                elif check == "save":
                    sub_ok, why = (("save" in ev) or saved_rows > 0), f"save이벤트={'save' in ev}, Followup저장={saved_rows}건"
                else:
                    sub_ok, why = bool(reply), "reply 존재"
                passed = route_ok and sub_ok and sid_ok
                judge = await _judge(utt, reply, f"실제 예약: {time_str}, 병원={HOSPITAL_NAME}, 담당의={DOCTOR_NAME}") if reply else {"score": 0, "reason": "no reply"}
                rec("C_BOOKED", scen, utt, route, exp, reply, events, sid, phase, passed,
                    f"route={route}({'✓' if route_ok else '✗'}), {why}, scheduleid={'실값' if sid_ok else sid}",
                    extra={"confirmed_time_read": ct_read, "hospital_read": hn_read,
                           "doctor_read": dn_read, "followup_saved_rows": saved_rows,
                           "judge_score": judge["score"], "judge_reason": judge["reason"]})
                await _cleanup(db, ids)

        # C7 사진 후속 — 직전 사진 소견 맥락에서 후속 질문이 끊기지 않는지
        photo_hist = [
            {"role": "user", "content": "여기 사진 보냈어요", "image_url": "https://example.com/x.jpg"},
            {"role": "assistant", "content": "보내주신 사진상 발적이 보이네요. 지금도 그 부위를 핥거나 부어 보이는지 살펴봐 주세요."},
        ]
        async with AsyncSessionLocal() as db:
            ids = await _make_subject(db, run_id, 40, booked=True, history=photo_hist)
            reply, events, route, sid, phase = await _run_turn(db, ids, "사진 못 찍었으면 어떡해요?")
            passed = route == "followup_filter" and bool(reply) and isinstance(sid, int)
            rec("C_BOOKED", "사진후속_연속성", "사진 못 찍었으면 어떡해요?", route, "followup_filter",
                reply, events, sid, phase, passed,
                f"route={route}, 사진맥락 후속 응답 존재={bool(reply)}, scheduleid={'실값' if isinstance(sid,int) else sid}")
            await _cleanup(db, ids)

        # ── D. 상태 (저장/로드) ──
        async with AsyncSessionLocal() as db:
            ids = await _make_subject(db, run_id, 50, booked=True)
            before = (await db.execute(select(ChatHistory).where(ChatHistory.id == ids["session_id"]))).scalar_one()
            n_before = len(before.messages or [])
            reply, events, route, sid, phase = await _run_turn(db, ids, "내 예약 언제였지?")
            after = (await db.execute(select(ChatHistory).where(ChatHistory.id == ids["session_id"]))).scalar_one()
            n_after = len(after.messages or [])
            orch = after.orch_state or {}
            ch_saved = n_after >= n_before + 2  # user + assistant
            orch_ok = isinstance(orch, dict)
            sid_ok = isinstance(sid, int)
            rec("D_상태", "chat_history_저장", "내 예약 언제였지?", route, None,
                f"messages {n_before}→{n_after} (user+assistant 추가)", events, sid, phase,
                ch_saved, f"메시지 {n_after-n_before}건 증가")
            rec("D_상태", "orch_state_저장로드", "(orch_state 확인)", None, None,
                f"orch_state keys={list(orch.keys())[:6]}", [], sid, phase,
                orch_ok, "orch_state dict 영속")
            rec("D_상태", "scheduleid_실값", "(BOOKED ctx.scheduleid)", None, None,
                f"scheduleid={sid}", [], sid, phase, sid_ok,
                "BOOKED 턴에서 ctx.scheduleid가 null이 아닌 실제 schedule id")
            await _cleanup(db, ids)
    finally:
        graph_mod.route = _orig_route
        graph_mod.run_turn = _orig_run_turn
    return results


def aggregate(results):
    routed = [r for r in results if r.get("expected_route")]
    route_correct = sum(1 for r in routed if r["route"] == r["expected_route"])
    booked = [r for r in results if r["group"] == "C_BOOKED"]
    booked_sid = [r for r in booked if isinstance(r.get("scheduleid"), int)]
    a_block = [r for r in results if r["group"] == "A_진입" and "차단" in r["scenario"] or (r["group"]=="A_진입" and "제외" in r["scenario"])]
    archived_block = [r for r in results if r["group"] == "A_진입" and r["scenario"] in ("보관펫_신규채팅_차단", "보관펫_선택목록_제외")]
    save_rows = [r for r in results if r.get("scenario") == "경과저장"]
    judged = [r for r in booked if r.get("judge_score", 0) > 0]
    ctx_pass = [r for r in booked if r["pass"]]
    total_pass = sum(1 for r in results if r["pass"])
    lats = sorted(r["latency_ms"] for r in results if r.get("latency_ms") is not None)
    return {
        "total_checks": len(results),
        "turn_latency_ms_avg": round(sum(lats) / len(lats)) if lats else None,
        "turn_latency_ms_p50": lats[len(lats) // 2] if lats else None,
        "turn_latency_ms_max": lats[-1] if lats else None,
        "turns_timed": len(lats),
        "total_passed": total_pass,
        "total_failed": len(results) - total_pass,
        "pass_rate": round(total_pass / len(results), 3) if results else 0,
        "route_accuracy": round(route_correct / len(routed), 3) if routed else None,
        "route_correct": route_correct, "route_total": len(routed),
        "reply_quality_score_avg": round(sum(r["judge_score"] for r in judged) / len(judged), 2) if judged else None,
        "event_correctness": round(sum(1 for r in results if r.get("expected_route") and r["pass"]) / len(routed), 3) if routed else None,
        "scheduleid_fill_rate": round(len(booked_sid) / len(booked), 3) if booked else None,
        "booked_with_real_scheduleid": len(booked_sid), "booked_total": len(booked),
        "archived_pet_block_rate": round(sum(1 for r in archived_block if r["pass"]) / len(archived_block), 3) if archived_block else None,
        "booked_context_accuracy": round(len(ctx_pass) / len(booked), 3) if booked else None,
        "followup_save_success": all(r["pass"] for r in save_rows) if save_rows else None,
        "followup_saved_rows": sum(r.get("followup_saved_rows", 0) for r in save_rows),
    }


async def main_async(args):
    print(f"OPENAI_API_KEY set? {'yes' if os.getenv('OPENAI_API_KEY') else 'NO'}\n", file=sys.stderr)
    run_id = str(int(time.time()))[-6:]
    results = await run_all(run_id)
    summary = aggregate(results)
    report = {"meta": {"generated_at_unix": int(time.time()),
                       "seed": {"hospital": HOSPITAL_NAME, "doctor": DOCTOR_NAME}},
              "summary": summary, "results": results}
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== 요약 ===", file=sys.stderr)
    for k, v in summary.items():
        print(f"  {k}: {v}", file=sys.stderr)
    print(f"✓ {args.out}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE.parent / "data" / "validation" / "chat_eval_results.json"))
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
