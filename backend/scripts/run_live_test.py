"""라이브 파이프라인 관찰 테스트 (리팩토링된 현재 구현 기준).

각 벤치마크 케이스에 대해:
  1) 노트 기반 '가상 보호자' ↔ TriageAgent 핑퐁 대화 (봇 질문 → 보호자 답변 루프)
     → 핑퐁이 자연스러운지, quick_replies(pill)가 답변유도에 맞게 나오는지 관찰
  2) ScheduleAgent → 예상 진료시간 + 내원 전 케어팁 (응급도 연결)
  3) ChartAgent → SOAP/의심질환/처방 초안
관찰용이라 gold 채점은 하지 않는다(그건 리팩토링 후 run_vet_eval.py 담당).
booking 슬롯추천(DB결합)·validation/judge(미리팩토링)는 범위 외.

병렬: asyncio + Semaphore(동시 N). I/O(LLM 대기) 바운드라 동시성으로 가속.

실행(도커):
  docker cp backend/scripts/run_live_test.py docker-backend-1:/app/backend/scripts/
  docker exec -w /app/backend docker-backend-1 \
    python scripts/run_live_test.py --n 12 --concurrency 6 --out /tmp/live.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))   # /app/backend (app.* 용)
sys.path.insert(0, str(HERE.parent.parent))  # /app (ai.* 용)

from ai.agents.triage.agent import TriageAgent
from ai.agents.schedule.agent import ScheduleAgent
from ai.agents.chart.agent import ChartAgent
from ai.llm import call_llm, call_llm_json

# ── validation/judge는 아직 미리팩토링이라 삭제된 ..observability / .base 를 import한다.
#    로직은 손대지 않고, 사라진 의존성만 런타임 shim으로 복원해 '현재 로직 그대로' 평가한다.
#    (레포에 파일을 추가하지 않으려고 sys.modules에 주입)
import types
from contextlib import contextmanager

_obs = types.ModuleType("ai.observability")
_obs.push_scores = lambda *a, **k: None
@contextmanager
def _score_trace(*a, **k):
    yield
_obs.score_trace = _score_trace
_obs.get_langfuse_handler = lambda *a, **k: None
sys.modules["ai.observability"] = _obs

_base = types.ModuleType("ai.agents.base")
async def _call_openai_once(user: str, system: str = "", max_tokens: int = 800, **k) -> dict:
    prompt = (system + "\n\n" + user) if system else user
    try:
        return await call_llm_json(prompt)
    except Exception:
        try:  # 코드펜스 등 비순수 JSON 방어
            raw = await call_llm(prompt, temperature=0)
            raw = raw.strip().strip("`")
            if raw.startswith("json"):
                raw = raw[4:]
            return json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        except Exception:
            return {}
_base.call_openai_once = _call_openai_once
_base.call_openai = _call_openai_once
sys.modules["ai.agents.base"] = _base

from ai.agents.validation import run_validation   # noqa: E402
from ai.agents.judge import run_judge              # noqa: E402

DATASET = HERE.parent / "data" / "validation" / "vet_eval_dataset.json"
MAX_TURNS = 7
_URGENCY_NUM = {"RED": 1, "ORANGE": 2, "YELLOW": 3, "GREEN": 5}
_URGENCY_WINDOW = {"RED": "immediate", "ORANGE": "emergency_today",
                   "YELLOW": "urgent_24h", "GREEN": "routine_72h"}
_noop = lambda *a, **k: None


def map_pet(pet: dict) -> dict:
    sex = (pet.get("sex") or "").upper()
    gender = "male" if sex.startswith("M") else "female" if sex.startswith("F") else None
    return {
        "species": pet.get("species") or "dog",
        "breed": pet.get("breed"),
        "age": pet.get("age_years"),
        "weight": pet.get("weight_kg"),
        "gender": gender,
        "neutered": sex.endswith("N"),
    }


PATIENT_SYS = """너는 동물병원에 온 반려동물 보호자다. 아래는 네 아이의 실제 상태(수의사 노트)다.
너는 비전문가이고 이 노트의 정보만 안다.

