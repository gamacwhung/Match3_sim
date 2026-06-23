"""
Asset Manifest — 盤點遊戲美術資產:名稱、尺寸、功能、視覺約束。

每張 sprite 的「功能描述 + 不可妥協的視覺約束」是風格轉換時 prompt 的核心,
確保換皮後物件仍然能被玩家辨識(火箭要有方向性、元素顏色不能變、破損進程要連貫)。
function / constraints 一律用英文撰寫,因為會直接注入 Gemini prompt。

用法:
    from art_pipeline.manifest import build_manifest
    manifest = build_manifest()          # list[dict]
    python -m art_pipeline.manifest      # 輸出 art_pipeline/asset_manifest.json
"""

from __future__ import annotations

import json
import pathlib

PROJECT_ROOT = pathlib.Path(__file__).parent.parent
SPRITES_DIR = PROJECT_ROOT / 'godot_demo' / 'resources' / 'sprites'
MANIFEST_PATH = pathlib.Path(__file__).parent / 'asset_manifest.json'

# 盤面一格約 70px,所有物件都要在這個尺寸下可辨識
CELL_DISPLAY_PX = 70

# 注意:背景處理(chromakey 綠/洋紅幕)由 pipeline 的 generation prompt 統一注入,
# 不放在這裡,避免和「要求透明」互相矛盾。這裡只放與「主體本身」有關的約束。
_COMMON_SPRITE_CONSTRAINTS = [
    'A single centered object occupying 70%-90% of the canvas, with padding around it',
    f'Silhouette must remain clearly recognizable when displayed at {CELL_DISPLAY_PX}px',
    'No text, letters, or watermarks of any kind',
]


def _role(category: str, function: str, constraints: list[str] | None = None,
          family: str | None = None, transparent: bool = True) -> dict:
    return {
        'category': category,
        'function': function,
        'constraints': (constraints or []) + (_COMMON_SPRITE_CONSTRAINTS if transparent else []),
        'family': family,
        'transparent': transparent,
    }


