"""followup_marathon_report.json → 사람이 눈으로 보는 HTML 리포트.

턴별로 보호자 질문 / 봇 답변 / pill(quick_replies) / 담당 에이전트 /
저장여부·카테고리·심각도 / 기대-실제 일치를 한 화면에 펼친다.
재실행 없이 기존 JSON만 변환한다(순수 stdlib).

실행:
  python3 backend/scripts/render_followup_report.py \
    --in backend/data/validation/followup_marathon_report.json \
    --out backend/data/validation/followup_marathon_report.html
  open backend/data/validation/followup_marathon_report.html
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_IN = HERE.parent / "data" / "validation" / "followup_marathon_report.json"
DEFAULT_OUT = HERE.parent / "data" / "validation" / "followup_marathon_report.html"


HTML = """<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<title>followup_filter 장기대화 리포트</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,'Segoe UI','Apple SD Gothic Neo',sans-serif;background:#f6f7f9;color:#1a1a1a;font-size:14px;line-height:1.5;padding:24px;max-width:1080px;margin:0 auto}
h1{font-size:22px;margin-bottom:4px}.sub{color:#6b7280;margin-bottom:18px;font-size:13px}
h2{font-size:17px;margin:26px 0 10px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:14px}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:12px 14px}
.card .n{font-size:22px;font-weight:700}.card .l{font-size:12px;color:#6b7280;margin-top:2px}
.card.good .n{color:#16a34a}.card.warn .n{color:#d97706}.card.bad .n{color:#dc2626}
.sess{background:#fff;border:1px solid #e5e7eb;border-radius:12px;margin-bottom:14px;overflow:hidden}
.sesshead{padding:12px 16px;background:#f9fafb;border-bottom:1px solid #eee;display:flex;gap:8px;align-items:center;flex-wrap:wrap;cursor:pointer}
.sesshead .nm{font-weight:700;font-size:15px}.sesshead .sp{margin-left:auto;color:#6b7280;font-size:12px}
.turns{padding:6px 10px}
.turn{border-bottom:1px solid #f3f4f6;padding:10px 6px}
.turn:last-child{border-bottom:none}
.turn.miss{background:#fef2f2;border-radius:8px}
.turn.save{background:#f7fdf9}
.row{display:flex;gap:8px;align-items:flex-start;margin:2px 0}
.tnum{color:#9ca3af;font-size:11px;font-weight:700;min-width:34px;padding-top:2px}
.who{font-size:11px;font-weight:700;color:#9ca3af;min-width:48px;padding-top:2px}
.usr{color:#111827}.bot{color:#1d4ed8}
.pills{display:flex;gap:5px;flex-wrap:wrap;margin:5px 0 2px 90px}
.pill{background:#eef2ff;color:#4f46e5;border:1px solid #c7d2fe;border-radius:999px;padding:2px 10px;font-size:11px;font-weight:600}
.meta{margin:5px 0 0 90px;display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.b{font-size:11px;padding:2px 8px;border-radius:999px;font-weight:600;white-space:nowrap}
.bl{background:#eff6ff;color:#2563eb}.gr{background:#f0fdf4;color:#16a34a}.am{background:#fffbeb;color:#d97706}
.rd{background:#fef2f2;color:#dc2626}.gy{background:#f3f4f6;color:#6b7280}.pp{background:#f5f3ff;color:#7c3aed}
.legend{font-size:12px;color:#6b7280;margin:6px 0 16px}
.legend .b{margin-right:4px}
input[type=checkbox]{display:none}
label.tog{cursor:pointer;user-select:none}
.filterbar{margin:10px 0 4px;font-size:12px;color:#6b7280}
.filterbar label{cursor:pointer;margin-right:12px}
</style></head><body>
<h1>followup_filter 장기대화 리포트</h1>
<div class="sub" id="meta"></div>
<div class="legend">
 <span class="b bl">담당 에이전트</span>
 <span class="b gr">save=경과저장</span>
 <span class="b pp">rebook/cancel/time</span>
 <span class="b am">clarify/reply</span>
 빨강 배경=기대와 불일치 · 연녹 배경=저장됨
</div>
<div class="filterbar">
 <label><input type="checkbox" id="onlymiss" onchange="render()"> 불일치만 보기</label>
 <label><input type="checkbox" id="onlysave" onchange="render()"> 저장턴만 보기</label>
</div>
<div id="root"></div>
<script>
const DATA = __DATA__;
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function obsCls(o){return o==='save'?'gr':(o==='rebook'||o==='cancel'||o==='time')?'pp':(o==='reception'||o&&o.indexOf('handoff')===0)?'bl':o==='error'?'rd':'am'}
function routeCls(r){return r==='followup_filter'?'bl':r==='reception'?'pp':'gy'}
function turnKeywords(t){
  const xs=[];
  if(t.intent_hint) xs.push('의도:'+t.intent_hint);
  if(t.observed) xs.push('결과:'+t.observed);
  if(t.routed) xs.push('route:'+t.routed);
  if(t.save_meta){ xs.push('저장:'+t.save_meta.category); xs.push('심각도:'+t.save_meta.severity); }
  (t.events||[]).forEach(e=>xs.push('event:'+e));
  (t.quick_replies||[]).slice(0,5).forEach(p=>xs.push('CTA:'+p));
  return [...new Set(xs)];
}

function turnHTML(t, scripted){
  const miss = scripted && t.match===false;
  const saved = t.observed==='save';
  let cls='turn'+(miss?' miss':'')+(saved?' save':'');
  let h=`<div class="${cls}" data-miss="${miss?1:0}" data-save="${saved?1:0}">`;
  h+=`<div class="row"><span class="tnum">t${String(t.turn).padStart(2,'0')}</span><span class="who">🧑 보호자</span><span class="usr">${esc(t.user_message)}</span></div>`;
  h+=`<div class="row"><span class="tnum"></span><span class="who">🤖 봇</span><span class="bot">${esc(t.reply)}</span></div>`;
  if(t.quick_replies&&t.quick_replies.length)
    h+=`<div class="pills">`+t.quick_replies.map(p=>`<span class="pill">${esc(p)}</span>`).join('')+`</div>`;
  const kws=turnKeywords(t);
  if(kws.length)
    h+=`<div class="pills">`+kws.map(p=>`<span class="pill">#${esc(p)}</span>`).join('')+`</div>`;
  // rebook(예약 변경/앞당김) 트리거 — 실제 슬롯은 DB 연동 경로(repro_followup_session.py 등)에서만
  // 계산되므로, DB-less 마라톤 리포트에선 '검색 트리거됨'을 명시해 '시간 안 보여줌' 오해를 막는다.
  if(t.events&&t.events.indexOf('rebook_request')>=0)
    h+=`<div class="pills"><span class="pill">🔎 더 빠른 예약 슬롯 검색 트리거됨 (실 슬롯은 DB 연동 시 노출)</span></div>`;
  h+=`<div class="meta"><span class="b ${routeCls(t.routed)}">route: ${esc(t.routed)}</span>`;
  h+=`<span class="b ${obsCls(t.observed)}">${esc(t.observed)}</span>`;
  if(scripted){h+=`<span class="b ${miss?'rd':'gy'}">기대: ${esc(t.expected)} ${miss?'✗':'✓'}</span>`;}
  if(t.intent_hint)h+=`<span class="b gy">의도: ${esc(t.intent_hint)}</span>`;
  if(t.save_meta){const m=t.save_meta;h+=`<span class="b gr">${esc(m.category)} · ${esc(m.severity)}${m.emergency?' · 🚨응급':''}</span>`;}
  if(t.handoff)h+=`<span class="b pp">handoff→${esc(t.handoff)}</span>`;
  h+=`<span class="b gy">요약누적 ${t.summary_len}자</span>`;
  if(t.error)h+=`<span class="b rd">ERROR: ${esc(t.error)}</span>`;
  h+=`</div></div>`;
  return h;
}

function sessionHTML(title, sub, turns, scripted){
  let h=`<div class="sess"><div class="sesshead" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none'">`;
  h+=`<span class="nm">${esc(title)}</span><span class="sp">${esc(sub)}</span></div>`;
  h+=`<div class="turns">`+turns.map(t=>turnHTML(t,scripted)).join('')+`</div></div>`;
  return h;
}

function render(){
  const onlymiss=document.getElementById('onlymiss').checked;
  const onlysave=document.getElementById('onlysave').checked;
  const root=document.getElementById('root');root.innerHTML='';
  let metaTxt=[];

  if(DATA.scripted){
    const s=DATA.scripted.summary;
    metaTxt.push(`scripted ${s.matched}/${s.total_turns} 일치 (${Math.round(s.match_rate*100)}%)`);
    let cards=`<h2>① scripted (턴별 기대동작 자동채점)</h2><div class="cards">`;
    cards+=card(s.matched+'/'+s.total_turns,'기대-실제 일치',s.matched<s.total_turns?'warn':'good');
    cards+=card(Math.round(s.match_rate*100)+'%','일치율',s.match_rate<0.9?'warn':'good');
    cards+=card(s.scenarios,'시나리오 수','');
    cards+='</div>';root.innerHTML+=cards;
    DATA.scripted.scenarios.forEach(sc=>{
      let turns=sc.turns;
      if(onlymiss)turns=turns.filter(t=>t.match===false);
      if(onlysave)turns=turns.filter(t=>t.observed==='save');
      const sub=`${sc.turn_count}턴 · 일치 ${sc.matched}/${sc.turn_count} · 저장 ${sc.save_count}턴 · 최종요약 ${sc.final_summary_len}자`;
      root.innerHTML+=sessionHTML('📋 '+sc.name+' ('+sc.pet.name+'/'+sc.pet.species+')',sub,turns,true);
    });
  }
  if(DATA.sim){
    root.innerHTML+='<h2>② sim (LLM 가상보호자 핑퐁 — 관찰)</h2>';
    DATA.sim.sessions.forEach(se=>{
      let turns=se.turns;
      if(onlysave)turns=turns.filter(t=>t.observed==='save');
      if(onlymiss)turns=[];
      const sub=`${se.turn_count}턴 · followup_filter ${se.stayed_in_followup}턴 · 저장 ${se.save_count}턴 · 최종요약 ${se.final_summary_len}자`;
      metaTxt.push(`sim/${se.pet.name} followup ${se.stayed_in_followup}/${se.turn_count}`);
      root.innerHTML+=sessionHTML('💬 '+se.pet.name+'/'+se.pet.species,sub,turns,false);
    });
  }
  document.getElementById('meta').textContent=metaTxt.join('  ·  ');
}
function card(n,l,cls){return `<div class="card ${cls||''}"><div class="n">${n}</div><div class="l">${l}</div></div>`}
render();
</script></body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", type=Path, default=DEFAULT_IN)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    data = json.loads(args.inp.read_text(encoding="utf-8"))
    html = HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    args.out.write_text(html, encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
