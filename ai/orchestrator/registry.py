"""담당 AI 묶음표(레지스트리). 이름 → 그 일을 하는 AI 객체.
graph.py 가 이 표를 보고 알맞은 AI를 부른다.

- 응대·필터: ai/agents/<name>/ 새 패키지
- 문진·스케줄: 기존 패키지에 추가한 node.py (오케스트레이터 어댑터)
"""
from ai.agents.followup_filter import followup_filter
from ai.agents.reception import reception
from ai.agents.schedule.node import schedule
from ai.agents.triage.node import triage

REGISTRY = {a.name: a for a in (reception, triage, schedule, followup_filter)}
