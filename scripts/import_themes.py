"""
把同事下載的 theme zip(多套換皮美術)匯入成可在 web 端 ?live=1 切換的主題。

- 從 zip 直接讀(不先解壓 2GB 到磁碟)，只取「白名單」內的 sprite（過濾掉 iterXX_sXX 等生成中間檔）。
- 下載到 web 端會逐張 fetch，所以先 downscale（board_bg→1024、其餘→512，跟 ArtTheme 執行期上限一致）+ optimize，
  把每套從 ~300MB 壓到 ~10MB，攤位/本機載入才順。
- 每套輸出到 godot_demo/web/live_sprites/themes/<theme>/<stem>.png + manifest.json（stem 陣列）。
- 另輸出 godot_demo/web/live_sprites/themes.json 給切換 UI 用（含預設 candy）。

用法:
  python scripts/import_themes.py <zip路徑> [<zip路徑2> ...]
"""
from __future__ import annotations

import io
import json
import os
import sys
import zipfile

from PIL import Image

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIVE_DIR = os.path.join(_ROOT, "godot_demo", "web", "live_sprites")
THEMES_DIR = os.path.join(LIVE_DIR, "themes")

MAX_DIM_DEFAULT = 512
MAX_DIM_NAMED = {"board_bg": 1024}

# 好看的顯示名稱（中/英）。沒列到的 theme 用資料夾名當 label。
THEME_LABELS = {
    "candy_pixar_cyberpunk_yuan": "賽博龐克 Cyberpunk",
    "ocean_theme": "海洋 Ocean",
    "pixar_cartoon": "皮克斯卡通 Pixar",
    "pixel_restyle": "像素 Pixel",
    "steampunk": "蒸氣龐克 Steampunk",
    "zen_garden_pool": "禪意庭園 Zen",
}


def _whitelist() -> set[str]:
    """遊戲實際會用到的 sprite stem = 目前 live_sprites/*.png（candy 預設集）。"""
    return {f[:-4] for f in os.listdir(LIVE_DIR) if f.endswith(".png")}


def _downscale(img: Image.Image, max_dim: int) -> Image.Image:
    w, h = img.size
    longest = max(w, h)
    if longest <= max_dim:
        return img
    s = max_dim / longest
    return img.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)


def import_zip(zip_path: str, wl: set[str]) -> list[str]:
    imported_themes: list[str] = []
    with zipfile.ZipFile(zip_path) as z:
        # 整理 zip 內 theme/<name>/<stem>.png
        by_theme: dict[str, dict[str, str]] = {}
        for n in z.namelist():
            if not n.lower().endswith(".png"):
                continue
            parts = n.split("/")
            if len(parts) < 3 or parts[0] != "theme":
                continue
            theme, stem = parts[1], parts[-1][:-4]
            if stem in wl:
                by_theme.setdefault(theme, {})[stem] = n

        for theme in sorted(by_theme):
            stems = by_theme[theme]
            out_dir = os.path.join(THEMES_DIR, theme)
            os.makedirs(out_dir, exist_ok=True)
            kept: list[str] = []
            for stem in sorted(stems):
                raw = z.read(stems[stem])
                try:
                    img = Image.open(io.BytesIO(raw)).convert("RGBA")
                except Exception as e:  # noqa: BLE001
                    print(f"  [skip] {theme}/{stem}: {e}")
                    continue
                img = _downscale(img, MAX_DIM_NAMED.get(stem, MAX_DIM_DEFAULT))
                img.save(os.path.join(out_dir, f"{stem}.png"), optimize=True)
                kept.append(stem)
            # manifest.json = ArtTheme 期望的 stem 陣列
            with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump(sorted(kept), f, ensure_ascii=False, indent=0)
            sz = sum(os.path.getsize(os.path.join(out_dir, f"{s}.png")) for s in kept)
            print(f"  [ok] {theme}: {len(kept)} sprites, {sz // 1024 // 1024} MB")
            imported_themes.append(theme)
    return imported_themes


def write_index(all_themes: list[str]) -> None:
    """themes.json：切換 UI 用。第一筆固定是預設 candy（base_url = live_sprites/ 本身）。"""
    entries = [{"name": "", "label": "糖果 Candy", "default": True}]
    for t in sorted(set(all_themes)):
        entries.append({"name": t, "label": THEME_LABELS.get(t, t)})
    with open(os.path.join(LIVE_DIR, "themes.json"), "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    print(f"themes.json: {len(entries)} 套（含預設 candy）")


def main() -> None:
    zips = sys.argv[1:]
    if not zips:
        print("用法: python scripts/import_themes.py <zip路徑> [...]")
        sys.exit(1)
    wl = _whitelist()
    print(f"白名單 {len(wl)} 個 sprite；輸出到 {THEMES_DIR}")
    os.makedirs(THEMES_DIR, exist_ok=True)
    all_themes: list[str] = []
    for zp in zips:
        if not os.path.exists(zp):
            print(f"[!] 找不到 {zp}")
            continue
        print(f"=== {zp} ===")
        all_themes += import_zip(zp, wl)
    write_index(all_themes)
    print("完成。")


if __name__ == "__main__":
    main()
