# =====================================================================
# Booth 一鍵啟動 — 自動帶好 Vertex AI 認證(服務帳戶 JSON)後啟動 booth server
# =====================================================================
#
#   .\run_booth.ps1              # 開發,預設 8800
#   .\run_booth.ps1 -Port 8501   # 對外正式(公開連結)
#   .\run_booth.ps1 -Port 8501 -Model gemini-2.5-pro   # 換模型
#
# 認證:自動在專案根目錄找「service_account 類型的 *.json」,設定
#       GCP_PROJECT_ID + GCP_CREDENTIALS_FILE(Vertex AI)。
#       → 換電腦(同事備援)只要把那個 JSON 放進專案根目錄即可,不必手動設環境變數。
#
# 會先清掉「目前佔用該 Port 的舊 process」再啟動(所以這也是安全的『重啟』指令)。
# =====================================================================

param(
    [int]$Port = 8800,
    [string]$Model = "gemini-3.5-flash"
)

$ErrorActionPreference = 'Stop'
$RepoRoot = $PSScriptRoot
Set-Location $RepoRoot

# 1) 找服務帳戶 JSON,取出 project_id
$cred = $null
$projectId = $null
foreach ($f in (Get-ChildItem -Path $RepoRoot -Filter *.json -File)) {
    try {
        $j = Get-Content -LiteralPath $f.FullName -Raw | ConvertFrom-Json
        if ($j.type -eq 'service_account' -and $j.project_id) {
            $cred = $f.FullName; $projectId = $j.project_id; break
        }
    } catch { }
}
if (-not $cred) {
    Write-Host "[!] 找不到服務帳戶 JSON(type=service_account)。請把 Vertex AI 金鑰 JSON 放到專案根目錄:" -ForegroundColor Red
    Write-Host "    $RepoRoot" -ForegroundColor DarkYellow
    exit 1
}

# 2) 設定 Vertex AI 認證 + 埠口 + 模型
$env:GCP_PROJECT_ID = $projectId
$env:GCP_CREDENTIALS_FILE = $cred
$env:BOOTH_PORT = "$Port"
$env:BOOTH_MODEL = $Model

Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host " Booth server" -ForegroundColor Cyan
Write-Host "   project : $projectId"
Write-Host "   creds   : $(Split-Path -Leaf $cred)"
Write-Host "   port    : $Port    model: $Model"
Write-Host "==============================================================" -ForegroundColor Cyan

# 3) 清掉佔用該 Port 的舊 process(安全重啟)
try {
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        Write-Host "[i] 停掉舊 process (PID $($c.OwningProcess)) on port $Port" -ForegroundColor DarkYellow
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
    }
    if ($conns) { Start-Sleep -Milliseconds 800 }
} catch { }

# 4) 啟動
python booth/server.py
