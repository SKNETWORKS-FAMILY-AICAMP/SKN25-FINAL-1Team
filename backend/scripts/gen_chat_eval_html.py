"""chat_eval_results.json → chat_eval_report.html (답변 전문 포함, 사람이 직접 검토용)."""
import html
import json
import sys
from pathlib import Path

src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("chat_eval_results.json")
out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("chat_eval_report.html")
d = json.loads(src.read_text(encoding="utf-8"))
s = d["summary"]


def esc(x):
    return html.escape(str(x)) if x is not None else ""


rows = []
for r in d["results"]:
    badge = '<span class="ok">PASS</span>' if r["pass"] else '<span class="bad">FAIL</span>'
    exp = f" (기대: {esc(r['expected_route'])})" if r.get("expected_route") else ""
    events = ", ".join(r.get("events") or []) or "—"
    judge = ""
    if r.get("judge_score"):
        judge = f"<div class='meta'>품질 judge: {r['judge_score']}/5 · {esc(r.get('judge_reason'))}</div>"
    extra = []
    for k in ("confirmed_time_read", "hospital_read", "doctor_read", "followup_saved_rows", "scheduleid_is_null_ok"):
        if k in r:
            extra.append(f"{k}={r[k]}")
    extra_s = (" · ".join(extra)) if extra else ""
    pills = "".join(f'<span class="pill">{esc(p)}</span>' for p in (r.get("quick_replies") or [])) or "<span class='meta'>—</span>"
    lat = f"{r['latency_ms']}ms" if r.get("latency_ms") is not None else "—"
    rows.append(f"""
    <tr class="{'rok' if r['pass'] else 'rbad'}">
      <td>{esc(r['group'])}<br><b>{esc(r['scenario'])}</b></td>
      <td class="utt">{esc(r['utterance'])}</td>
      <td>{esc(r['route'])}{exp}<div class="meta">scheduleid: <b>{esc(r['scheduleid'])}</b> · phase: {esc(r['phase'])} · ⏱ {lat}</div></td>
      <td class="reply">{esc(r['reply'])}{judge}</td>
      <td class="pills">{pills}</td>
      <td class="meta">{esc(events)}</td>
      <td>{badge}<div class="meta">{esc(r['reason'])}</div><div class="meta">{esc(extra_s)}</div></td>
    </tr>""")

summary_rows = "".join(
    f"<tr><td>{esc(k)}</td><td><b>{esc(v)}</b></td></tr>" for k, v in s.items()
)

doc = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<title>채팅 종합 E2E 리포트</title>
<style>
 body{{font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif;margin:24px;color:#1a1a1a;background:#fafafa}}
 h1{{font-size:22px}} h2{{font-size:17px;margin-top:28px}}
 table{{border-collapse:collapse;width:100%;background:#fff;font-size:13px}}
 th,td{{border:1px solid #e0e0e0;padding:8px;vertical-align:top;text-align:left}}
 th{{background:#f0f3f7;position:sticky;top:0}}
 .ok{{color:#fff;background:#137333;padding:2px 8px;border-radius:4px;font-weight:700;font-size:12px}}
 .bad{{color:#fff;background:#c5221f;padding:2px 8px;border-radius:4px;font-weight:700;font-size:12px}}
 .reply{{white-space:pre-wrap;max-width:420px;line-height:1.5}}
 .utt{{max-width:180px;white-space:pre-wrap}}
 .meta{{color:#666;font-size:11px;margin-top:4px}}
 .rbad{{background:#fff5f5}}
 .sumtbl{{width:auto;min-width:340px}}
 .note{{background:#fff8e1;border:1px solid #ffe082;padding:10px 14px;border-radius:6px;font-size:13px;margin:10px 0}}
 .pills{{max-width:160px}}
 .pill{{display:inline-block;background:#eef3ff;border:1px solid #c5d6ff;color:#1a3a7a;border-radius:12px;padding:2px 9px;margin:2px;font-size:11px;white-space:nowrap}}
</style></head><body>
<h1>🐾 채팅 종합 E2E 리포트</h1>
<p class="meta">생성: unix {esc(d['meta']['generated_at_unix'])} · seed 병원={esc(d['meta']['seed']['hospital'])}, 담당의={esc(d['meta']['seed']['doctor'])} · 실 dev DB + process_turn(SSE 동일 경로)</p>
<div class="note"><b>핵심 수치</b> — 전체 {s['total_passed']}/{s['total_checks']} 통과 ·
 route accuracy {s['route_accuracy']} · scheduleid fill {s['scheduleid_fill_rate']} (BOOKED {s['booked_with_real_scheduleid']}/{s['booked_total']} 실값) ·
 archived 차단율 {s['archived_pet_block_rate']} · BOOKED 맥락정확도 {s['booked_context_accuracy']} ·
 followup 저장 {s['followup_save_success']}({s['followup_saved_rows']}건) · 답변품질 {s['reply_quality_score_avg']}/5</div>

<h2>요약 지표</h2>
<table class="sumtbl">{summary_rows}</table>

<h2>시나리오별 상세 (답변 전문)</h2>
<table>
 <tr><th>그룹/시나리오</th><th>사용자 입력</th><th>route/agent</th><th>assistant reply (전문)</th><th>pill 키워드</th><th>events</th><th>결과</th></tr>
 {''.join(rows)}
</table>
</body></html>"""

out.write_text(doc, encoding="utf-8")
print(f"wrote {out} ({len(d['results'])} rows)")
