#!/usr/bin/env bash
# MediPaw 로컬 개발 환경 한 방 실행기
# 사용법:  ./dev.sh          (전체 빌드 후 실행: 처음 켤 때/의존성 바뀐 뒤)
#          ./dev.sh fast     (재빌드 없이 전체 스택 빠르게 실행: 평소 재시작용)
#          ./dev.sh guardian (보호자 앱만 다시 빌드/재시작: guardian 프론트 수정 뒤)
#          ./dev.sh vet      (수의사 앱만 다시 빌드/재시작: vet 프론트 수정 뒤)
#          ./dev.sh company  (회사 소개 사이트만 다시 빌드/재시작: company 프론트 수정 뒤)
#          ./dev.sh down     (전부 끄기)
#          ./dev.sh reset    (DB 볼륨까지 삭제하고 새로 시작)
#
# 하는 일: .env 자동 준비 → 포트 충돌(stray vite) 정리 → 빌드+실행
#          → 약 데이터 seed(비어있을 때만) → 테스트 계정 생성 → 접속 주소 출력

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE="docker compose -f ai/docker/docker-compose.yml"
MODE="${1:-up}"
BUILD_ARGS=(--build)
RUN_SETUP=true

# ── 서브 명령 ──────────────────────────────────────────────
case "$MODE" in
  help|-h|--help)
    cat <<EOF
MediPaw dev runner

Usage:
  ./dev.sh          전체 빌드 후 실행. 처음 켤 때, Dockerfile/requirements/package 변경 뒤 사용.
  ./dev.sh fast     재빌드 없이 전체 스택 실행. Docker 껐다 켠 뒤 평소 확인할 때 사용.
                   대상: DB + backend + guardian(5173) + vet(5174) + company(5175)
  ./dev.sh guardian 보호자 앱만 다시 빌드/재시작. guardian 프론트 수정 뒤 사용.
  ./dev.sh vet      수의사 앱만 다시 빌드/재시작. vet 프론트 수정 뒤 사용.
  ./dev.sh company  회사 소개 사이트만 다시 빌드/재시작. company 프론트 수정 뒤 사용.
  ./dev.sh down     컨테이너 종료. DB 데이터는 유지.
  ./dev.sh reset    컨테이너와 DB 볼륨 삭제. 계정/예약/seed 데이터도 삭제됨.

Rule of thumb:
  - 그냥 다시 켤 때: ./dev.sh fast
  - 코드/의존성 크게 바뀐 뒤: ./dev.sh
  - 보호자 화면만 바꾼 뒤: ./dev.sh guardian
  - 수의사 화면만 바꾼 뒤: ./dev.sh vet
  - 회사 소개 화면만 바꾼 뒤: ./dev.sh company
EOF
    exit 0
    ;;
  down)  echo "▶ 컨테이너 종료"; $COMPOSE down; exit 0 ;;
  reset) echo "▶ 컨테이너 + DB 볼륨까지 삭제"; $COMPOSE down -v ;;
  fast)
    BUILD_ARGS=()
    RUN_SETUP=false
    ;;
  guardian)
    echo "▶ 보호자 앱만 빌드 & 재시작"
    $COMPOSE build guardian
    $COMPOSE up -d guardian
    cat <<EOF

✅ 보호자 앱 재시작 완료!
  보호자 앱 : http://localhost:5173
EOF
    exit 0
    ;;
  vet)
    echo "▶ 수의사 앱만 빌드 & 재시작"
    $COMPOSE build vet
    $COMPOSE up -d vet
    cat <<EOF

✅ 수의사 앱 재시작 완료!
  수의사 앱 : http://localhost:5174
EOF
    exit 0
    ;;
  company)
    echo "▶ 회사 소개 사이트만 빌드 & 재시작"
    $COMPOSE build company
    $COMPOSE up -d company
    cat <<EOF

✅ 회사 소개 사이트 재시작 완료!
  회사 소개 : http://localhost:5175
EOF
    exit 0
    ;;
esac

# ── 1) backend/.env 준비 ──────────────────────────────────
if [ ! -f backend/.env ]; then
  echo "▶ backend/.env 가 없어서 .env.example 로 생성합니다."
  cp backend/.env.example backend/.env
fi
if ! grep -q '^OPENAI_API_KEY=.\+' backend/.env 2>/dev/null; then
  echo "  ⚠️  backend/.env 의 OPENAI_API_KEY 가 비어있어요."
  echo "     AI 기능(트리아지/처방전 추천)을 쓰려면 팀 공용 키를 채우세요."
  echo "     (지금은 키 없이도 서버는 뜹니다 — UI 개발은 가능)"
fi

