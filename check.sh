#!/usr/bin/env bash
# MediPaw 메인 받아온 뒤 "뭐 깨졌나?" 한 방 점검기
#
# 사용법:
#   ./check.sh              빠른 점검 (git 변경요약 + 파괴적 마이그레이션 스캔 +
#                           alembic head/드리프트 + backend import/문법)
#   ./check.sh deep         위 + 임시 DB에 마이그레이션 전체 적용(fresh 깨짐 감지)
#                           + 프론트 3종 타입체크(tsc)
#   ./check.sh install-hook git pull 할 때마다 빠른 점검이 자동으로 돌게 설치
#
# 컨테이너가 필요한 점검은 dev 스택(./dev.sh)이 떠 있을 때만 돌고, 안 떠 있으면
# 건너뛰며 안내합니다. 정적 점검(git/파괴적 스캔)은 항상 돕니다.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE="docker compose -f ai/docker/docker-compose.yml"
MODE="${1:-fast}"

# ── 색/카운터 ──────────────────────────────────────────────
RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; BLU=$'\033[34m'; DIM=$'\033[2m'; RST=$'\033[0m'
FAILS=0; WARNS=0
ok()   { echo "  ${GRN}✓${RST} $*"; }
warn() { echo "  ${YEL}⚠ $*${RST}"; WARNS=$((WARNS+1)); }
bad()  { echo "  ${RED}✗ $*${RST}"; FAILS=$((FAILS+1)); }
hdr()  { echo; echo "${BLU}▶ $*${RST}"; }

# ── 0) 훅 설치 ─────────────────────────────────────────────
if [ "$MODE" = "install-hook" ]; then
  HOOK=.git/hooks/post-merge
  cat > "$HOOK" <<'EOF'
#!/usr/bin/env bash
# git pull/merge 직후 자동 실행 — 빠른 정적 점검만 (느린 건 ./check.sh deep)
exec "$(git rev-parse --show-toplevel)/check.sh" --post-merge
EOF
  chmod +x "$HOOK"
  echo "${GRN}✓ 설치 완료${RST}: 이제 git pull/merge 할 때마다 빠른 점검이 자동으로 돕니다."
  echo "  (느린 정밀 점검은 직접: ./check.sh deep)"
  exit 0
fi

POST_MERGE=false
[ "$MODE" = "--post-merge" ] && { POST_MERGE=true; MODE="fast"; }

echo "${BLU}════════ MediPaw 점검 ($MODE) ════════${RST}"

# ── 1) 이번에 뭐가 바뀌었나 (특히 삭제) ────────────────────
hdr "이번 변경 요약 (이전 → 지금)"
BASE=""
if git rev-parse --verify -q ORIG_HEAD >/dev/null; then BASE=ORIG_HEAD
elif git rev-parse --verify -q "@{1}" >/dev/null; then BASE="@{1}"; fi
if [ -z "$BASE" ]; then
  echo "  ${DIM}비교 기준(ORIG_HEAD)이 없어 변경 요약은 건너뜁니다.${RST}"
else
  DELETED=$(git diff --diff-filter=D --name-only "$BASE" HEAD 2>/dev/null)
  if [ -n "$DELETED" ]; then
    warn "삭제된 파일 $(echo "$DELETED" | wc -l | tr -d ' ')개 — 확인 필요:"
    echo "$DELETED" | sed 's/^/      🗑  /'
  else
    ok "삭제된 파일 없음"
  fi
  MIGCHG=$(git diff --name-only "$BASE" HEAD -- backend/migrations/versions 2>/dev/null)
  MODELCHG=$(git diff --name-only "$BASE" HEAD -- backend/app/models 2>/dev/null)
  [ -n "$MIGCHG" ]   && echo "  ${DIM}• 마이그레이션 변경:${RST}" && echo "$MIGCHG" | sed 's/^/      /'
  [ -n "$MODELCHG" ] && echo "  ${DIM}• 모델 변경:${RST}"       && echo "$MODELCHG" | sed 's/^/      /'
  [ -z "$MIGCHG$MODELCHG" ] && ok "DB 스키마(모델/마이그레이션) 변경 없음"
