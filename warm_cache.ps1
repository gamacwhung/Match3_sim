# =====================================================================
# 攤位開場前「預熱」腳本 — 把所有主題的圖透過公開網址載過一遍,
# 讓 Cloudflare edge 先快取住 → 之後訪客(任何裝置/瀏覽器)都秒開,不必各自等冷載。
# =====================================================================
#
#   .\warm_cache.ps1                      # 預熱所有主題(公開網址)
#   .\warm_cache.ps1 -Theme fruit_cartoon # 只預熱水果(最快,~28 秒)
#   .\warm_cache.ps1 -BaseUrl http://localhost:8501   # 改對 localhost 預熱
#
# 每天開場前跑一次即可。若中途有「重匯出/換圖(revision 變了)」→ 再跑一次。
# =====================================================================
param(
    [string]$BaseUrl = "https://match3.gamaniaocc.org",
    [string]$Theme = ""   # 空 = 全部主題
)

$ErrorActionPreference = 'Continue'
$RepoRoot = $PSScriptRoot
$liveDir = Join-Path $RepoRoot "godot_demo\web\live_sprites"

# 版本號(跟 art_theme 請求 sprite 用的 ?v 一致 → 命中同一個 Cloudflare 快取鍵)
$rev = (Get-Content -LiteralPath (Join-Path $liveDir "revision.txt") -Raw).Trim()
$themes = Get-Content -LiteralPath (Join-Path $liveDir "themes.json") -Raw | ConvertFrom-Json

Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host " 預熱 Cloudflare 快取" -ForegroundColor Cyan
Write-Host "   目標: $BaseUrl"
Write-Host "   版本: $rev"
Write-Host "==============================================================" -ForegroundColor Cyan

$sw = [Diagnostics.Stopwatch]::StartNew()
$total = 0; $ok = 0; $miss = 0

foreach ($t in $themes) {
    $name = "$($t.name)"
    if ([string]::IsNullOrEmpty($name)) { continue }        # 預設糖果是打包圖,不走 live sprite
    if ($Theme -and $name -ne $Theme) { continue }
    $themeDir = Join-Path $liveDir "themes\$name"
    if (-not (Test-Path $themeDir)) { continue }

    $manifest = Get-Content -LiteralPath (Join-Path $themeDir "manifest.json") -Raw | ConvertFrom-Json
    Write-Host ("→ {0} ({1}) — {2} 張" -f $t.label, $name, $manifest.Count) -ForegroundColor White
    foreach ($sprite in $manifest) {
        $url = "$BaseUrl/game/live_sprites/themes/$name/$sprite.png?v=$rev"
        $total++
        try {
            $r = Invoke-WebRequest -Uri $url -Method Get -UseBasicParsing -TimeoutSec 90
            $cf = $r.Headers['Cf-Cache-Status']
            if ($r.StatusCode -eq 200) { $ok++ } else { $miss++ }
        } catch {
            $miss++
            Write-Host "   失敗: $sprite" -ForegroundColor DarkYellow
        }
    }
}
$sw.Stop()
Write-Host "==============================================================" -ForegroundColor Green
Write-Host (" 完成:{0}/{1} 張,耗時 {2} 秒。" -f $ok, $total, [int]$sw.Elapsed.TotalSeconds) -ForegroundColor Green
Write-Host " Cloudflare edge 已暖 → 訪客載入應大幅變快。" -ForegroundColor Green
Write-Host "==============================================================" -ForegroundColor Green
