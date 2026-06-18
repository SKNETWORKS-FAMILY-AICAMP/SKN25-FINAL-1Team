"""오케스트레이터 v2 — 인텐트 라우팅형 멀티에이전트 지휘자.

설계서: docs/ORCHESTRATOR_REDESIGN.md
- contracts.py : 모든 에이전트 공용 입출력 규격 (Day1에 팀과 공유하는 단일 기준)
- graph.py     : LangGraph supervisor 뼈대 (route → agent 노드 디스패치)
"""
