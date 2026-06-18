# ai/orchestrator/ — 챗봇 v2 지휘자 (구조 지도)

문서: 전체 그림 [docs/ORCHESTRATOR_REDESIGN.md](../../docs/ORCHESTRATOR_REDESIGN.md) · 작업 명세 [docs/AGENT_SPECS.md](../../docs/AGENT_SPECS.md)

## 한 턴의 여정 (이거 하나만 머리에 넣으면 됨)
```
사용자 발화
  → chat.py(send_message)            # 진입점 (TODO: run_turn 호출로 교체)
  → state.build_context()            # DB → SessionContext (리드)
  → graph: route()                   # 누가 답할지 (router.py)
  → agents/<담당>.run(ctx) → AgentResult
  → state.apply_patch + save_state   # 상태 저장 (orch_state)
  → SSE로 reply/quick_replies 전송
```

## 파일 지도 (누가 뭘 채우나)
```
ai/orchestrator/
├─ contracts.py        # 공용 입출력 타입 (SessionContext/AgentResult/Intent)  ★먼저 읽기
├─ graph.py            # LangGraph 뼈대 (route→노드)            [리드]
├─ router.py           # 누가 답할지 결정 (sticky+phase+LLM분류)  [리드]
├─ state.py            # DB ↔ SessionContext 로드/저장           [리드]
├─ agents/
│   ├─ reception.py        # 응대                                [A]
│   ├─ triage.py           # 문진(노드 어댑터, 로직은 ai/agents/triage) [리드]
│   ├─ schedule.py         # 스케줄(기존 재사용 래핑)             [리드]
│   └─ followup_filter.py  # 경과 필터                           [B]
└─ mcp/
    ├─ server.py        # medipaw-mcp 서버(FastMCP) + 도구 5개    [리드(+A 합의)]
    └─ client.py        # MCP 클라이언트(langchain-mcp-adapters)  [리드]

(별도) ai/agents/prescription/  # 처방전 — 수의사 EMR, 챗봇 무관  [리드]
(재사용) ai/agents/chart, ai/agents/validation  # 백그라운드      [리드 / C]
```

## 지금 상태
- 전부 **stub** — 라우팅은 실제로 돌고(아래), 각 에이전트는 placeholder 응답만.
- 스모크 테스트: `run_turn(ctx)` → phase/flow 따라 알맞은 노드로 감.
- 채우는 법: 자기 `agents/*.py`의 `run()` 안 TODO를 [AGENT_SPECS.md](../../docs/AGENT_SPECS.md) 자기 섹션대로 구현.

## 리드 TODO (뼈대→실물)
1. `chat_historyDB.orch_state` JSON 컬럼 추가(alembic)
2. `state.build_context` / `save_state` 구현
3. `router.route`에 LLM 분류 붙이기
4. `chat.py` 진입점을 `run_turn`으로 교체 + AgentResult→SSE
5. MCP 서버/클라이언트 실제 연결