fi

# ── 2) 파괴적 마이그레이션 스캔 (데이터 날아갈 수 있는 것) ──
# downgrade()의 DROP은 정상이므로 upgrade() 본문만 검사한다. (.pyc 제외)
# 평소엔 조용히: "이번 pull로 추가/변경된" 마이그레이션의 파괴적 작업만 크게 경고하고,
# 기존(이미 적용된) 것은 개수만 알려준다.
hdr "파괴적 마이그레이션 스캔 (upgrade()의 DROP / CASCADE)"
TOTAL_DEST=0; NEW_DEST=0
for f in $(find backend/migrations/versions -name '*.py' ! -path '*__pycache__*' 2>/dev/null | sort); do
  HITS=$(awk '/^def upgrade/{u=1} /^def downgrade/{u=0} u' "$f" \
         | grep -niE "drop[_ ]table|drop[_ ]column|cascade|op\.drop_")
  [ -z "$HITS" ] && continue
  TOTAL_DEST=$((TOTAL_DEST+1))
  CHANGED=false
  if [ -n "$BASE" ] && git diff --name-only "$BASE" HEAD -- "$f" 2>/dev/null | grep -q .; then CHANGED=true; fi
  if [ -z "$BASE" ] || [ "$CHANGED" = true ]; then
    NEW_DEST=$((NEW_DEST+1))
    MARK=""; [ "$CHANGED" = true ] && MARK=" ${RED}[이번 pull로 추가/변경!]${RST}"
    warn "${f#backend/migrations/versions/}$MARK — 적용 시 데이터 삭제 가능:"
    echo "$HITS" | sed 's/^/          /'
  fi
done
if [ "$TOTAL_DEST" = 0 ]; then
  ok "upgrade()에 파괴적 작업 없음"
elif [ "$NEW_DEST" = 0 ]; then
  ok "이번 pull로 추가된 파괴적 마이그레이션 없음 (${DIM}기존 ${TOTAL_DEST}개는 이미 적용됨${RST})"
fi

# ── 컨테이너 필요 여부 판단 ────────────────────────────────
BCID=$($COMPOSE ps -q backend 2>/dev/null)
BACKEND_UP=false
if [ -n "$BCID" ] && [ "$(docker inspect -f '{{.State.Running}}' "$BCID" 2>/dev/null)" = "true" ]; then
  BACKEND_UP=true
fi

run_container_checks() {
  # ── 3) alembic head 1개인지 (브랜치 충돌 감지) ──────────
  hdr "마이그레이션 head 점검"
  HEADS=$($COMPOSE exec -T backend bash -c "cd /app/backend && alembic heads 2>/dev/null" | grep -c "(head)")
  if [ "$HEADS" = "1" ]; then ok "head 1개 (정상)"
  elif [ "$HEADS" = "0" ]; then bad "head를 못 읽음 (alembic 설정/DB 확인)"
  else bad "head가 ${HEADS}개! 마이그레이션이 갈라졌습니다 (merge 필요)"; fi

  # ── 4) DB가 head까지 적용됐는지 (마이그레이션 누락 감지) ─
  # (alembic check 드리프트는 raw SQL/pgvector 때문에 오탐이 심해 쓰지 않음.
  #  대신 "지금 DB가 최신 마이그레이션까지 올라갔나"만 확실히 본다.)
  hdr "현재 DB가 최신 마이그레이션(head)까지 적용됐는지"
  CUR=$($COMPOSE exec -T backend bash -c "cd /app/backend && alembic current 2>/dev/null" | grep -oE "^[0-9a-z_]+" | head -1)
  HEAD1=$($COMPOSE exec -T backend bash -c "cd /app/backend && alembic heads 2>/dev/null" | grep -oE "^[0-9a-z_]+" | head -1)
  if [ -z "$CUR" ]; then
    warn "DB에 적용된 마이그레이션이 없음(빈 DB?) → ./dev.sh 로 적용 필요"
  elif [ "$CUR" = "$HEAD1" ]; then
    ok "DB가 head($HEAD1)까지 적용됨"
  else
    warn "DB($CUR)가 head($HEAD1)보다 뒤처짐 → ./dev.sh (migrate) 로 새 마이그레이션 적용 필요"
  fi

  # ── 5) 백엔드 import/문법 ───────────────────────────────
  hdr "백엔드 로드 점검 (문법 + import)"
  if $COMPOSE exec -T backend bash -c "cd /app/backend && python -m compileall -q app && python -c 'import app.main'" 2>/tmp/medipaw_imp.err; then
    ok "app.main import 성공 (문법/import 정상)"
  else
    bad "백엔드 로드 실패:"; sed 's/^/      /' /tmp/medipaw_imp.err | tail -15
  fi
}

