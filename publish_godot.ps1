# =====================================================================
# Godot Web 一鍵發佈到 GitHub Pages
# =====================================================================
#
#   .\publish_godot.ps1                  # 有 GODOT 則先 export，再 commit+push
#   .\publish_godot.ps1 -Export          # 強制先 headless export
#   .\publish_godot.ps1 -SkipExport      # 只 publish 現有 godot_demo/web/
#   .\publish_godot.ps1 -Message "..."
#   .\publish_godot.ps1 -DryRun
#
# 環境變數 GODOT = Godot_*_console.exe 完整路徑（找不到時必填）
#
# GitHub Actions → https://gamacwhung.github.io/Match3_sim/
# =====================================================================

param(
    [string]$Message = "",
    [switch]$DryRun,
    [switch]$Export,
    [switch]$SkipExport
)

$ErrorActionPreference = 'Stop'
$RepoRoot = $PSScriptRoot
$WebDir = Join-Path $RepoRoot "godot_demo\web"
$GodotProject = Join-Path $RepoRoot "godot_demo\project.godot"

function Find-GodotExe {
    if ($env:GODOT -and (Test-Path -LiteralPath $env:GODOT)) {
        return (Resolve-Path -LiteralPath $env:GODOT).Path
    }
    $names = @(
        'Godot_v4.6-stable_win64_console.exe',
        'Godot_v4.6-stable_win64.exe',
        'Godot_v4.5-stable_win64_console.exe',
        'Godot_v4.5-stable_win64.exe'
    )
    $dirs = @(
        $env:LOCALAPPDATA,
        (Join-Path $env:LOCALAPPDATA 'Godot'),
        (Join-Path $env:USERPROFILE 'Downloads'),
        'C:\Program Files\Godot',
        'C:\Godot'
    )
    foreach ($dir in $dirs) {
        if (-not $dir -or -not (Test-Path $dir)) { continue }
        foreach ($name in $names) {
            $p = Join-Path $dir $name
            if (Test-Path -LiteralPath $p) { return (Resolve-Path -LiteralPath $p).Path }
        }
        try {
            $hit = Get-ChildItem -Path $dir -Filter 'Godot*.exe' -Recurse -Depth 3 -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -match 'console' } |
                Select-Object -First 1
            if ($hit) { return $hit.FullName }
        } catch { }
    }
    return $null
}

function Test-GodotScripts {
    param([string]$GodotExe, [string]$GodotDir)
    Write-Host "=== Script check ===" -ForegroundColor Cyan
    Push-Location $GodotDir
    try {
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $out = & $GodotExe --headless --quit-after 2 2>&1 | Out-String
        $ErrorActionPreference = $prevEap
        if ($out -match 'Failed to load script|Parse Error:\s|SCRIPT ERROR:') {
            Write-Host $out
            throw "Godot 腳本有錯誤,請先修再 export"
        }
        Write-Host "[OK] 腳本檢查通過" -ForegroundColor Green
    } finally {
        Pop-Location
    }
}

function Invoke-GodotWebExport {
    param([string]$GodotExe)
    $godotDir = Join-Path $RepoRoot "godot_demo"
    Test-GodotScripts -GodotExe $GodotExe -GodotDir $godotDir
    Write-Host "=== Godot Export (Web) ===" -ForegroundColor Cyan
    Write-Host "  $GodotExe"
    Write-Host "  project: $GodotProject"
    $godotDir = Split-Path -Parent $GodotProject
    Push-Location $godotDir
    try {
        & $GodotExe --headless --path . --export-release "Web" "web/index.html"
        if ($LASTEXITCODE -ne 0) {
            throw "Godot export 結束碼 $LASTEXITCODE（請確認已安裝 Web export templates）"
        }
    } finally {
        Pop-Location
    }
    Write-Host "[OK] Export 完成" -ForegroundColor Green
    Write-Host ""
}

$doExport = $Export -or (-not $SkipExport)
if ($doExport) {
    $godotExe = Find-GodotExe
    if ($godotExe) {
        Invoke-GodotWebExport -GodotExe $godotExe
    } elseif ($Export) {
        Write-Host "[!] 找不到 Godot — 請設定環境變數 GODOT 指向 Godot_*_console.exe" -ForegroundColor Red
        Write-Host "    例: `$env:GODOT = 'C:\Godot\Godot_v4.6-stable_win64_console.exe'" -ForegroundColor DarkYellow
        exit 1
    } else {
        Write-Host "[i] 未找到 Godot，跳過 export（僅 publish 現有 web/）" -ForegroundColor Yellow
        Write-Host "    若要自動匯出: 安裝 Godot 4.6 或設定 `$env:GODOT，再跑 .\publish_godot.ps1 -Export" -ForegroundColor DarkGray
        Write-Host ""
    }
}

if (-not (Test-Path $WebDir)) {
    Write-Host "[!] $WebDir 不存在 — 請先 Export Web 到 godot_demo/web/" -ForegroundColor Red
    exit 1
}

$indexHtml = Join-Path $WebDir "index.html"
$indexPck = Join-Path $WebDir "index.pck"
$indexWasm = Join-Path $WebDir "index.wasm"