[규칙]
- 챗봇의 질문에 한국어 구어체로 1~2문장 짧게 답한다.
- 노트에 없는 내용을 물으면 "잘 모르겠어요" / "그건 못 봤어요"라고 한다(지어내지 마라).
- 진단명·의학용어를 쓰지 마라. 관찰한 증상만 일상어로 말한다.

[내 아이 상태(노트)]
{note}

[지금까지 대화]
{transcript}

[챗봇의 마지막 질문]
{question}

위 질문에 대한 보호자의 답변만 한국어로 출력해라(따옴표·이름표 없이)."""


async def simulate_patient(note: str, messages: list[dict], question: str) -> str:
    transcript = "\n".join(
        f"{'챗봇' if m['role']=='assistant' else '보호자'}: {m['content']}" for m in messages
    ) or "(없음)"
    prompt = PATIENT_SYS.format(note=note[:1200], transcript=transcript[-1500:], question=question)
    try:
        reply = await call_llm(prompt, temperature=0.5)
        return reply.strip().strip('"').split("\n")[0][:300]
    except Exception as e:
        return "잘 모르겠어요."


async def _safe_validation(payload: dict) -> dict:
    try:
        r = await run_validation(payload, _noop, None, None)
        return {"overall": r.get("overall"),
                "checks": {c["item"]: c["status"] for c in (r.get("checks") or [])},
                "summary": r.get("summary")}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


async def _safe_judge(payload: dict) -> dict:
    try:
        r = await run_judge(payload, _noop, None, None)
        return {"verdict": r.get("monitoring_verdict"), "scores": r.get("quality_scores"),
                "turns": r.get("turn_count"), "notes": r.get("notes")}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


async def run_flawed(case: dict, sem: asyncio.Semaphore) -> dict:
    """flawed 케이스: corrupted_outputs(이미 검사기 입력 형태)를 validation/judge에 먹여
    expected_verdict를 잡는지 평가(검사기 recall)."""
    async with sem:
        co = case["injected_defect"]["corrupted_outputs"]
        ev = case.get("expected_verdict", {})
        payload = {
            "pet": co.get("pet", {}),
            "triage_result": co.get("triage_result", {}),
            "schedule_result": co.get("schedule_result", {}),
            "chart_result": co.get("chart_result"),
        }
        val = await _safe_validation(payload)
        judge = await _safe_judge({"triage_result": co.get("triage_result", {}),
                                   "chat_history": case.get("input", {}).get("messages", [])})
        # 엄밀한 감지: 결함 유형에 '대응하는' validation 체크가 WARN이어야 진짜 감지.
        # (무관한 체크가 떠서 ATTENTION인 건 감지가 아님 — 특히 rx_safety는 현재 체크 자체가 없어 항상 미탐)
        defect = case["injected_defect"]["type"]
        DEFECT_CHECK = {
            "redflag_urgency_mismatch": "응급신호 정합성",
            "missing_field": "데이터 완전성",
            "chart_symptom_drift": "문진-차트 일치도",
            "rx_safety": "처방 안전성",  # 현재 validation.py에 없음 → 구조적으로 미탐(=리팩토링 타깃)
        }
        checks = val.get("checks") or {}
        target_check = DEFECT_CHECK.get(defect)
        caught = checks.get(target_check) == "WARN"
        return {
            "case_id": case["case_id"], "tier": "flawed", "defect": defect,
            "species": case.get("species"),
            "target_check": target_check,
            "expected": {"validation": (ev.get("validation") or {}).get("overall"),
                         "judge": (ev.get("judge") or {}).get("monitoring_verdict")},
            "validation": val, "judge": judge,
            "caught": caught,                                   # 결함 대응 체크 발화 여부(엄밀)
            "any_attention": val.get("overall") == "ATTENTION",  # 무관 이유 포함(참고)
            "judge_flag": judge.get("verdict") == "NEEDS_REVIEW",
            "note": case["injected_defect"].get("description"),
        }


async def run_one(case: dict, sem: asyncio.Semaphore) -> dict:
    async with sem:
        t0 = time.time()
        rec = {"case_id": case["case_id"], "species": case.get("species"),
               "input_style": case.get("input_style"), "category": case.get("category"),
               "note": case["source"].get("original_note", "")[:200]}
        try:
            agent = TriageAgent()
            pet = map_pet(case["input"]["pet"])
            note = case["source"].get("original_note", "")
            # 첫 보호자 발화 = 데이터셋의 첫 user 턴(노트 기반 lay 증상)
            first_user = next((m["content"] for m in case["input"]["messages"]
                               if m.get("role") == "user"), "아이가 좀 아파요.")

            messages: list[dict] = []
            transcript: list[dict] = []
            user_msg = first_user
            triage_final = None
            pill_turns = 0
            for turn in range(MAX_TURNS):
                result = await agent.process_message(user_msg, messages, pet)
                reply = result.get("reply", "")
                pills = result.get("quick_replies") or []
                if pills:
                    pill_turns += 1
                transcript.append({"user": user_msg, "bot": reply, "pills": pills,
                                   "urgency": result.get("urgency"), "score": result.get("score")})
                messages.append({"role": "user", "content": user_msg})
                messages.append({"role": "assistant", "content": reply, "meta": result.get("state")})
                if result.get("is_complete"):
                    triage_final = result
                    break
                user_msg = await simulate_patient(note, messages, reply)

            completed = triage_final is not None
            rec["triage"] = {
                "completed": completed,
                "turns": len(transcript),
                "pill_turns": pill_turns,
                "final_urgency": (triage_final or {}).get("urgency"),
                "final_score": (triage_final or {}).get("score"),
                "chief_complaints": (triage_final or {}).get("chief_complaints"),
                "suspected": (triage_final or {}).get("suspected_conditions"),
                "summary": (triage_final or {}).get("triage_summary"),
            }
            rec["transcript"] = transcript

            # 트리아지 결과를 schedule/chart 입력 형태로
            tview = triage_final or transcript[-1]
            triage_dict = {
                "urgency": tview.get("urgency") or tview.get("final_urgency"),
                "score": tview.get("score") or tview.get("final_score"),
                "chief_complaints": (triage_final or {}).get("chief_complaints"),
                "suspected_conditions": (triage_final or {}).get("suspected_conditions"),
                "triage_summary": (triage_final or {}).get("triage_summary"),
                "fields": (triage_final or {}).get("fields"),
                "is_initial_visit": True,
            }

            # 2) 스케줄
            try:
                sched = await ScheduleAgent().estimate_duration(pet, triage_dict)
                tips = await ScheduleAgent().care_guidance(triage_dict)
                rec["schedule"] = {**sched, "care_tips": tips}
            except Exception as e:
                rec["schedule"] = {"error": f"{type(e).__name__}: {e}"}

            # 3) 차트
            chart = {}
            try:
                chart = await ChartAgent().generate(pet, triage_dict, chat_history=messages)
                rec["chart"] = {
                    "intake_summary": chart.get("intake_summary"),
                    "soap": chart.get("soap"),
                    "differential": chart.get("differential_diagnosis"),
                    "prescription": chart.get("prescription_draft"),
                    "empty": not bool(chart),
                }
            except Exception as e:
                rec["chart"] = {"error": f"{type(e).__name__}: {e}"}

            # 4) validation + judge (현재 로직 그대로) — 정상 파이프라인 출력에 대해
            #    검사기가 헛경보(ATTENTION/NEEDS_REVIEW) 안 내는지(precision) 관찰
            urg = (triage_final or {}).get("urgency")
            fields = (triage_final or {}).get("fields") or {}
            ccs = (triage_final or {}).get("chief_complaints") or []
            adapted_triage = {
                "chief_complaint": (ccs[0] if ccs else None) or fields.get("chief_complaint"),
                "symptom_onset": fields.get("symptom_onset") or fields.get("onset"),
                "symptom_summary": (triage_final or {}).get("triage_summary"),
                "symptom_keywords": ccs + ((triage_final or {}).get("suspected_conditions") or []),
                "red_flags": ccs if (triage_final or {}).get("red_flag") else [],
                "urgency_level_num": _URGENCY_NUM.get(urg, 5),
            }
            val_pet = {"species": pet.get("species"), "age": pet.get("age"), "gender": pet.get("gender")}
            sched_res = {"estimated_duration_min": (rec.get("schedule") or {}).get("estimated_duration_min"),
                         "slot_window": _URGENCY_WINDOW.get(urg)}
            rec["validation"] = await _safe_validation(
                {"pet": val_pet, "triage_result": adapted_triage,
                 "schedule_result": sched_res, "chart_result": chart})
            rec["judge"] = await _safe_judge(
                {"triage_result": adapted_triage, "chat_history": messages})

        except Exception as e:
            import traceback
            rec["error"] = f"{type(e).__name__}: {e}"
            rec["trace"] = traceback.format_exc()[-800:]
        rec["elapsed_s"] = round(time.time() - t0, 1)
        print(f"  ✓ {rec['case_id']} turns={rec.get('triage',{}).get('turns','?')} "
              f"urg={rec.get('triage',{}).get('final_urgency')} {rec['elapsed_s']}s", file=sys.stderr)
        return rec


async def main_async(args):
    from collections import Counter
    data = json.loads(Path(args.dataset).read_text())
    clean = [c for c in data["cases"] if c["tier"] == "clean" and c.get("input", {}).get("messages")]
    flawed = [c for c in data["cases"] if c["tier"] == "flawed"]
    clean_cases = clean[: args.n]
    # flawed는 결함 유형 4종 균형 샘플링 (앞에서 자르면 한 유형만 뽑힘)
    by_def: dict[str, list] = {}
    for fc in flawed:
        by_def.setdefault(fc["injected_defect"]["type"], []).append(fc)
    per = max(1, args.flawed_n // max(len(by_def), 1))
    flawed_cases = []
    for lst in by_def.values():
        flawed_cases += lst[:per]
    flawed_cases = flawed_cases[: args.flawed_n]
    sem = asyncio.Semaphore(args.concurrency)
    print(f"▶ clean {len(clean_cases)} + flawed {len(flawed_cases)} · 동시성 {args.concurrency}", file=sys.stderr)
    t0 = time.time()
    clean_res, flawed_res = await asyncio.gather(
        asyncio.gather(*(run_one(c, sem) for c in clean_cases)),
        asyncio.gather(*(run_flawed(c, sem) for c in flawed_cases)),
    )
    elapsed = round(time.time() - t0, 1)

    ok = [r for r in clean_res if "error" not in r]
    def vcount(key, val):
        return sum(1 for r in ok if (r.get("validation") or {}).get(key) == val)
    # flawed recall (검사기가 잡은 비율) — defect 유형별
    fl_by_def = {}
    for d in sorted(set(r["defect"] for r in flawed_res)):
        grp = [r for r in flawed_res if r["defect"] == d]
        fl_by_def[d] = {"caught": sum(1 for r in grp if r["caught"]), "total": len(grp)}

    summary = {
        "clean": {
            "n": len(clean_res),
            "errors": sum(1 for r in clean_res if "error" in r),
            "triage_completed": sum(1 for r in ok if r.get("triage", {}).get("completed")),
            "avg_turns": round(sum(r.get("triage", {}).get("turns", 0) for r in ok) / max(len(ok), 1), 1),
            "had_pills": sum(1 for r in ok if r.get("triage", {}).get("pill_turns", 0) > 0),
            "urgency_dist": dict(Counter(r.get("triage", {}).get("final_urgency") for r in ok)),
            "schedule_ok": sum(1 for r in ok if "error" not in r.get("schedule", {})),
            "chart_ok": sum(1 for r in ok if not r.get("chart", {}).get("empty", True) and "error" not in r.get("chart", {})),
            # 정상인데 검사기가 경보 낸 비율(=false alarm; 낮을수록 좋음)
            "validation_ATTENTION": vcount("overall", "ATTENTION"),
            "validation_OK": vcount("overall", "OK"),
            "judge_NEEDS_REVIEW": sum(1 for r in ok if (r.get("judge") or {}).get("verdict") == "NEEDS_REVIEW"),
            "judge_HEALTHY": sum(1 for r in ok if (r.get("judge") or {}).get("verdict") == "HEALTHY"),
        },
        "flawed": {
            "n": len(flawed_res),
            "caught_total": sum(1 for r in flawed_res if r["caught"]),
            "recall_by_defect": fl_by_def,
        },
        "elapsed_s": elapsed,
        "caveat": ("clean 케이스의 validation '데이터 완전성'은 어댑터/계약 불일치로 과대경보될 수 있음"
                   "(리팩토링된 triage가 chief_complaint/symptom_onset 키를 안 내보내고 펫 age/gender가 비어있음). "
                   "신뢰 신호는 문진-차트 일치도·응급신호, 그리고 flawed recall."),
    }
    out = {"summary": summary, "clean_results": clean_res, "flawed_results": flawed_res}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))
    if args.html:
        Path(args.html).write_text(render_html(out))
        print(f"✓ HTML: {args.html}", file=sys.stderr)
    print(f"\n✓ {args.out}\n  {json.dumps(summary, ensure_ascii=False)}", file=sys.stderr)


def render_html(out: dict) -> str:
    data_json = json.dumps(out, ensure_ascii=False)
    return """<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<title>MediPaw 라이브 테스트 리포트</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}body{font-family:-apple-system,'Segoe UI',sans-serif;background:#f6f7f9;color:#1a1a1a;font-size:14px;line-height:1.5;padding:24px;max-width:1100px;margin:0 auto}
h1{font-size:22px;margin-bottom:4px}.sub{color:#6b7280;margin-bottom:20px;font-size:13px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:14px}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:12px 14px}
.card .n{font-size:22px;font-weight:700}.card .l{font-size:12px;color:#6b7280;margin-top:2px}
.card.warn .n{color:#d97706}.card.bad .n{color:#dc2626}.card.good .n{color:#16a34a}
h2{font-size:16px;margin:22px 0 10px}
.case{background:#fff;border:1px solid #e5e7eb;border-radius:10px;margin-bottom:8px;overflow:hidden}
.head{padding:11px 14px;cursor:pointer;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.head:hover{background:#fafafa}.body{display:none;border-top:1px solid #f0f0f0;padding:14px}
.case.open .body{display:block}.case.open .head{background:#f9fafb}
.b{font-size:11px;padding:2px 8px;border-radius:999px;font-weight:600;white-space:nowrap}
.red{background:#fef2f2;color:#dc2626}.amber{background:#fffbeb;color:#d97706}.green{background:#f0fdf4;color:#16a34a}
.gray{background:#f3f4f6;color:#6b7280}.blue{background:#eff6ff;color:#2563eb}.purple{background:#f5f3ff;color:#7c3aed}
.cid{font-weight:600;font-size:13px}.sp{margin-left:auto;color:#9ca3af;font-size:12px}
.msg{margin:6px 0}.u{color:#374151}.bot{color:#1d4ed8}.who{font-weight:600;font-size:11px;color:#9ca3af}
.pills{display:flex;gap:5px;flex-wrap:wrap;margin:3px 0 8px 14px}
.pill{background:#eef2ff;color:#4f46e5;border:1px solid #c7d2fe;border-radius:999px;padding:2px 9px;font-size:11px}
.sec{margin-top:12px;padding-top:10px;border-top:1px dashed #eee}.sec h4{font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px}
pre{background:#f9fafb;border-radius:8px;padding:10px;font-size:12px;white-space:pre-wrap;word-break:break-word;line-height:1.5}
.kv{display:flex;gap:8px;flex-wrap:wrap}.kv span{background:#f9fafb;border-radius:6px;padding:3px 8px;font-size:12px}
.note{font-size:12px;color:#6b7280;font-style:italic}
</style></head><body>
<h1>MediPaw 라이브 테스트 리포트</h1>
<div class="sub" id="meta"></div>
<div id="root"></div>
<script>const DATA=""" + data_json + """;
const $=h=>{const d=document.createElement('div');d.innerHTML=h;return d.firstElementChild};
function uColor(u){return u==='RED'?'red':u==='ORANGE'?'amber':u==='YELLOW'?'amber':'green'}
function vColor(s){return s==='ATTENTION'||s==='WARN'||s==='NEEDS_REVIEW'?'amber':s==='OK'||s==='PASS'||s==='HEALTHY'?'green':'gray'}
const s=DATA.summary;
document.getElementById('meta').textContent=`소요 ${s.elapsed_s}s · clean ${s.clean.n} / flawed ${s.flawed.n}`;
const root=document.getElementById('root');
if(s.caveat)root.innerHTML+=`<div style="background:#fffbeb;border:1px solid #fde68a;color:#92400e;border-radius:8px;padding:10px 12px;margin-bottom:14px;font-size:12px">⚠ ${s.caveat}</div>`;
// 통계 카드
function cards(title,arr){let h=`<h2>${title}</h2><div class="cards">`;arr.forEach(c=>h+=`<div class="card ${c.cls||''}"><div class="n">${c.n}</div><div class="l">${c.l}</div></div>`);return h+'</div>'}
const c=s.clean;
root.innerHTML+=cards('① 파이프라인 (clean) 통계',[
 {n:c.triage_completed+'/'+c.n,l:'트리아지 완료'},
 {n:c.avg_turns,l:'평균 턴 수'},
 {n:c.had_pills+'/'+c.n,l:'pill 출현'},
 {n:c.schedule_ok+'/'+c.n,l:'스케줄 OK'},
 {n:c.chart_ok+'/'+c.n,l:'차트 OK',cls:c.chart_ok<c.n?'warn':'good'},
 {n:c.validation_ATTENTION+'/'+c.n,l:'validation 경보(정상인데)',cls:c.validation_ATTENTION>0?'warn':'good'},
 {n:c.judge_NEEDS_REVIEW+'/'+c.n,l:'judge 재검토(정상인데)',cls:c.judge_NEEDS_REVIEW>0?'warn':'good'},
]);
root.innerHTML+=`<div class="sub">urgency 분포: ${JSON.stringify(c.urgency_dist)}</div>`;
// flawed recall 카드
const f=s.flawed;let fc=[{n:f.caught_total+'/'+f.n,l:'검사기 결함 감지',cls:f.caught_total<f.n?'bad':'good'}];
for(const [d,o] of Object.entries(f.recall_by_defect))fc.push({n:o.caught+'/'+o.total,l:'recall: '+d,cls:o.caught<o.total?'bad':'good'});
root.innerHTML+=cards('② 검사기 (flawed) recall',fc);
// clean 케이스 상세
root.innerHTML+='<h2>clean 케이스 (정상 — 파이프라인 관찰)</h2>';
DATA.clean_results.forEach(r=>{
 const t=r.triage||{};const card=$(`<div class="case"></div>`);
 const head=`<div class="cid">${r.case_id}</div>
  ${r.error?'<span class="b red">ERROR</span>':''}
  <span class="b ${uColor(t.final_urgency)}">${t.final_urgency||'-'} / ${t.final_score??'-'}</span>
  <span class="b gray">${t.turns||0}턴</span>
  ${t.pill_turns?'<span class="b blue">pill '+t.pill_turns+'</span>':'<span class="b amber">pill 없음</span>'}
  <span class="b ${vColor((r.validation||{}).overall)}">val ${(r.validation||{}).overall||'-'}</span>
  <span class="b ${vColor((r.judge||{}).verdict)}">judge ${(r.judge||{}).verdict||'-'}</span>
  <span class="sp">${r.species||'?'} · ${r.input_style||''} · ${r.elapsed_s}s</span>`;
 card.appendChild($(`<div class="head" onclick="this.parentNode.classList.toggle('open')">${head}</div>`));
 let b='<div class="body">';
 if(r.error){b+=`<pre>${r.error}\\n${r.trace||''}</pre></div>`;card.appendChild($(b));root.appendChild(card);return}
 b+='<div class="sec"><h4>핑퐁 대화</h4>';
 (r.transcript||[]).forEach(m=>{b+=`<div class="msg"><div class="who">🧑 보호자</div><div class="u">${esc(m.user)}</div></div>
  <div class="msg"><div class="who">🤖 챗봇</div><div class="bot">${esc(m.bot)}</div></div>`;
  if(m.pills&&m.pills.length)b+='<div class="pills">'+m.pills.map(p=>`<span class="pill">${esc(p)}</span>`).join('')+'</div>';});
 b+='</div>';
 b+=`<div class="sec"><h4>트리아지 결과</h4><div class="kv"><span>주증상: ${esc((t.chief_complaints||[]).join(', '))}</span><span>의심: ${esc((t.suspected||[]).join(', '))}</span></div><div class="note">${esc(t.summary||'')}</div></div>`;
 const sc=r.schedule||{};b+=`<div class="sec"><h4>스케줄</h4><div class="kv"><span>예상 ${sc.estimated_duration_min||'-'}분</span></div><div class="note">${esc(sc.reasoning||sc.error||'')}</div>`;
 if(sc.care_tips)b+='<ul style="margin:6px 0 0 16px;font-size:12px">'+sc.care_tips.map(x=>`<li>${esc(x)}</li>`).join('')+'</ul>';b+='</div>';
 const ch=r.chart||{};b+=`<div class="sec"><h4>차트</h4>`+(ch.error?`<span class="b red">${esc(ch.error)}</span>`:`<pre>${esc(JSON.stringify(ch.intake_summary||{},null,1))}</pre>`)+'</div>';
 const v=r.validation||{};b+=`<div class="sec"><h4>validation (현재 로직)</h4><div class="kv">`+Object.entries(v.checks||{}).map(([k,st])=>`<span class="b ${vColor(st)}">${k}: ${st}</span>`).join('')+`</div><div class="note">${esc(v.summary||v.error||'')}</div></div>`;
 const j=r.judge||{};b+=`<div class="sec"><h4>judge (현재 로직)</h4><div class="kv"><span class="b ${vColor(j.verdict)}">${j.verdict||'-'}</span>`+(j.scores?Object.entries(j.scores).map(([k,sv])=>`<span>${k}: ${sv}</span>`).join(''):'')+`</div><div class="note">${esc(j.notes||j.error||'')}</div></div>`;
 b+='</div>';card.appendChild($(b));root.appendChild(card);
});
// flawed 케이스
root.innerHTML+='<h2>flawed 케이스 (결함 주입 — 검사기가 잡아야 함)</h2>';
DATA.flawed_results.forEach(r=>{
 const card=$(`<div class="case"></div>`);
 const head=`<div class="cid">${r.case_id}</div>
  <span class="b purple">${r.defect}</span>
  <span class="b ${r.caught?'green':'red'}">${r.caught?'✓ 감지':'✗ 놓침'}</span>
  <span class="b ${vColor((r.validation||{}).overall)}">val ${(r.validation||{}).overall||'-'}</span>
  <span class="b ${vColor((r.judge||{}).verdict)}">judge ${(r.judge||{}).verdict||'-'}</span>
  <span class="sp">기대 val=${(r.expected||{}).validation||'-'}</span>`;
 card.appendChild($(`<div class="head" onclick="this.parentNode.classList.toggle('open')">${head}</div>`));
 const v=r.validation||{};const j=r.judge||{};
 let b=`<div class="body"><div class="note">${esc(r.note||'')}</div>
  <div class="sec"><h4>validation</h4><div class="kv">`+Object.entries(v.checks||{}).map(([k,st])=>`<span class="b ${vColor(st)}">${k}: ${st}</span>`).join('')+`</div><div class="note">${esc(v.summary||v.error||'')}</div></div>
  <div class="sec"><h4>judge</h4><span class="b ${vColor(j.verdict)}">${j.verdict||'-'}</span> <span class="note">${esc(j.notes||j.error||'')}</span></div></div>`;
 card.appendChild($(b));root.appendChild(card);
});
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=str(DATASET))
    ap.add_argument("--out", default="/tmp/live_test.json")
    ap.add_argument("--n", type=int, default=12, help="clean 케이스 수")
    ap.add_argument("--flawed-n", type=int, default=12, help="flawed 케이스 수")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--html", default=None, help="HTML 리포트 출력 경로")
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
