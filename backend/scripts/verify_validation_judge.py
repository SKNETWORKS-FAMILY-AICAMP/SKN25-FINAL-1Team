"""Validation/Judge 재설계 라이브 검증 (실제 OpenAI 호출).

실행: backend 디렉터리에서
  PYTHONPATH=<repo>:<repo>/backend python -m scripts.verify_validation_judge
"""
import asyncio
import json

from ai.agents.validation import run_validation
from ai.agents.judge import run_judge


def _noop(_step: str) -> None:
    pass


def _print(title, obj):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)
    print(json.dumps(obj, ensure_ascii=False, indent=2))


PET = {"name": "초코", "species": "dog", "breed": "말티즈", "age": 5, "gender": "수컷", "weight": 4.2}

# ── 케이스 1: 일관된 차트 + Red Flag 표현 존재 ─────────────────────────────
TRIAGE_1 = {
    "chief_complaint": "갑자기 쓰러져서 몸을 떨고 경련함",
    "symptom_onset": "10분 전",
    "symptom_keywords": ["경련", "쓰러짐", "의식저하"],
    "symptom_summary": "10분 전 갑자기 쓰러진 뒤 전신 경련, 의식이 흐림",
    "red_flags": ["지속 경련"],
    "urgency_level_num": 2,
}
CHART_1 = {
    "soap": {"S": "보호자: 갑자기 쓰러져 경련", "O": "발작 의심(수의사 확인 필요)",
             "A": "신경계 발작 가능성", "P": "즉시 신경학적 검사 권고"},
    "differential_diagnosis": [{"name": "특발성 뇌전증", "prob": "중"}, {"name": "저혈당", "prob": "낮음"}],
}

# ── 케이스 2: 문진(소화기) vs 차트(피부) 모순 ─────────────────────────────
TRIAGE_2 = {
    "chief_complaint": "어제부터 토하고 설사함",
    "symptom_onset": "어제 저녁",
    "symptom_keywords": ["구토", "설사", "식욕부진"],
    "symptom_summary": "어제 저녁부터 반복 구토와 설사, 기운 없음",
    "red_flags": [],
    "urgency_level_num": 3,
}
CHART_2 = {
    "soap": {"S": "피부 가려움 호소", "O": "발적 및 탈모 관찰(수의사 확인)",
             "A": "아토피성 피부염 의심", "P": "피부 도말 검사 권고"},
    "differential_diagnosis": [{"name": "아토피 피부염", "prob": "높음"}],
}

SCHEDULE = {"estimated_duration_min": 30, "slot_window": "emergency_today", "is_initial_visit": True}

CHAT_HISTORY = [
    {"role": "assistant", "content": "안녕하세요, 초코에게 어떤 증상이 있나요?"},
    {"role": "user", "content": "갑자기 쓰러지더니 몸을 막 떨어요"},
    {"role": "assistant", "content": "언제부터 그랬는지, 의식은 있는지 알려주세요."},
    {"role": "user", "content": "10분 전부터요. 불러도 반응이 잘 없어요"},
]


async def main():
    # 케이스 1: 일관 + red flag
    v1 = await run_validation(
        {"pet": PET, "triage_result": TRIAGE_1, "schedule_result": SCHEDULE, "chart_result": CHART_1},
        _noop, emrid=1001, scheduleid=2001,
    )
    _print("① Validation — 일관된 차트 + 응급 신호 (기대: overall=ATTENTION, redflag DETECTED, 일관성 PASS)", v1)

    # 케이스 2: 모순
    v2 = await run_validation(
        {"pet": PET, "triage_result": TRIAGE_2, "schedule_result": SCHEDULE, "chart_result": CHART_2},
        _noop, emrid=1002, scheduleid=2002,
    )
    _print("② Validation — 문진(소화기) vs 차트(피부) 모순 (기대: workflow_consistency=WARN)", v2)

    # Judge: 운영 품질 모니터링
    j = await run_judge(
        {"triage_result": TRIAGE_1, "chat_history": CHAT_HISTORY},
        _noop, emrid=1001, scheduleid=2001,
    )
    _print("③ Judge — 운영 품질 모니터링 (기대: monitoring_verdict + quality_scores + turn_count)", j)


if __name__ == "__main__":
    asyncio.run(main())
