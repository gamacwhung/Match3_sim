#!/usr/bin/env python3
"""
批次測試 theme-swap 模式 — 只生成五種基本元素 (Red, Grn, Blu, Yel, Pur)。

用法:
  # 列出預設主題
  python scripts/test_theme_elements.py --list

  # 試跑全部主題(不呼叫 API)
  python scripts/test_theme_elements.py --dry-run

  # 只跑海洋、森林
  python scripts/test_theme_elements.py --themes ocean,forest

  # 跑全部預設主題(預設不用參考圖,純文字風格)
  python scripts/test_theme_elements.py

  # 若要使用 game_art_reference.png 或自訂參考圖
  python scripts/test_theme_elements.py --use-reference-image
  python scripts/test_theme_elements.py --use-reference-image --style-image ref.png

  # 自訂 style + 主題概念(LLM 自動展開每個 element 的物件)
  python scripts/test_theme_elements.py \
    --style "2D Disney cartoon style" \
    --theme "糖果屋" \
    --run candy_house

  # 手動指定每色物件(不經 LLM 展開)
  python scripts/test_theme_elements.py \
    --style "2D Disney cartoon style" \
    --theme "Red=red gumdrop, Grn=green candy cane, Blu=blue lollipop, Yel=yellow lemon drop, Pur=purple jelly" \
    --run candy_manual --no-expand-theme

產出: generated_art/theme_test_noref_<slug>/sprites/{Red,Grn,Blu,Yel,Pur}.png
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# slug → (style, theme_direction)
THEME_PRESETS: dict[str, tuple[str, str]] = {
    'ocean': (
        'ocean watercolor pixel art, soft bubbles, seafoam highlights',
        'Red=red coral, Grn=green seaweed, Blu=blue shell, Yel=yellow starfish, Pur=purple sea urchin',
    ),
    'forest': (
        'cozy forest hand-painted pixel art, moss and bark textures',
        'Red=red apple, Grn=green leaf, Blu=blue berry, Yel=yellow mushroom cap, Pur=purple flower',
    ),
    'space': (
        'cute sci-fi pixel art, glowing nebula accents',
        'Red=red planet, Grn=green alien crystal, Blu=blue comet, Yel=yellow star, Pur=purple moon',
    ),
    'dessert': (
        'pastel dessert pixel art, glossy icing highlights',
        'Red=red strawberry tart, Grn=green matcha mochi, Blu=blue blueberry cupcake, '
        'Yel=yellow lemon macaron, Pur=purple grape jelly',
    ),
    'farm': (
        'warm farm pixel art, rustic wooden crate vibes',
        'Red=red tomato, Grn=green cabbage, Blu=blue plum, Yel=yellow corn, Pur=purple eggplant',
    ),
    'winter': (
        'winter holiday pixel art, frosty sparkle',
        'Red=red mitten, Grn=green pine cone, Blu=blue icicle, Yel=yellow lantern, Pur=purple scarf',
    ),
    'steampunk': (
        'steampunk brass pixel art, rivets and gauges',
        'Red=red pressure valve, Grn=green copper pipe, Blu=blue gauge dial, '
        'Yel=yellow gear, Pur=purple steam orb',
    ),
    'candy': (
        '2D Disney cartoon style, rounded shapes, glossy candy highlights, playful and colorful',
        'Red=red cherry candy, Grn=green gummy bear, Blu=blue lollipop, '
        'Yel=yellow lemon drop, Pur=purple grape jelly bean',
    ),
}

ELEMENT_ASSETS = 'Red,Grn,Blu,Yel,Pur'
RUN_PREFIX_NOREF = 'theme_test_noref_'
RUN_PREFIX_REF = 'theme_test_'


def _list_themes() -> None:
    print('預設主題 (--themes 用 slug,逗號分隔):')
    for slug, (style, theme) in THEME_PRESETS.items():
        print(f'\n  {slug}')
        print(f'    style : {style}')
        print(f'    theme : {theme}')
    print(f'\n共 {len(THEME_PRESETS)} 組 → 每組生成 {ELEMENT_ASSETS}')
    print(f'輸出目錄(預設無參考圖): generated_art/{RUN_PREFIX_NOREF}<slug>/')


def _run_one(slug: str, style: str, theme: str, *, dry_run: bool, force: bool,
             max_iters: int, style_image: str | None, reference_image: bool,
             expand_theme: bool) -> tuple[str, float, str | None]:
    from art_pipeline import gemini_api, pipeline

    prefix = RUN_PREFIX_REF if reference_image else RUN_PREFIX_NOREF
    run_name = f'{prefix}{slug}'
    t0 = time.time()
    try:
        pipeline.run(
            style_text=style,
            run_name=run_name,
            style_image_path=style_image,
            asset_names=ELEMENT_ASSETS.split(','),
            image_model=gemini_api.DEFAULT_IMAGE_MODEL,
            critic_model=gemini_api.DEFAULT_CRITIC_MODEL,
            max_iters=max_iters,
            force=force,
            dry_run=dry_run,
            mode='theme_swap',
            theme_text=theme,
            reference_image=reference_image,
            expand_theme=expand_theme,
        )
        elapsed = time.time() - t0
        return run_name, elapsed, None
    except Exception as e:  # noqa: BLE001
        return run_name, time.time() - t0, str(e)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='批次測試 theme-swap 元素生成(僅 Red/Grn/Blu/Yel/Pur)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--list', action='store_true', help='列出預設主題後結束')
    parser.add_argument('--themes', metavar='SLUG,...',
                        help=f'要跑的主題 slug(預設全部)。可選: {",".join(THEME_PRESETS)}')
    parser.add_argument('--style', help='自訂 style 描述(需搭配 --theme)')
    parser.add_argument('--theme', help='主題概念,例如「糖果屋」(可搭配 --expand-theme 自動指派每色物件)')
    parser.add_argument('--run', metavar='SLUG', help='自訂 run 名稱(搭配 --style/--theme 時使用)')
    parser.add_argument('--expand-theme', action='store_true',
                        help='用 LLM 展開 --theme 成每個 element 物件(概念型主題預設自動開啟)')
    parser.add_argument('--no-expand-theme', action='store_true',
                        help='不要 LLM 展開,直接把 --theme 當完整描述')
    parser.add_argument('--dry-run', action='store_true', help='只印 prompt,不呼叫 API')
    parser.add_argument('--force', action='store_true', help='重生已 pass 的 asset')
    parser.add_argument('--max-iters', type=int, default=3, help='每張 asset 最多迭代次數(預設 3)')
    parser.add_argument('--style-image', help='主題視覺參考圖(需搭配 --use-reference-image)')
    parser.add_argument('--use-reference-image', action='store_true',
                        help='使用參考圖(預設 game_art_reference.png 或 --style-image)')
    args = parser.parse_args()

    if args.list:
        _list_themes()
        return

    custom = bool(args.style and args.theme)
    if (args.style or args.theme) and not custom:
        raise SystemExit('自訂模式需同時提供 --style 和 --theme')

    if custom:
        slug = (args.run or args.theme.replace(' ', '_'))[:40]
        slugs = [slug]
        style_theme = [(args.style, args.theme)]
        # 概念型主題(沒有 Red=...)預設自動展開
        auto_expand = '=' not in args.theme
        expand_theme = (not args.no_expand_theme) and (args.expand_theme or auto_expand)
    elif args.themes:
        slugs = [s.strip() for s in args.themes.split(',') if s.strip()]
        unknown = [s for s in slugs if s not in THEME_PRESETS]
        if unknown:
            raise SystemExit(f'未知主題 slug: {unknown}\n可用: {list(THEME_PRESETS)}')
        style_theme = [THEME_PRESETS[s] for s in slugs]
        expand_theme = args.expand_theme and not args.no_expand_theme
    else:
        slugs = list(THEME_PRESETS)
        style_theme = [THEME_PRESETS[s] for s in slugs]
        expand_theme = False

    mode = 'DRY-RUN' if args.dry_run else 'GENERATE'

    ref_mode = '含參考圖' if args.use_reference_image else '純文字(無參考圖)'
    expand_label = 'LLM展開' if expand_theme else '不展開'
    print(f'[{mode}] 將測試 {len(slugs)} 個主題 × 5 elements · {ref_mode} · {expand_label}')
    print(f'  slugs: {", ".join(slugs)}')
    prefix = RUN_PREFIX_REF if args.use_reference_image else RUN_PREFIX_NOREF
    print(f'  輸出: generated_art/{prefix}<slug>/')
    print()

    results: list[tuple[str, float, str | None]] = []
    for i, slug in enumerate(slugs, 1):
        style, theme = style_theme[i - 1]
        print(f'── [{i}/{len(slugs)}] {slug} ──')
        print(f'  style: {style}')
        print(f'  theme: {theme}')
        run_name, elapsed, err = _run_one(
            slug, style, theme,
            dry_run=args.dry_run,
            force=args.force,
            max_iters=args.max_iters,
            style_image=args.style_image,
            reference_image=args.use_reference_image,
            expand_theme=expand_theme,
        )
        if err:
            print(f'  ✗ 失敗 ({elapsed:.1f}s): {err}')
        else:
            print(f'  ✓ 完成 ({elapsed:.1f}s) → generated_art/{run_name}/')
        results.append((slug, elapsed, err))
        print()

    print('=' * 50)
    print('摘要')
    ok = [r for r in results if r[2] is None]
    fail = [r for r in results if r[2] is not None]
    print(f'  成功: {len(ok)}/{len(results)}')
    prefix = RUN_PREFIX_REF if args.use_reference_image else RUN_PREFIX_NOREF
    for slug, elapsed, _ in ok:
        print(f'    ✓ {slug} ({elapsed:.0f}s) → generated_art/{prefix}{slug}/')
    if fail:
        print(f'  失敗: {len(fail)}')
        for slug, _, err in fail:
            print(f'    ✗ {slug}: {err}')


if __name__ == '__main__':
    main()