if [ "$BACKEND_UP" = true ]; then
  run_container_checks
else
  hdr "컨테이너 점검 (건너뜀)"
  warn "dev 스택이 안 떠 있어 alembic/import 점검을 건너뜁니다."
  echo "      먼저: ${DIM}./dev.sh fast${RST} 로 켠 뒤 다시 ${DIM}./check.sh${RST}"
fi

# ── 6) deep: 임시 DB 마이그레이션 + 프론트 타입체크 ────────
if [ "$MODE" = "deep" ]; then
  if [ "$BACKEND_UP" = true ]; then
    hdr "임시 DB에 마이그레이션 전체 적용 (fresh 셋업 깨짐 감지)"
    TMPDB="checktmp_$$"
    $COMPOSE exec -T db psql -U medipaw -d medipaw -c "DROP DATABASE IF EXISTS \"$TMPDB\";" >/dev/null 2>&1
    if $COMPOSE exec -T db psql -U medipaw -d medipaw -c "CREATE DATABASE \"$TMPDB\";" >/dev/null 2>&1; then
      URL="postgresql://medipaw:${POSTGRES_PASSWORD:-medipaw_secret}@db:5432/$TMPDB"
      if $COMPOSE run --rm -e DATABASE_URL="$URL" migrate >/tmp/medipaw_mig.log 2>&1; then
        ok "빈 DB에서 마이그레이션 head까지 정상 적용 (fresh 셋업 OK)"
      else
        bad "빈 DB 마이그레이션 실패 (새 환경/팀원 셋업이 깨짐):"; tail -20 /tmp/medipaw_mig.log | sed 's/^/      /'
      fi
      $COMPOSE exec -T db psql -U medipaw -d medipaw -c "DROP DATABASE IF EXISTS \"$TMPDB\";" >/dev/null 2>&1
    else
      warn "임시 DB 생성 실패 — 건너뜀"
    fi
  else
    warn "deep DB 점검은 dev 스택이 떠 있어야 합니다 (./dev.sh fast)"
  fi

  # ── 프론트 API 경로 ↔ 백엔드 라우트 일치 (best-effort) ───
  # 프론트가 부르는 경로가 백엔드에 실제로 있는지 검사(없으면 404 — reset-password 사례).
  # 정답지는 백엔드 /openapi.json. 동적/외부 URL은 검사 못 하므로 best-effort 경고.
  if [ "$BACKEND_UP" = true ]; then
    hdr "프론트 API 경로 ↔ 백엔드 라우트 일치 (best-effort)"
    if curl -fs http://localhost:8000/openapi.json -o /tmp/medipaw_openapi.json 2>/dev/null; then
      cat > /tmp/medipaw_apicheck.py <<'PYEOF'
import json, re, sys, os
spec = json.load(open(sys.argv[1]))
backend = [[s for s in p.split("?")[0].strip("/").split("/") if s] for p in spec.get("paths", {})]
IGNORE = ("/uploads",)  # 정적 서빙(라우트 아님)
def isparam(s): return s.startswith("{") or "${" in s
def matches(fp):
    fs = [s for s in fp.strip("/").split("/") if s]
    if not fs: return False
    for bs in backend:
        if len(bs) != len(fs): continue
        if all(isparam(a) or isparam(b) or a == b for a, b in zip(fs, bs)): return True
    return False
def norm(r):
    r = r.split("?")[0].split("#")[0]
    return r[4:] if r.startswith("/api/") else r
