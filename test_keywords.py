import sys
sys.path.insert(0, ".")
from ai.agents.followup_filter.schema import keyword_fallback, SeverityHint

tests = [
    "발작이 멈추지 않아요",
    "숨을 계속 헐떡여요",
    "갑자기 쓰러졌어요",
    "의식이 없는 것 같아요",
    "소변을 못 봐요",
    "대변에 피가 섞여 나와요",
    "혈뇨가 나왔어요",
    "소변 색이 붉어졌어요",
]
total = 0
for t in tests:
    result = keyword_fallback(t)
    is_urgent = result.severity_hint == SeverityHint.URGENT_POSSIBLE
    total += is_urgent
    print(f"{'O' if is_urgent else 'X'} [{result.severity_hint.value}] {t}")

print(f"\n합계: {total}/8")
