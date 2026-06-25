"""pytest 수집 설정.

아래 모듈들은 과거 리팩터로 '사라진 옛 API'를 import 하는 stale 테스트라,
수집 단계에서 ImportError 로 전체 실행을 멈추게 한다. CI 게이트가 멎지 않도록
명시적으로 수집에서 제외한다. (삭제/복구는 별도 작업 — 아래 사유 참고)

  - triage_regression/test_triage_engine.py : ai.triage.engine(트리워크 엔진, 제거됨) 참조
  - triage_regression/test_triage_prompt.py : ai.triage.prompt._build_triage_system_prompt(제거됨) 참조
  - shadow_triage/test_guardian_safe.py     : app.api.chat._guardian_safe_triage(제거됨) 참조

triage_regression/test_triage_live.py 는 import 가 유효하고 `-m live` 로만 도므로
제외하지 않는다(키 없는 CI 에선 `-m "not live"` 로 자동 비선택됨).
"""

collect_ignore = [
    "triage_regression/test_triage_engine.py",
    "triage_regression/test_triage_prompt.py",
    "shadow_triage/test_guardian_safe.py",
]