STR = r'["\'`]([^"\'`]*)["\'`]'
api_re = re.compile(r'apiClient\.(?:get|post|put|delete|patch)\b[^()]*?\(\s*' + STR, re.S)
fetch_re = re.compile(r'fetch\(\s*[`"\']\s*(?:\$\{API\})?([^`"\']*)', re.S)
found = {}
for d in sys.argv[2:]:
    for root, _, files in os.walk(d):
        if "node_modules" in root: continue
        for fn in files:
            if not fn.endswith((".ts", ".tsx")): continue
            fp = os.path.join(root, fn)
            try: txt = open(fp, encoding="utf-8").read()
            except Exception: continue
            for m in list(api_re.finditer(txt)) + list(fetch_re.finditer(txt)):
                found.setdefault(m.group(1), fp)
chk = 0; mism = []
for raw, fp in sorted(found.items()):
    p = norm(raw)
    if not p.startswith("/") or p.startswith("//") or p == "/": continue
    if any(p == ig or p.startswith(ig + "/") for ig in IGNORE): continue
    chk += 1
    if not matches(p): mism.append((p, fp))
for p, fp in mism: print("MISMATCH\t%s\t%s" % (p, fp))
print("RESULT\t%d\t%d" % (len(mism), chk))
PYEOF
      OUT=$(python3 /tmp/medipaw_apicheck.py /tmp/medipaw_openapi.json \
            frontend/guardian-web/src frontend/vet-web/src frontend/company-web/src 2>/dev/null)
      MIS=$(printf '%s\n' "$OUT" | grep -c '^MISMATCH')
      CHK=$(printf '%s\n' "$OUT" | awk -F'\t' '/^RESULT/{print $3}')
      if [ "${MIS:-0}" = "0" ]; then
        ok "프론트 호출 ${CHK:-0}개 경로 전부 백엔드 라우트와 일치"
      else
        warn "백엔드에 없는 프론트 호출 ${MIS}개 (404 위험 — 오타/삭제된 라우트?):"
        printf '%s\n' "$OUT" | awk -F'\t' '/^MISMATCH/{print "      ✗ "$2"   ("$3")"}'
        echo "      ${DIM}* best-effort: 정적 경로만, 동적/외부 URL 제외 — 오탐이면 무시${RST}"
      fi
    else
      warn "openapi.json을 못 받아 API 계약 검사 건너뜀 (backend 확인)"
    fi
  fi

  # ── 프론트 실제 빌드 (tsc + vite build) — 타입오류 + 번들 에러 ──
  hdr "프론트 실제 빌드 (npm run build = tsc + vite) — 타입+번들 에러"
  for app in guardian-web vet-web company-web; do
    DIR="frontend/$app"
    [ -d "$DIR/node_modules" ] || { warn "$app: node_modules 없음 → (cd $DIR && npm i) 후 재시도"; continue; }
    if (cd "$DIR" && npm run build >/tmp/medipaw_build.log 2>&1); then
      ok "$app 빌드 성공"
    else
      bad "$app 빌드 실패:"; tail -15 /tmp/medipaw_build.log | sed 's/^/      /'
    fi
  done
fi

# ── 결과 ──────────────────────────────────────────────────
echo
echo "${BLU}════════ 결과 ════════${RST}"
if [ "$FAILS" -gt 0 ]; then
  echo "${RED}✗ 문제 ${FAILS}건, 주의 ${WARNS}건 — 위 ✗ 항목을 먼저 보세요.${RST}"
  exit 1
elif [ "$WARNS" -gt 0 ]; then
  echo "${YEL}⚠ 치명적 문제는 없음. 주의 ${WARNS}건 — 삭제/파괴적 마이그레이션만 확인하세요.${RST}"
  [ "$POST_MERGE" = true ] && echo "${DIM}  정밀 점검: ./check.sh deep${RST}"
  exit 0
else
  echo "${GRN}✓ 전부 통과! 안심하고 작업하세요.${RST}"
  [ "$MODE" = "fast" ] && echo "${DIM}  더 깊게: ./check.sh deep (임시DB 마이그레이션 + API계약 + 프론트 실제빌드)${RST}"
  exit 0
fi
