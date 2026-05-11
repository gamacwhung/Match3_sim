# =====================================================================
# Match3 Demo 一鍵啟動腳本
# =====================================================================
#
# 用法:
#   .\start_demo.ps1                  # 起 Streamlit (8501) + Godot HTTP server (8765)
#   .\start_demo.ps1 -StreamlitOnly   # 只起 Streamlit
#   .\start_demo.ps1 -GodotOnly       # 只起 Godot HTTP server
#   .\start_demo.ps1 -Stop            # 把所有先前啟動的 server 殺掉
#
# 前置(都做過一次以後可以跳過):
#   1. pip install -r requirements.txt
#   2. Godot Editor 開 godot_demo/ → Export → Web → 輸出到 godot_demo/web/
#      (沒做這步就用 -StreamlitOnly,Demo 時 Godot 直接用 Editor 跑)
#
# Demo 時 3 個瀏覽器 tab:
#   - http://localhost:8501/           Streamlit 主頁
#   - http://localhost:8501/AI_Auto_Test  AI 自動測試頁
#   - http://localhost:8765/           Godot 美術版
# =====================================================================

param(
    [switch]$StreamlitOnly,
    [switch]$GodotOnly,
    [switch]$Stop,
    [int]$StreamlitPort = 8501,
    [int]$GodotPort = 8765
)

$ErrorActionPreference = 'Stop'
$RepoRoot = $PSScriptRoot
$LogDir = Join-Path $RepoRoot ".demo_logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

# === Stop 模式:把 .demo_logs/*.pid 內的 PID 都殺掉 ===
if ($Stop) {
    Write-Host "Stopping all demo servers..." -ForegroundColor Yellow
    Get-ChildItem "$LogDir\*.pid" -ErrorAction SilentlyContinue | ForEach-Object {
        $procPid = Get-Content $_.FullName -ErrorAction SilentlyContinue
        if ($procPid) {
            try {
                Stop-Process -Id $procPid -Force -ErrorAction SilentlyContinue
                Write-Host "  Killed PID $procPid ($($_.BaseName))" -ForegroundColor Green
            } catch {
                Write-Host "  PID $procPid not running" -ForegroundColor DarkGray
            }
        }
        Remove-Item $_.FullName -Force
    }
    exit 0
}

# === Helper:啟動 background process + 記 PID ===
function Start-DemoServer {
    param(
        [string]$Name,
        [string]$Cmd,
        [string]$Arguments,
        [string]$WorkingDir,
        [int]$Port
    )
    $logFile = Join-Path $LogDir "$Name.log"
    $pidFile = Join-Path $LogDir "$Name.pid"

    # 殺舊的(避免 port conflict)
    if (Test-Path $pidFile) {
        $oldProcPid = Get-Content $pidFile -ErrorAction SilentlyContinue
        if ($oldProcPid) {
            try { Stop-Process -Id $oldProcPid -Force -ErrorAction SilentlyContinue } catch {}
        }
    }

    Write-Host "Starting $Name on port $Port..." -ForegroundColor Cyan
    $proc = Start-Process -FilePath $Cmd -ArgumentList $Arguments `
        -WorkingDirectory $WorkingDir `
        -RedirectStandardOutput $logFile `
        -RedirectStandardError "$logFile.err" `
        -PassThru -WindowStyle Hidden
    $proc.Id | Out-File $pidFile -NoNewline
    Write-Host "  $Name PID = $($proc.Id), log = $logFile" -ForegroundColor DarkGray
    return $proc
}

# === 啟動 Streamlit ===
if (-not $GodotOnly) {
    Start-DemoServer `
        -Name "streamlit" `
        -Cmd "python" `
        -Arguments "-m streamlit run streamlit_app.py --server.port $StreamlitPort --server.headless true" `
        -WorkingDir $RepoRoot `
        -Port $StreamlitPort | Out-Null
}

# === 啟動 Godot Web HTTP server(從 godot_demo/web/)===
if (-not $StreamlitOnly) {
    $godotWebDir = Join-Path $RepoRoot "godot_demo\web"
    if (Test-Path $godotWebDir) {
        # 用 scripts/serve_godot.py(no-cache header)而不是 http.server,
        # 避免重 export 後 iframe 還抓到舊版 PCK
        Start-DemoServer `
            -Name "godot-web" `
            -Cmd "python" `
            -Arguments "scripts\serve_godot.py --port $GodotPort --dir godot_demo\web" `
            -WorkingDir $RepoRoot `
            -Port $GodotPort | Out-Null
    } else {
        Write-Host "[!] godot_demo\web\ 不存在 — 跳過 Godot HTTP server" -ForegroundColor Yellow
        Write-Host "    若要 demo Godot 版,請先用 Godot Editor 做 Web export 到 godot_demo\web\" -ForegroundColor DarkYellow
        Write-Host "    或 demo 時直接用 Godot Editor F5 跑也可以" -ForegroundColor DarkYellow
    }
}

Write-Host "" 
Write-Host "==============================================================" -ForegroundColor Green
Write-Host " Match3 Demo 已啟動" -ForegroundColor Green
Write-Host "==============================================================" -ForegroundColor Green
if (-not $GodotOnly) {
    Write-Host "  Streamlit:     http://localhost:$StreamlitPort/" -ForegroundColor White
    Write-Host "  AI 自動測試:    http://localhost:$StreamlitPort/AI_Auto_Test" -ForegroundColor White
    Write-Host "  Demo 模式:     http://localhost:$StreamlitPort/Demo" -ForegroundColor White
}
if (-not $StreamlitOnly -and (Test-Path (Join-Path $RepoRoot "godot_demo\web"))) {
    Write-Host "  Godot 美術版:  http://localhost:$GodotPort/" -ForegroundColor White
}
Write-Host ""
Write-Host "  關閉:  .\start_demo.ps1 -Stop" -ForegroundColor DarkGray
Write-Host "  Log:   $LogDir" -ForegroundColor DarkGray
Write-Host "==============================================================" -ForegroundColor Green
