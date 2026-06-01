# 로컬 도커 실행 가이드 (비전공자용)

MediPaw를 내 컴퓨터에서 켜는 방법. **공통 준비물: Docker Desktop 켜기 🐳** (안 켜면 모든 docker 명령이 에러).

> ## 🟢 제일 쉬운 방법 — 레포 루트에서 한 줄
>
> **맥 / 리눅스 (터미널):**
> ```bash
> ./dev.sh
> ```
>
> **윈도우 (PowerShell):**
> ```powershell
> .\dev.ps1
> ```
> (빨간 글씨로 막히면 한 번만: `powershell -ExecutionPolicy Bypass -File .\dev.ps1`)
>
> **윈도우 (Git Bash 쓰는 경우)** 는 맥이랑 똑같이 `./dev.sh` 써도 됩니다.
>
> 이거 하나면 **.env 자동 생성 → 포트 정리 → 빌드·실행 → 약 데이터 seed → 테스트 계정 생성 → 접속 주소 출력**까지 다 됩니다.
> 처음 한 번은 빌드하느라 몇 분 걸려요.

실행 끝나면:
- 보호자 앱: http://localhost:5173  (`guardian_test` / `Test1234!`)
- 수의사 앱: http://localhost:5174  (`admin` / `Test1234!`)
- API 문서: http://localhost:8000/docs

기타 명령:
```bash
# 맥/리눅스
./dev.sh down     # 전부 끄기
./dev.sh reset    # DB까지 싹 지우고 새로 시작 (꼬였을 때)
# 윈도우
.\dev.ps1 down
.\dev.ps1 reset
```

### ☀️ 다음 날 작업 시작 (매일 루틴)
1. **Docker Desktop 켜기** 🐳 (초록불 될 때까지)
2. 최신 코드 받기: `git pull`
3. 실행: 맥/리눅스 `./dev.sh` · 윈도우 `.\dev.ps1`

> 컴퓨터 껐다 켜도 **DB 데이터(계정·약·기록)는 안 사라져요.** `dev.sh`/`dev.ps1`는 몇 번 돌려도 안전(이미 있으면 건너뜀).
> EC2(인터넷 서버)는 24시간 따로 돌아가니 매일 손댈 필요 없어요.

> 💡 `OPENAI_API_KEY` 가 비어 있으면 서버는 뜨지만 AI 기능(트리아지/처방전 추천)만 안 돼요.
> `backend/.env` 열어서 팀 공용 키를 채우면 됩니다. (이 파일은 git에 안 올라감)

---

## AI(Claude/Codex)한테 시킬 거면 — 이 프롬프트 붙여넣기

```
이 레포 루트에서 ./dev.sh 를 실행해서 MediPaw 개발 스택을 띄워줘.
- 실행 중 에러가 나면 멈추지 말고 로그를 보여주고 원인을 설명해줘.
- 다 뜨면 docker compose -f ai/docker/docker-compose.yml ps 로 db/backend/guardian/vet 가
  전부 Up 인지 확인하고(migrate는 Exited(0)이면 정상), 접속 주소를 알려줘.
- 수의사(5174) 화면이 안 뜨면 vet 컨테이너 로그를 확인하고 필요하면 vet만 재빌드해줘.
```

---

## 직접(수동) 켜고 싶으면

```bash
# 1) 처음 한 번 (없을 때만)
cp backend/.env.example backend/.env      # 그리고 OPENAI_API_KEY 채우기

# 2) 실행 (레포 루트에서!)
docker compose -f ai/docker/docker-compose.yml up --build -d
```
> ⚠️ `git pull` 로 코드 받은 뒤엔 **반드시 `--build`** 붙이기. 안 그러면 옛 화면이 떠요.

---

## "수의사(vet) 화면이 안 켜져요" — 가장 흔한 증상

원인 1순위: 누가 host에서 `npm run dev`로 vite를 띄워놔서 그게 5174를 가로채는 것.
(`./dev.sh` 는 이 stray 프로세스를 자동으로 정리하므로 보통 안 생겨요.)

직접 확인/정리:
```bash
lsof -nP -iTCP:5174 -sTCP:LISTEN     # 도커 아닌 node/vite가 보이면
kill -9 <PID>                         # 그 PID 종료
docker compose -f ai/docker/docker-compose.yml up -d --build vet
```

처방전 약 검색이 비어 있으면 → 약 데이터 seed가 안 된 것. `./dev.sh` 가 자동으로 하지만 수동은:
```bash
docker compose -f ai/docker/docker-compose.yml exec backend bash -c "cd /app/backend && python scripts/seed_drugs.py"
```

---

## 안 될 때 팀에 공유할 진단 결과

```bash
docker compose -f ai/docker/docker-compose.yml ps
docker compose -f ai/docker/docker-compose.yml logs backend | tail -40
```
backend 로그에 환경변수 관련 에러가 보이면 `backend/.env` 문제예요.

---

## 팀 규칙 (도커/compose 건드릴 때)

- compose·Dockerfile·포트를 바꾸는 작업은 **별도 브랜치에서**, 끝나기 전엔 남들이 그 브랜치로 안 갈아타기.
- 도커 관련을 바꿨으면 PR 설명에 **"도커 변경됨 / .env에 OO 추가 필요"** 꼭 적기.
- `backend/.env` 는 절대 git에 올리지 않기 (이미 .gitignore에 있음).
