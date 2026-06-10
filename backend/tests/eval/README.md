# MediPaw 정량 평가 하네스 (tests/eval)

중간발표(master) → 현재(main)의 개선을 **측정값**으로 보이기 위한 평가 모음.
"AI가 AI를 평가한다"는 비판이 나오지 않도록, 핵심 지표는 전부 **LLM-free(재현 가능)**
또는 **객관 속성(재현성·지연·실제 토큰 비용)** 으로 설계했다.

## 무엇을 측정하나

| 파일 | 측정 | LLM 호출 | 신뢰 근거 |
|---|---|---|---|
| `test_determinism.py` | 트리아지 엔진의 **명세 일치도** + **결정론(분산)** | ❌ 없음 | 독립 레퍼런스 채점기(`reference_scorer.py`)와 차등 비교 + 반복 실행 분산 측정 |
| `test_graph_structure.py` | LangGraph 오케스트레이션 **배선** | ❌ 없음 | 컴파일된 그래프에서 노드/조건부 엣지 직접 검증 |
| `test_llm_variance.py` | (대조군) LLM-only 분류기 **재현성** | ✅ LIVE | 같은 입력 K회 → 불일치율 측정(정답 판단 아님) |
| `test_latency_cost.py` | **실측 지연 + 실제 토큰 비용** | ✅ LIVE | `response.usage` 실제 토큰 × 공개 단가 |
| `test_multilingual.py` | 다국어 **라우팅 + 증상어 보존 + 표시 커버리지** | A:❌ / B·C:✅ LIVE | 라우팅=정규식(결정론), 보존율=결정론 키워드 매칭(번역만 실제) |

> `reference_scorer.py` 는 `vet_triage.json > scoring_engine` 명세를 engine.py와
> **독립적으로 재구현**한 것이다. 두 구현이 모든 경로에서 일치하면 = 엔진이 사람이 쓴
> 명세대로 동작한다는 증거(self-eval 아님, 명세 vs 구현의 교차검증).

## 실행

```bash
# 1) LLM-free (무료, 항상) — 스택 없이도 됨
cd backend && PYTHONPATH=.. python3 -m tests.eval.run_eval

# 2) LIVE 포함 (OpenAI 소량 호출 + 지연/비용 실측)
#    RAG 지연까지 보려면 DB(pgvector)가 떠 있어야 함(./dev.sh)
cd backend && RUN_LIVE_EVAL=1 PYTHONPATH=.. python3 -m tests.eval.run_eval

# 3) pytest 로 (스택/의존성 설치 환경)
pytest tests/eval -q                      # LLM-free 만
RUN_LIVE_EVAL=1 pytest tests/eval -q      # LIVE 포함
```

## 산출물 (gitignore 처리됨)

- `backend/eval_determinism.json` — 명세 일치도/분산 원자료
- `backend/eval_llm_variance.json` — LLM 재현성 원자료 (LIVE)
- `backend/eval_latency_cost.json` — 지연/비용 원자료 (LIVE)
- `backend/EVAL_REPORT.md` — 취합 리포트(발표용)

## 발표용 한 줄

> "응급도 산정은 규칙 엔진이라 **4,000회 실행 분산 0%**(재현성 100%)이고, 명세 일치도
> 100%입니다. 같은 걸 LLM이 직접 하면 같은 입력에도 답이 흔들립니다(대조군 측정).
> 그래서 우리는 판단을 LLM에 맡기지 않고 규칙으로 고정하고, LLM은 구조화·요약·검색에만 씁니다."
