# =====================================================================
# Godot Web 一鍵發佈到 GitHub Pages
# =====================================================================
#
# 流程:Godot Editor → Export → Web → 輸出到 godot_demo/web/ 之後,
# 跑這支:
#
#   .\publish_godot.ps1                  # add + commit + push (預設 message)
#   .\publish_godot.ps1 -Message "tnt 5x5 fixed"
#   .\publish_godot.ps1 -DryRun          # 只看 size + diff,不 commit
#
# GitHub Actions 會自動 deploy 到 https://gamacwhung.github.io/Match3_sim/
# (約 30 秒 build + 1~5 分鐘 CDN 同步)
# =====================================================================

param(
    [string]$Message = "",
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$RepoRoot = $PSScriptRoot
$WebDir = Join-Path $RepoRoot "godot_demo\web"

if (-not (Test-Path $WebDir)) {
    Write-Host "[!] $WebDir 不存在 — 請先在 Godot Editor 內 Export → Web → 輸出到 godot_demo/web/" -ForegroundColor Red
    exit 1
}

$indexHtml = Join-Path $WebDir "index.html"
$indexPck = Join-Path $WebDir "index.pck"
$indexWasm = Join-Path $WebDir "index.wasm"

foreach ($f in @($indexHtml, $indexPck, $indexWasm)) {
    if (-not (Test-Path $f)) {
        Write-Host "[!] 找不到 $f — 請確認 Godot Export 的 Export Path 是 godot_demo/web/index.html" -ForegroundColor Red
        exit 1
    }
}

$pckSize = (Get-Item $indexPck).Length / 1MB
$wasmSize = (Get-Item $indexWasm).Length / 1MB
$pckMtime = (Get-Item $indexPck).LastWriteTime

Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host " Godot Web Build" -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host ("  index.pck:  {0:N1} MB  ({1})" -f $pckSize, $pckMtime)
Write-Host ("  index.wasm: {0:N1} MB" -f $wasmSize)
Write-Host ""

# 看現在 godot_demo/web/ 有什麼變動
Set-Location $RepoRoot
$diffStat = git diff --stat -- godot_demo/web/ 2>&1
$untracked = git ls-files --others --exclude-standard godot_demo/web/ 2>&1
$staged = git diff --cached --stat -- godot_demo/web/ 2>&1

if (-not $diffStat -and -not $untracked -and -not $staged) {
    Write-Host "[i] godot_demo/web/ 沒變動 — 沒東西要 publish" -ForegroundColor Yellow
    exit 0
}

Write-Host "=== 變動 ===" -ForegroundColor Green
if ($diffStat) { Write-Host $diffStat }
if ($untracked) { Write-Host "Untracked:`n$untracked" }
Write-Host ""

if ($DryRun) {
    Write-Host "[DryRun] 結束 — 沒 commit / push" -ForegroundColor Yellow
    exit 0
}

# Commit message
if (-not $Message) {
    $Message = "build: re-export godot web ($([datetime]::Now.ToString('yyyy-MM-dd HH:mm')))"
}

git add godot_demo/web/
git commit -m $Message
if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] commit 失敗" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Pushing to origin/main..." -ForegroundColor Cyan
git push origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] push 失敗 — 改動還在 local commit,需要時可手動 push" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "==============================================================" -ForegroundColor Green
Write-Host " 已 push,等 GitHub Actions deploy" -ForegroundColor Green
Write-Host "==============================================================" -ForegroundColor Green
Write-Host "  Workflow:  https://github.com/gamacwhung/Match3_sim/actions" -ForegroundColor White
Write-Host "  Live URL:  https://gamacwhung.github.io/Match3_sim/" -ForegroundColor White
Write-Host ""
Write-Host "  約 30 秒後 Actions 跑完,再過 1~5 分鐘 CDN 同步" -ForegroundColor DarkGray
