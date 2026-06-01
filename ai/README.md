# MediPaw AI — 6-Agent Pipeline

수의학 AI 트리아지·예약·차트·검증·품질심사·경과모니터링 파이프라인입니다.

## 폴더 구조

```
ai/
├── agents/                 # 에이전트별 Python 모듈 (프롬프트 + 실행 로직)
│   ├── base.py             # OpenAI 비동기 공용 함수
│   ├── triage.py           # [1] Triage Agent — Modified VTL 5단계 문진
│   ├── schedule.py         # [2] Schedule Agent — 최적 진료시간 결정
│   ├── chart.py            # [3] Chart Agent — SOAP 차트 초안
│   ├── validation.py       # [4] Validation Agent — 정합성 Cross Validation
│   ├── judge.py            # [5] Judge Agent — LLM-as-Judge 품질 심사
│   └── followup.py         # [6] Followup Agent — 경과 모니터링
├── services/
│   └── vision_model.py     # CNN 피부(6종)/안구(11종) 분류
├── router.py               # FastAPI 라우터 /api/agent/*
├── schemas.py              # Pydantic 스키마
├── tasks.py                # BackgroundTask 오케스트레이터 + DB 저장
├── requirements-ai.txt     # AI 전용 추가 의존성
├── frontend/
│   ├── useAgentPipeline.ts # 보호자 React 훅 (TypeScript)
│   └── agentPrompts.ts     # 프론트엔드용 시스템 프롬프트 빌더
└── docker/
    ├── docker-compose.yml  # 전체 스택 (DB + Backend + 프론트 ×2)
    ├── Dockerfile.backend
    ├── Dockerfile.guardian
    ├── Dockerfile.vet
    ├── nginx-guardian.conf
    └── nginx-vet.conf
```

---

## 6개 에이전트 흐름

```
보호자 입력
  │
  ▼
[1] Triage Agent ──────── 문진 루프 (Modified VTL 5단계, CoT)
  │  ↕ 사진 첨부 시
  │  └─ Vision CNN (피부 6종 / 안구 11종)
  │
  ▼ triageInfo 완성
[2] Schedule Agent ─────── 진료시간 결정 (체중/증상 복잡도/재진 이력 반영)
  │
  ▼ 슬롯 선택 → confirmAppointment
  ├─── [3] Chart Agent ────── SOAP 차트 초안 (background, gpt-4o)
  ├─── [4] Validation Agent ─ 정합성 검증 (background, gpt-4o, 내부 전용)
  └─── [5] Judge Agent ────── 독립 품질 심사 (fire-and-forget, gpt-4o-mini, 20% 샘플링, audit.log)
  │
  ▼ need_followup=true 시
[6] Followup Agent ──────── 경과 모니터링 (예약일까지, 롤링 6턴 윈도우)
```

---

## Backend 통합 (3단계)

### 1. 파일 복사
```bash
# ai 폴더를 backend 루트에 배치
cp -r ai/ backend/ai/

# 또는 개별 파일 위치:
# ai/router.py      → backend/app/api/agent.py
# ai/tasks.py       → backend/app/workers/tasks.py
# ai/schemas.py     → backend/app/schemas/agent.py
# ai/services/      → backend/app/services/
# ai/agents/        → backend/app/agents/
```

### 2. main.py에 라우터 등록
```python
# backend/app/main.py 에 추가
from ai.router import router as agent_router
app.include_router(agent_router)
```

### 3. CNN 모델 파일 배치
```
backend/models/
  ├── efficientnet_b0_pet_skin.pth      # 피부 6클래스
  └── efficientnet_b0_eye_10epoch.pth   # 안구 11클래스
```

### 4. 추가 의존성 설치
```bash
pip install -r ai/requirements-ai.txt
```

---

## Frontend 통합 (2단계)

### 1. 훅 파일 복사
```bash
cp ai/frontend/useAgentPipeline.ts frontend/guardian-web/src/hooks/
cp ai/frontend/agentPrompts.ts      frontend/guardian-web/src/hooks/
```

### 2. 챗봇 페이지에서 훅 사용
```tsx
// frontend/guardian-web/src/pages/chatbot/chatbot-page.tsx
import { useAgentPipeline } from "../hooks/useAgentPipeline";

function ChatbotPage() {
  const pipeline = useAgentPipeline({
    onAppointmentConfirmed: (payload) => {
      // appointmentQueue에 추가, DB API 호출 등
    },
    onChartReady: (apptId, chartData, validationResult) => {
      // VetDashboard에 전달 (SSE 또는 API)
    },
    onFollowupUpdate: (apptId, messages, summary) => {
      // followupDB 업데이트
    },
  });

  // pipeline.startTriage(pet)   ← 반려동물 선택 시
  // pipeline.sendMessage(text)  ← 메시지 전송
  // pipeline.confirmAppointment(slot) ← 예약 확정
  // pipeline.sendFollowupMessage(text) ← 경과 보고
}
```