def _build_role_table() -> dict[str, dict]:
    roles: dict[str, dict] = {}

    # ---- 基本元素(消除主角,顏色 identity 絕對不能變) ----
    for tid, color_en in [('Red', 'red'), ('Grn', 'green'), ('Blu', 'blue'),
                          ('Yel', 'yellow'), ('Pur', 'purple')]:
        roles[tid] = _role(
            'element',
            f'Basic {color_en} match element. Players swap adjacent elements to form lines of 3+ '
            f'to clear them. This is the most numerous object on the board.',
            [f'Dominant color must be unmistakably {color_en} — players distinguish elements '
             f'by color at a glance; it must never be confused with the other element colors',
             'Plump, rounded shape that tiles well when packed densely in a grid'],
            family='elements',
        )

    # ---- 道具(powerups,合成獲得,功能語意要看得出來) ----
    roles['Soda0d'] = _role(
        'powerup',
        'Horizontal rocket powerup (created by matching 4 in a vertical line). '
        'When triggered it clears the entire row.',
        ['Appearance must clearly read as HORIZONTAL direction (e.g. sideways rocket/arrow/'
         'energy bar) — players must anticipate it fires left and right'],
        family='powerups',
    )
    roles['Soda90'] = _role(
        'powerup',
        'Vertical rocket powerup (created by matching 4 in a horizontal line). '
        'When triggered it clears the entire column.',
        ['Appearance must clearly read as VERTICAL direction — players must anticipate '
         'it fires up and down',
         'Should look like the same object as Soda0d rotated 90 degrees'],
        family='powerups',
    )
    roles['TNT'] = _role(
        'powerup',
        'Bomb powerup (created by an L/T-shaped match). When triggered it explodes '
        'a 5x5 area around itself.',
        ['Must instantly read as an EXPLOSIVE (bomb / dynamite / energy orb) with a sense of danger'],
        family='powerups',
    )
    roles['LtBl'] = _role(
        'powerup',
        'Color bomb / light ball powerup (created by matching 5 in a line; the strongest powerup). '
        'Swapping it with an element clears every element of that color on the board.',
        ['A glowing spherical orb with rainbow/multi-color hints implying "works on all colors"; '
         'it should look like the rarest, most powerful item'],
        family='powerups',
    )
    roles['TrPr'] = _role(
        'powerup',
        'Paper plane powerup (created by a 2x2 square match). When triggered it clears the 4 '
        'adjacent cells in a cross, then flies to a high-value target for a precision strike.',
        ['Must read as a FLYING PROJECTILE (paper plane / dart / small bird) with direction '
         'and a sense of motion'],
        family='powerups',
    )

    # ---- 紙箱(最常見障礙物,4 級破損進程) ----
    for lv in range(1, 5):
        state = {1: 'almost destroyed, heavily cracked', 2: 'visibly damaged',
                 3: 'slightly damaged', 4: 'intact, undamaged'}[lv]
        roles[f'Crt{lv}'] = _role(
            'obstacle',
            f'Cardboard crate obstacle (remaining HP {lv}/4, {state}). Occupies a cell and blocks '
            f'falling elements; each adjacent match deals 1 damage.',
            ['Crt1-Crt4 are the SAME crate at 4 progressive damage stages — material and design '
             'must be identical, only the damage level increases',
             'Boxy square body that fills the cell'],
            family='crate',
        )

    # ---- 可移動障礙物 ----
    roles['Barrel'] = _role(
        'obstacle',
        'Barrel obstacle (player can swap it around; affected by gravity and falls). '
        'Destroyed by adjacent matches.',
        ['Cylindrical barrel shape that looks "pushable" rather than fixed in place'],
        family='movable',
    )
    for lv in (1, 2):
        roles[f'TrafficCone_lv{lv}'] = _role(
            'obstacle',
            f'Traffic cone obstacle (remaining HP {lv}/2; movable and falls with gravity). '
            f'Each adjacent match deals 1 damage.',
            ['lv1 is the damaged version of lv2 — identical design, different wear',
             'Clear cone silhouette'],
            family='movable',
        )

    # ---- 罐頭(只能被道具打) ----
    roles['SalmonCan'] = _role(
        'obstacle',
        'Salmon can obstacle (intact state). Immune to normal matches — only powerups '
        '(rocket / bomb / paper plane) can damage it.',
        ['Metallic can texture; must look HARD and impervious to ordinary matches'],
        family='salmon_can',
    )
    roles['SalmonCan_body'] = _role(
        'obstacle',
        'Salmon can body (lower part shown after the lid opens; rendered layered with top1/top2).',
        ['Must share the same design language as SalmonCan'], family='salmon_can',
    )
    roles['SalmonCan_top1'] = _role(
        'obstacle', 'Salmon can lid (half-open state part).',
        ['Rendered layered on SalmonCan_body — alignment must look natural'],
        family='salmon_can',
    )
    roles['SalmonCan_top2'] = _role(
        'obstacle', 'Salmon can lid (fully-open state part).',
        ['Rendered layered on SalmonCan_body — alignment must look natural'],
        family='salmon_can',
    )

    # ---- 下層 / 上層修飾物 ----
    for lv in (1, 2):
        roles[f'Puddle_lv{lv}'] = _role(
            'obstacle',
            f'Puddle (bottom-layer obstacle, remaining HP {lv}/2). Elements sit ON TOP of it; '
            f'clearing an element in this cell deals 1 damage.',
            ['Flat and semi-transparent — elements are drawn above it, so it must not steal '
             'visual focus from the elements',
             'lv1 is a nearly-dried-up version of lv2'],
            family='puddle',
        )
    for lv in (1, 2):
        roles[f'Rope_lv{lv}'] = _role(
            'obstacle',
            f'Rope (top-layer obstacle, remaining HP {lv}/2). Covers the element underneath '
            f'so it cannot be swapped; each adjacent match deals 1 damage.',
            ['Net/frame structure — the trapped element underneath must remain visible through it',
             'lv1 is the damaged version of lv2'],
            family='rope',
        )
    roles['Mud'] = _role(
        'obstacle',
        'Mud (top-layer obstacle). Completely hides the element underneath (players cannot see '
        'what is below); cleared by an adjacent match.',
        ['Opaque, fully covers the cell, with a "dirty smear" feel'],
        family='mud',
    )

    # ---- 郵戳製造機 + 明信片 ----
    roles['Stamp'] = _role(
        'obstacle',
        'Stamp machine (never destroyed). Every adjacent match makes it "stamp once", '
        'producing 1 goal item that counts toward level completion.',
        ['Should look like a stamp/postmark machine — something REUSABLE, not breakable'],
        family='postmark',
    )
    for name, desc in [
        ('Postmark_01', 'Postmark imprint pattern 1 (used in the stamping animation)'),
        ('Postmark_02', 'Postmark imprint pattern 2 (used in the stamping animation)'),
        ('Postmark_card', 'Postcard (the object that receives the stamp)'),
        ('Postmark_bundle', 'Bundle of postcards (visual for the collected goal items)'),
        ('Postmark_goal', 'Postcard goal icon (shown small in the top-left HUD objective bar)'),
    ]:
        roles[name] = _role(
            'obstacle', f'{desc}. Part of the postmark-level goal item set.',
            ['The whole Postmark_* set must share one consistent style'],
            family='postmark',
        )

    # ---- 水池(2x2) ----
    for lv in range(1, 6):
        roles[f'Pool_lv{lv}'] = _role(
            'obstacle',
            f'Pool obstacle (large 2x2 object, remaining HP {lv}/5). When destroyed it spawns '
            f'puddles (Puddle) in surrounding cells.',
            ['Pool_lv1-lv5 are the SAME pool at 5 progressive depletion stages — identical design',
             'Large 2x2 object — composition must fill the square canvas'],
            family='pool',
        )

    # ---- 礦泉水櫃(2x2, 11 級) ----
    roles['WaterChiller_closed'] = _role(
        'obstacle',
        'Water chiller cabinet (large 2x2 object, door closed). The door must be opened first, '
        'then bottles are consumed one by one.',
        ['Sealed cabinet — it should read as "something inside, door still closed"'],
        family='water_chiller',
    )
    roles['WaterChiller_door'] = _role(
        'obstacle', 'Water chiller door (part used in the door-opening animation; tall rectangle).',
        ['Must match the door design of WaterChiller_closed'],
        family='water_chiller',
    )
    for lv in range(1, 12):
        roles[f'WaterChiller_lv{lv}'] = _role(
            'obstacle',
            f'Water chiller after the door opens (remaining {lv}/11 bottles). '
            f'Each valid match removes one bottle.',
            ['lv1-lv11 form a "bottles decreasing" progression — the cabinet stays identical, '
             'only the bottle count changes'],
            family='water_chiller',
        )

    # ---- 飲料櫃(2x2, 對色消除) ----
    roles['BeverageChiller_closed'] = _role(
        'obstacle',
        'Beverage chiller (large 2x2 object, door closed). Requires matches of the MATCHING COLOR '
        'next to it to open the door.',
        ['The 4 colored beverage bottles inside should be faintly visible through the door'],
        family='beverage_chiller',
    )
    roles['BeverageChiller_body'] = _role(
        'obstacle',
        'Beverage chiller cabinet body (base part after the door opens; bottles are drawn on top).',
        ['Composition must leave space for 4 bottle slots'], family='beverage_chiller',
    )
    roles['BeverageChiller_door'] = _role(
        'obstacle', 'Beverage chiller door (door-opening animation part).',
        ['Must match the door of BeverageChiller_closed'], family='beverage_chiller',
    )
    for color_en in ['red', 'green', 'blue', 'yellow']:
        roles[f'BeverageChiller_bottle_{color_en}'] = _role(
            'obstacle',
            f'{color_en.capitalize()} beverage bottle inside the chiller (drawn on top of '
            f'BeverageChiller_body). Only matches using {color_en} elements can clear this bottle.',
            [f'Bottle dominant color must be unmistakably {color_en} and consistent with the '
             f'{color_en} basic element — this is a gameplay-critical color match'],
            family='beverage_chiller',
        )
    for lv in range(1, 6):
        roles[f'BeverageChiller_lv{lv}'] = _role(
            'obstacle',
            f'Beverage chiller full-state image (remaining {lv}/5).',
            ['lv1-lv5 form a bottles-decreasing progression — the cabinet stays identical'],
            family='beverage_chiller',
        )

    # ---- 盤面背景 ----
    roles['board_bg'] = _role(
        'background',
        'Board background image (full-canvas backdrop drawn underneath the grid cells).',
        ['Opaque, low-contrast, low-saturation — must never steal focus from board elements',
         'Seamless feel with no strong focal object; semi-transparent grid cells will be '
         'drawn over it'],
        family='background',
        transparent=False,
    )

    return roles