foreach ($f in @($indexHtml, $indexPck, $indexWasm)) {
    if (-not (Test-Path $f)) {
        Write-Host "[!] 找不到 $f — Export Path 應為 godot_demo/web/index.html" -ForegroundColor Red
        exit 1
    }
}

$pckSize = (Get-Item $indexPck).Length / 1MB
$wasmSize = (Get-Item $indexWasm).Length / 1MB
$pckMtime = (Get-Item $indexPck).LastWriteTime

# 注入 no-cache meta 到 index.html（Godot export 每次重新生成，需要在這裡後處理）
$htmlContent = Get-Content $indexHtml -Raw
if ($htmlContent -notmatch 'Cache-Control') {
    $htmlContent = $htmlContent -replace '(<meta charset="utf-8">)', "`$1`n`t`t<meta http-equiv=`"Cache-Control`" content=`"no-cache, no-store, must-revalidate`">`n`t`t<meta http-equiv=`"Pragma`" content=`"no-cache`">`n`t`t<meta http-equiv=`"Expires`" content=`"0`">"
    Set-Content $indexHtml -Value $htmlContent -NoNewline
}

# 在 .pck 和 .wasm 路徑加上 timestamp cache-bust
$ts = [int](Get-Date -UFormat %s)
$htmlContent = Get-Content $indexHtml -Raw
$htmlContent = $htmlContent -replace '"index\.pck"', "`"index.pck?v=$ts`""
$htmlContent = $htmlContent -replace '"index\.wasm"', "`"index.wasm?v=$ts`""
Set-Content $indexHtml -Value $htmlContent -NoNewline

# bump live_sprites 資產版本號 → 具名主題 sprite 網址(?v=)跟著換 → 瀏覽器強制重抓最新圖。
# (換了主題 PNG 後只要重跑 export/publish,就不必叫每台瀏覽器硬重整了)
$revFile = Join-Path $WebDir "live_sprites\revision.txt"
if (Test-Path (Split-Path -Parent $revFile)) {
    Set-Content -Path $revFile -Value "$ts" -NoNewline -Encoding ascii
    Write-Host "[patch] live_sprites/revision.txt bump -> $ts" -ForegroundColor Green
}

# 注入 ArtTheme splash 等待：載到「正確風格」才收 loading，避免先閃預設風格再變風格
# （Godot export 每次重生 index.html，這裡後處理重新注入 → 重匯出不會遺失）
$htmlContent = Get-Content $indexHtml -Raw
if ($htmlContent -notmatch '_artThemeReady') {
    $splashPattern = "(?s)\}\)\.then\(\(\) => \{\s*setStatusMode\('hidden'\);\s*\}, displayFailureNotice\);"
    $splashRepl = @"
}).then(() => {
				// 等 ArtTheme 就緒（套用完正確風格才收 loading，避免先閃預設風格）
				const artStart = Date.now();
				const pollArt = () => {
					if (window._artThemeReady || Date.now() - artStart > 60000) {
						setStatusMode('hidden');
						return;
					}
					const p = window._artThemeProgress;
					if (p && p.total > 0) {
						statusProgress.value = p.current;
						statusProgress.max = p.total;
					}
					setTimeout(pollArt, 100);
				};
				pollArt();
			}, displayFailureNotice);
"@
    if ($htmlContent -match $splashPattern) {
        $htmlContent = [regex]::Replace($htmlContent, $splashPattern, $splashRepl)
        Set-Content $indexHtml -Value $htmlContent -NoNewline
        Write-Host "[patch] index.html: ArtTheme splash 等待已注入" -ForegroundColor Green
    } else {
        Write-Host "[patch] 找不到 splash 收尾片段，略過（Godot shell 可能改版）" -ForegroundColor DarkYellow
    }
}

Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host " Godot Web Publish" -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host ("  index.pck:  {0:N1} MB  ({1})" -f $pckSize, $pckMtime)
Write-Host ("  index.wasm: {0:N1} MB" -f $wasmSize)
Write-Host ""

Set-Location $RepoRoot
$diffStat = git diff --stat -- godot_demo/web/ 2>&1
$untracked = git ls-files --others --exclude-standard godot_demo/web/ 2>&1
$staged = git diff --cached --stat -- godot_demo/web/ 2>&1

if (-not $diffStat -and -not $untracked -and -not $staged) {
    Write-Host "[i] godot_demo/web/ 沒變動 — 沒東西要 publish" -ForegroundColor Yellow
    if (-not (Find-GodotExe)) {
        Write-Host "    腳本已改但 web 未重匯出 → 請在 Godot Editor Export 或設定 GODOT 後跑 -Export" -ForegroundColor DarkYellow
    }
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
    Write-Host "[!] push 失敗 — 改動還在 local commit" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "==============================================================" -ForegroundColor Green
Write-Host " 已 push,等 GitHub Actions deploy" -ForegroundColor Green
Write-Host "==============================================================" -ForegroundColor Green
Write-Host "  https://github.com/gamacwhung/Match3_sim/actions" -ForegroundColor White
Write-Host "  https://gamacwhung.github.io/Match3_sim/" -ForegroundColor White
