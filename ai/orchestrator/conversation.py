"""채팅 에이전트 공통 대화 헬퍼 — 같은 대화방을 '같은 규칙'으로 읽게 한다.

reception / triage / followup_filter 가 제각기 복제하던 history 포맷 규칙을 한 곳으로 모으고
(format_history), 문진 결론을 에이전트 간에 잇는 durable 맥락 메모리를 조합한다(triage_context).

설계 원칙:
 - 에이전트끼리 서로를 import 하지 않는다. 공유는 오케스트레이터 계층(이 모듈)만 통한다.
 - 별도 history 저장소를 만들지 않는다. 원천은 항상 chat_historyDB.messages(= ctx.history).
 - triage_context 는 '새 저장 경로'를 만들지 않는다. triage 가 완료 시 orch_state.triage_state
   ['last_complete']['data'] 에 이미 영속한 값을 읽어 조합만 한다(읽기 전용).
"""
from __future__ import annotations


def format_history(
    history: list[dict] | None,
    n: int | None = 6,
    *,
    user_label: str = "user",
    bot_label: str = "assistant",
    skip_empty: bool = False,
) -> str:
    """최근 n턴을 'label: content' 줄로 직렬화. n=None 이면 전체.

    창 크기(n)와 라벨은 호출자가 정한다 — 기존 각 에이전트의 출력과 동일하게 맞추기 위함이다.
    skip_empty=True 면 content 가 빈 메시지를 건너뛴다(라우터처럼 잡음 제거가 필요한 곳).
    """
    items = [m for m in (history or []) if isinstance(m, dict)]
    if skip_empty:
        items = [m for m in items if m.get("content")]
    recent = items if n is None else items[-n:]

    def _label(m: dict) -> str:
        return user_label if m.get("role") == "user" else bot_label

    return "\n".join(f"{_label(m)}: {m.get('content', '')}" for m in recent)


def triage_context(triage_state: dict | None) -> str:
    """직전 문진 결론(주증상·문진 요약)을 짧은 '참고 맥락' 블록으로. 없으면 ''.

    예약을 부른 증상 맥락이 raw 최근 N턴 창 밖으로 밀려나도 reception/followup 이 이어서
    이해하도록, triage 가 완료 시 남긴 영속 값에서 뽑아 준다.

    ★ 의료 안전: '의심질환(suspected_conditions)'은 진단 단정을 유발할 수 있어 일부러 제외한다.
      보호자가 실제로 말한 사실(주증상·요약)만 배경으로 넘기고, 단정 금지를 블록에 명시한다.
    """
    data = ((triage_state or {}).get("last_complete") or {}).get("data") or {}
    chief = ", ".join(c for c in (data.get("chief_complaints") or []) if c)
    summary = (data.get("triage_summary") or "").strip()
    lines = []
    if chief:
        lines.append(f"- 주증상: {chief}")
    if summary:
        lines.append(f"- 문진 요약: {summary}")
    if not lines:
        return ""
    return "[지난 문진 맥락 — 참고용 배경, 진단·처방 단정 금지]\n" + "\n".join(lines)