# ── 2) 포트 충돌(도커 아닌 stray 프로세스) 정리 ─────────────
echo "▶ 포트 5173/5174/5175/8000 점검 (stray vite/uvicorn 정리)"
for port in 5173 5174 5175 8000; do
  for pid in $(lsof -nP -iTCP:$port -sTCP:LISTEN -t 2>/dev/null); do
    cmd=$(ps -p "$pid" -o comm= 2>/dev/null)
    case "$cmd" in
      *docker*|*Docker*|*com.docke*|*vpnkit*) ;;  # 도커가 잡은 포트는 건드리지 않음
      *) echo "  - 포트 $port 의 stray '$cmd'(pid $pid) 종료"; kill -9 "$pid" 2>/dev/null ;;
    esac
  done
done

# ── 3) 빌드 + 실행 ────────────────────────────────────────
if [ "$MODE" = "fast" ]; then
  echo "▶ 빠른 실행 (재빌드 없이 기존 이미지 사용)"
else
  echo "▶ 빌드 & 실행 (처음엔 몇 분 걸려요)"
fi
$COMPOSE up "${BUILD_ARGS[@]}" -d

# ── 4) backend 가 뜰 때까지 대기 ───────────────────────────
echo -n "▶ backend 기동 대기"
for i in $(seq 1 60); do
  if curl -fs http://localhost:8000/docs >/dev/null 2>&1; then echo " ✓"; break; fi
  echo -n "."; sleep 2
done

# ── 4.5) DB 마이그레이션 + 운영자 계정 ─────────────────────
echo "▶ DB 마이그레이션 적용"
if ! $COMPOSE run --rm migrate; then
  echo "  ❌ 마이그레이션 실패. 로그를 확인해 주세요."
  exit 1
fi

echo "▶ 운영자 계정 확인/생성"
$COMPOSE exec -T backend bash -c "cd /app/backend && python scripts/seed_admin.py" 2>/dev/null || true

# ── 5) 약 데이터 seed (drugsDB 비어있을 때만 — 중복 방지) ───
if [ "$RUN_SETUP" = false ]; then
  echo "▶ seed/RAG/테스트 계정 확인 건너뜀 (fast 모드)"
  cat <<EOF

✅ 빠른 실행 완료!
  보호자 앱 : http://localhost:5173   (guardian_test / Test1234!)
  수의사 앱 : http://localhost:5174   (admin / Test1234!)
  회사 소개 : http://localhost:5175
  API 문서  : http://localhost:8000/docs

  전체 재빌드:  ./dev.sh
  보호자만:    ./dev.sh guardian
  수의사만:    ./dev.sh vet
  회사 소개만:  ./dev.sh company
  끄기:        ./dev.sh down
EOF
  exit 0
fi

# ── 5) 약 데이터 seed (drugsDB 비어있을 때만 — 중복 방지) ───
echo "▶ 약 데이터 확인/seed"
DRUGCOUNT=$($COMPOSE exec -T db psql -U medipaw -d medipaw -tAc 'SELECT count(*) FROM "drugsDB"' 2>/dev/null | tr -d '[:space:]')
if [ -z "${DRUGCOUNT}" ]; then
  $COMPOSE run --rm migrate >/dev/null 2>&1 || true
  DRUGCOUNT=$($COMPOSE exec -T db psql -U medipaw -d medipaw -tAc 'SELECT count(*) FROM "drugsDB"' 2>/dev/null | tr -d '[:space:]')
fi
if [ "${DRUGCOUNT:-0}" = "0" ]; then
  echo "  - 비어있음 → seed_drugs 실행"
  $COMPOSE exec -T backend bash -c "cd /app/backend && python scripts/seed_drugs.py" || true
else
  echo "  - 이미 ${DRUGCOUNT}개 있음 → 건너뜀"
fi

# ── 5.5) Triage RAG 적재 (덤프 있으면 비어있을 때만 — 중복/임베딩비용 방지) ───
echo "▶ Triage RAG 확인/적재"
$COMPOSE exec -T backend bash -c "cd /app/backend && python scripts/load_triage_rag.py" || true

# ── 6) 테스트 계정 생성 (있으면 그대로) ────────────────────
echo "▶ 테스트 계정 확인/생성"
$COMPOSE exec -T backend bash -c "cd /app/backend && python scripts/create_test_accounts.py" 2>/dev/null || true

# ── 완료 ──────────────────────────────────────────────────
cat <<EOF

✅ 준비 끝!
  보호자 앱 : http://localhost:5173   (guardian_test / Test1234!)
  수의사 앱 : http://localhost:5174   (admin / Test1234!)
  회사 소개 : http://localhost:5175
  API 문서  : http://localhost:8000/docs

  끄기:        ./dev.sh down
  초기화:      ./dev.sh reset   (DB 데이터 삭제 후 재시작)
EOF