### 3. emrid 연동 (백엔드 예약 확정 후)
```tsx
// 백엔드 API에서 실제 emrid를 받으면 훅에 전달
const response = await apiClient.get(`/api/appointment/confirm/${apptId}`);
pipeline.setRealEmrId(response.data.result.emrid);
```

---

## API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/agent/chat` | OpenAI 프록시 (API 키 서버 보관) |
| POST | `/api/agent/run` | 에이전트 실행 (BackgroundTasks) |
| GET  | `/api/agent/sse/{task_id}` | SSE 실시간 진행 스트리밍 |
| POST | `/api/agent/vision/skin` | 피부질환 CNN 분석 |
| POST | `/api/agent/vision/eye` | 안구질환 CNN 분석 |

### /api/agent/run payload 예시
```json
// triage
{"agent_type": "triage", "emrid": 1,
 "payload": {"pet": {"name":"뽀미","breed":"말티즈","age":3,"weight":4,"species":"dog"}, "messages": [...]}}

// chart (예약 확정 후 background)
{"agent_type": "chart", "emrid": 1, "scheduleid": 2,
 "payload": {"pet": {...}, "triage_result": {...}, "chat_history": [...]}}

// validation (chart와 병렬)
{"agent_type": "validation", "emrid": 1, "scheduleid": 2,
 "payload": {"pet": {...}, "triage_result": {...}, "schedule_result": {...}}}

// followup
{"agent_type": "followup", "emrid": 1,
 "payload": {"pet": {...}, "triage_info": {...}, "messages": [...], "accumulated_summary": "..."}}
```

---

## Docker로 실행

```bash
# 1. 루트에 .env 파일 생성 (backend/.env.example 참고)
cp backend/.env.example .env
# OPENAI_API_KEY, SECRET_KEY, POSTGRES_PASSWORD 등 설정

# 2. 빌드 및 실행
docker compose -f ai/docker/docker-compose.yml up --build

# 3. DB 마이그레이션 (최초 1회 자동 실행됨)

# 접속
# 보호자 앱:   http://localhost:5173
# 수의사 앱:   http://localhost:5174
# API 문서:    http://localhost:8000/docs
```

### CNN 모델 없이 실행
모델 파일(.pth)이 없어도 서버는 정상 실행됩니다.
Vision 엔드포인트는 `prediction: null`로 응답하고 image_url만 반환합니다.

---

## 운영 정책 — Validation / Judge 는 내부 전용

**두 에이전트 결과는 보호자/수의사에게 직접 노출하지 않는다.** 운영팀 내부 품질 모니터링 용도다.

| 에이전트 | 저장 위치 | 노출 정책 |
|----------|-----------|-----------|
| Validation | `validation_resultDB` (DB) | 저장만. 수의사 화면 warning 노출 여부는 **추후 결정**. `GET /doctor/emr/{id}/validation` API는 존재하나 UI에서 경고로 띄우지 않음 |
| Judge | `audit.log` (로그 파일) | 화면 노출 없음. 운영팀 로그 확인 전용. 현재 `emrid % 5 == 0` (20%) 샘플링 |

> Judge 결과에 대한 액션(예: REVIEW_NEEDED 시 알림)은 아직 연결돼 있지 않음 — 액션을 붙이는 시점에 전수 실행 전환 검토.

---

## 주요 설계 결정

| 결정 | 이유 |
|------|------|
| OpenAI 프록시 방식 | API 키 클라이언트 노출 방지 |
| BackgroundTasks + SSE | Chart/Validation을 보호자 화면 차단 없이 비동기 실행 |
| Judge Agent 완전 독립 호출 | Self-bias 방지 (Zheng et al. 2023) |
| Followup 롤링 6턴 윈도우 | 컨텍스트 크기 고정, 누적 요약으로 보완 |
| CNN 실패 시 image_url 보장 | 모델 오류가 예약 흐름 전체를 막지 않도록 |
| gpt-4o-mini (트리아지/경과/심사) / gpt-4o (차트/검증) | 비용과 정확도 균형 |
