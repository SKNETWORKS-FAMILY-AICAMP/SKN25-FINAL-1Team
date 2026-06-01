# MediPaw 로컬 개발 환경 한 방 실행기 (Windows / PowerShell)
# 사용법 (레포 루트에서):
#   .\dev.ps1            실행
#   .\dev.ps1 down       전부 끄기
#   .\dev.ps1 reset      DB까지 싹 지우고 새로 시작
#
# 실행이 막히면(빨간 글씨) 한 번만:
#   powershell -ExecutionPolicy Bypass -File .\dev.ps1
#
# 하는 일: .env 자동 준비 -> 포트(stray vite) 정리 -> 빌드+실행
#          -> 약 데이터 seed(비어있을 때만) -> 테스트 계정 생성 -> 접속 주소 출력

param([string]$cmd = "up")

$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
Set-Location $PSScriptRoot
$COMPOSE = @("compose", "-f", "ai/docker/docker-compose.yml")

function Compose { docker @COMPOSE @args }

# --- 서브 명령 ---
if ($cmd -eq "down")  { Write-Host "▶ 컨테이너 종료"; Compose down; exit }
if ($cmd -eq "reset") { Write-Host "▶ 컨테이너 + DB 볼륨 삭제"; Compose down -v }

# --- 1) backend/.env 준비 ---
if (-not (Test-Path "backend/.env")) {
    Write-Host "▶ backend/.env 가 없어서 .env.example 로 생성합니다."
    Copy-Item "backend/.env.example" "backend/.env"
}
if (-not (Select-String -Path "backend/.env" -Pattern '^OPENAI_API_KEY=.+' -Quiet)) {
    Write-Host "  ⚠️  backend/.env 의 OPENAI_API_KEY 가 비어있어요." -ForegroundColor Yellow
    Write-Host "     AI 기능을 쓰려면 팀 공용 키를 채우세요. (없어도 서버는 뜸 - UI 개발 가능)"
}

# --- 2) 포트 충돌(도커 아닌 stray 프로세스) 정리 ---
Write-Host "▶ 포트 5173/5174/8000 점검 (stray vite/node 정리)"
foreach ($port in 5173,5174,8000) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        $p = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
        if ($p -and $p.ProcessName -notmatch 'docker|vpnkit|com\.docke') {
            Write-Host "  - 포트 $port 의 stray '$($p.ProcessName)'(pid $($p.Id)) 종료"
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

# --- 3) 빌드 + 실행 ---
Write-Host "▶ 빌드 & 실행 (처음엔 몇 분 걸려요)"
Compose up --build -d

# --- 4) backend 기동 대기 ---
Write-Host -NoNewline "▶ backend 기동 대기"
for ($i=0; $i -lt 60; $i++) {
    try { Invoke-WebRequest -UseBasicParsing "http://localhost:8000/docs" -TimeoutSec 3 | Out-Null; Write-Host " ✓"; break }
    catch { Write-Host -NoNewline "."; Start-Sleep -Seconds 2 }
}

# --- 5) 약 데이터 seed (비어있을 때만) ---
Write-Host "▶ 약 데이터 확인/seed"
$drugCount = (Compose exec -T db psql -U medipaw -d medipaw -tAc 'SELECT count(*) FROM "drugsDB"' 2>$null | Out-String).Trim()
if ([string]::IsNullOrWhiteSpace($drugCount)) {
    Compose run --rm migrate *> $null
    $drugCount = (Compose exec -T db psql -U medipaw -d medipaw -tAc 'SELECT count(*) FROM "drugsDB"' 2>$null | Out-String).Trim()
}
if ($drugCount -eq "0" -or [string]::IsNullOrWhiteSpace($drugCount)) {
    Write-Host "  - 비어있음 → seed_drugs 실행"
    Compose exec -T backend bash -c "cd /app/backend && python scripts/seed_drugs.py"
} else {
    Write-Host "  - 이미 $drugCount 개 있음 → 건너뜀"
}

# --- 6) 테스트 계정 생성 ---
Write-Host "▶ 테스트 계정 확인/생성"
Compose exec -T backend bash -c "cd /app/backend && python scripts/create_test_accounts.py" 2>$null

# --- 완료 ---
Write-Host ""
Write-Host "✅ 준비 끝!" -ForegroundColor Green
Write-Host "  보호자 앱 : http://localhost:5173   (guardian_test / Test1234!)"
Write-Host "  수의사 앱 : http://localhost:5174   (admin / Test1234!)"
Write-Host "  API 문서  : http://localhost:8000/docs"
Write-Host ""
Write-Host "  끄기:    .\dev.ps1 down"
Write-Host "  초기화:  .\dev.ps1 reset"
