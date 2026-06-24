"""펫 보관/복원/영구삭제 API E2E (실 dev API :8000 대상).

검증:
  - 펫 생성 → 활성 목록 포함
  - 보관 → 활성 목록 제외 / 보관함 목록 포함
  - 복원 → 활성 목록 재포함
  - 기록 없는 펫 영구삭제 → 200 성공
  - 기록 있는 펫(채팅 세션) 영구삭제 → 409 + 법령 문구
결과를 pet_archive_e2e.json 으로 남긴다. dev DB는 끝에 정리.
"""
from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

BASE = "http://localhost:8000"
OUT = Path(__file__).resolve().parent.parent / "data" / "validation" / "pet_archive_e2e.json"
LEGAL_SNIPPET = "수의사법"


def call(method: str, path: str, token: str | None = None, body: dict | None = None) -> dict:
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            return {"status": r.status, "body": json.loads(raw) if raw else None}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = raw
        return {"status": e.code, "body": parsed}


def active_ids(token):
    r = call("GET", "/pets", token)
    return {p["pet_id"] for p in (r["body"] or [])}, r


def archived_ids(token):
    r = call("GET", "/pets/archived", token)
    return {p["pet_id"] for p in (r["body"] or [])}, r


def main():
    steps = []
    checks = {}

    login = call("POST", "/auth/login", body={"loginid": "guardian_test", "password": "Test1234!"})
    steps.append({"step": "login", "request": "POST /auth/login (guardian_test)", "status": login["status"]})
    if login["status"] != 200:
        print("LOGIN FAILED", login, file=sys.stderr)
        OUT.write_text(json.dumps({"error": "login_failed", "login": login}, ensure_ascii=False, indent=2))
        sys.exit(1)
    token = login["body"]["result"]["access_token"]

    # ── 시나리오 1: 기록 없는 펫 — 생성/보관/복원/영구삭제 ──
    petA = call("POST", "/pets", token, {"petname": "E2E무기록", "species": "dog", "breed": "Mixed", "gender": "male", "weight_kg": 4.5})
    a_id = petA["body"]["pet_id"]
    steps.append({"step": "create_pet_A_no_records", "request": "POST /pets", "status": petA["status"], "response": petA["body"]})

    act, act_r = active_ids(token)
    checks["A_in_active_after_create"] = a_id in act
    steps.append({"step": "active_list_after_create", "request": "GET /pets", "status": act_r["status"], "contains_A": a_id in act})

    arch = call("DELETE", f"/pets/{a_id}", token)
    steps.append({"step": "archive_A", "request": f"DELETE /pets/{a_id}", "status": arch["status"], "response": arch["body"]})

    act, _ = active_ids(token)
    arc, _ = archived_ids(token)
    checks["A_not_in_active_after_archive"] = a_id not in act
    checks["A_in_archived_after_archive"] = a_id in arc
    steps.append({"step": "lists_after_archive", "active_contains_A": a_id in act, "archived_contains_A": a_id in arc})

    restore = call("POST", f"/pets/{a_id}/restore", token)
    steps.append({"step": "restore_A", "request": f"POST /pets/{a_id}/restore", "status": restore["status"], "response": restore["body"]})
    act, _ = active_ids(token)
    checks["A_in_active_after_restore"] = a_id in act
    steps.append({"step": "active_after_restore", "active_contains_A": a_id in act})

    # 영구삭제 전 다시 보관(영구삭제는 보관함에서만)
    call("DELETE", f"/pets/{a_id}", token)
    perm_a = call("DELETE", f"/pets/{a_id}/permanent", token)
    checks["A_permanent_delete_success"] = perm_a["status"] == 200
    steps.append({"step": "permanent_delete_A_no_records", "request": f"DELETE /pets/{a_id}/permanent", "status": perm_a["status"], "response": perm_a["body"]})
    act, _ = active_ids(token)
    arc, _ = archived_ids(token)
    checks["A_gone_after_permanent"] = (a_id not in act) and (a_id not in arc)

    # ── 시나리오 2: 기록 있는 펫 — 영구삭제 409 ──
    petB = call("POST", "/pets", token, {"petname": "E2E기록", "species": "cat", "breed": "Korean", "gender": "female", "weight_kg": 3.2})
    b_id = petB["body"]["pet_id"]
    steps.append({"step": "create_pet_B_with_records", "request": "POST /pets", "status": petB["status"], "response": petB["body"]})

    sess = call("POST", "/chat/sessions", token, {"pet_id": b_id})
    sess_id = (sess["body"] or {}).get("result", {}).get("session_id")
    steps.append({"step": "create_chat_session_for_B", "request": "POST /chat/sessions", "status": sess["status"], "session_id": sess_id})

    call("DELETE", f"/pets/{b_id}", token)  # archive B
    perm_b = call("DELETE", f"/pets/{b_id}/permanent", token)
    pb = perm_b["body"] if isinstance(perm_b["body"], dict) else {}
    detail = pb.get("message") or pb.get("detail")  # 커스텀 핸들러는 message, 기본은 detail
    checks["B_permanent_delete_409"] = perm_b["status"] == 409
    checks["B_409_has_legal_text"] = bool(detail and LEGAL_SNIPPET in detail)
    steps.append({"step": "permanent_delete_B_with_records", "request": f"DELETE /pets/{b_id}/permanent",
                  "status": perm_b["status"], "detail": detail})

    # B는 보관 상태로 남아있는지(영구삭제 차단됐으니 보관함에 유지)
    arc, _ = archived_ids(token)
    checks["B_still_in_archived_after_409"] = b_id in arc

    # archived pet의 기존 채팅 기록 조회 유지 확인
    if sess_id:
        det = call("GET", f"/chat/sessions/{sess_id}", token)
        checks["archived_pet_past_chat_still_viewable"] = det["status"] == 200
        steps.append({"step": "archived_pet_chat_detail_viewable", "request": f"GET /chat/sessions/{sess_id}", "status": det["status"]})

    # ── 정리: B의 채팅 세션 삭제 후 영구삭제 ──
    if sess_id:
        call("DELETE", f"/chat/sessions/{sess_id}", token)
    cleanup_b = call("DELETE", f"/pets/{b_id}/permanent", token)
    steps.append({"step": "cleanup_B", "request": f"DELETE /pets/{b_id}/permanent (after removing records)", "status": cleanup_b["status"]})

    passed = sum(1 for v in checks.values() if v)
    total = len(checks)
    report = {
        "base_url": BASE,
        "summary": {"checks_passed": passed, "checks_total": total, "pass_rate": round(passed / total, 3) if total else 0},
        "checks": checks,
        "steps": steps,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== pet archive E2E: {passed}/{total} checks passed ===", file=sys.stderr)
    for k, v in checks.items():
        print(f"  {'✓' if v else '✗'} {k}", file=sys.stderr)
    print(f"✓ {OUT}", file=sys.stderr)
    sys.exit(0 if passed == total else 2)


if __name__ == "__main__":
    main()