ROLE_TABLE = _build_role_table()


def build_manifest(sprites_dir: pathlib.Path = SPRITES_DIR) -> list[dict]:
    """掃描 sprites 目錄,合併功能表,回傳完整 manifest。"""
    from PIL import Image

    manifest = []
    unknown = []
    for png in sorted(sprites_dir.glob('*.png')):
        stem = png.stem
        with Image.open(png) as im:
            width, height = im.size
            has_alpha = im.mode in ('RGBA', 'LA', 'PA')
        role = ROLE_TABLE.get(stem)
        if role is None:
            unknown.append(stem)
            role = _role('unknown', '(Unregistered asset — add a function description before generating)')
        manifest.append({
            'name': stem,
            'file': png.name,
            'path': str(png.relative_to(PROJECT_ROOT)),
            'width': width,
            'height': height,
            'has_alpha': has_alpha,
            **role,
        })
    if unknown:
        print(f'[manifest] 警告: {len(unknown)} 個 asset 未登錄功能描述: {unknown}')
    return manifest


def save_manifest(path: pathlib.Path = MANIFEST_PATH) -> list[dict]:
    manifest = build_manifest()
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[manifest] 已輸出 {len(manifest)} 筆 asset 到 {path}')
    return manifest


def families(manifest: list[dict]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for a in manifest:
        out.setdefault(a.get('family') or 'misc', []).append(a['name'])
    for names in out.values():
        names.sort()
    return out


def all_asset_names(sprites_dir: pathlib.Path = SPRITES_DIR) -> list[str]:
    """所有可生成的 asset 名稱(與 --assets 選項一致)。"""
    return [a['name'] for a in build_manifest(sprites_dir)]


def format_assets_help(manifest: list[dict] | None = None) -> str:
    """產生 --assets / list-assets 用的分組說明文字。"""
    grouped = families(manifest or build_manifest())
    lines = ['可用 asset 名稱(逗號分隔,大小寫需完全一致):']
    for fam in sorted(grouped):
        lines.append(f'  {fam}: {", ".join(grouped[fam])}')
    return '\n'.join(lines)


if __name__ == '__main__':
    save_manifest()
