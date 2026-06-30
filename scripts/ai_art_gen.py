"""
Game Art AI Generation — CLI 入口

用法:
  # 1. 盤點 asset(輸出 art_pipeline/asset_manifest.json)
  python scripts/ai_art_gen.py manifest

  # 2. 生成(text 風格描述,可加元素參考圖:圖騰/logo/特殊形狀/風格;先 --dry-run 看 prompt)
  python scripts/ai_art_gen.py generate --style "像素風格 pixel art" --run pixel --dry-run
  python scripts/ai_art_gen.py generate --style "像素風格 pixel art" --run pixel
  python scripts/ai_art_gen.py generate --style "水彩手繪" --style-image ref.png --run watercolor

  # 主題生成後再換畫風:用先前 run 的 sprite 當 Reference A(不含的 asset 會跳過)
  python scripts/ai_art_gen.py generate --style "水彩手繪" --run watercolor_v2 \\
      --reference-run pixar_cartoon

  # 主題換物件模式(theme-swap):不參考原圖,依 gameplay role 發明新主題物件
  python scripts/ai_art_gen.py generate --mode theme-swap --style "海洋主題 watercolor" \\
      --theme "糖果換成貝殼,箱子換成珊瑚礁" --run ocean_theme --dry-run

  # 不使用參考圖(只靠 style text)
  python scripts/ai_art_gen.py generate --style "像素風格" --run pixel --no-reference-image
  python scripts/ai_art_gen.py list-roles

  # 列出所有 --assets / --family 選項
  python scripts/ai_art_gen.py list-assets

  # 只生部分 asset / 某個 family
  python scripts/ai_art_gen.py generate --style "像素風格" --run pixel --assets Red,Grn,Blu,Yel
  python scripts/ai_art_gen.py generate --style "像素風格" --run pixel --family powerups

  # 3. 審核 generated_art/<run>/ 後套用(自動備份原版)/ 還原
  python scripts/ai_art_gen.py apply --run pixel
  python scripts/ai_art_gen.py restore

API key: config.py / .streamlit/secrets.toml / 環境變數 GOOGLE_API_KEY(或 Vertex AI GCP_PROJECT_ID)
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_asset_options():
    from art_pipeline.manifest import build_manifest, families, format_assets_help
    manifest = build_manifest()
    grouped = families(manifest)
    return manifest, grouped, format_assets_help(manifest)


def main():
    parser = argparse.ArgumentParser(
        description='Game Art AI Generation pipeline (Gemini)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest='cmd', required=True)

    sub.add_parser('manifest', help='盤點 asset,輸出 manifest JSON')

    _, grouped, assets_help = _load_asset_options()
    family_choices = sorted(grouped)

    list_assets = sub.add_parser('list-assets', help='列出所有 --assets 名稱與 --family 選項')
    list_assets.add_argument('--family', choices=family_choices,
                             help='只顯示某個 family 的 asset')

    g = sub.add_parser(
        'generate',
        help='生成新風格美術(staging,不動原圖)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=assets_help,
    )
    g.add_argument('--style', required=True, help='美術風格 text 描述,例如 "像素風格 pixel art"')
    g.add_argument('--run', required=True, help='run 名稱(輸出到 generated_art/<run>/)')
    g.add_argument('--mode', choices=['restyle', 'theme-swap'], default='restyle',
                   help='restyle=保留原物件只換風格(預設); theme-swap=依 gameplay role 發明新主題物件')
    g.add_argument('--theme', default=None,
                   help='主題方向(theme-swap):概念如「糖果屋」(可 --expand-theme 自動指派每色物件)')
    g.add_argument('--expand-theme', action='store_true',
                   help='用 LLM 展開 --theme 成每個 element 物件(概念型主題預設自動開啟)')
    g.add_argument('--no-expand-theme', action='store_true',
                   help='不要 LLM 展開 --theme')
    g.add_argument('--no-refine-style', action='store_true',
                   help='不要 LLM 精煉 --style（預設會精煉成鎖定畫風規格）')
    g.add_argument('--style-image',
                   help='元素參考圖路徑(圖騰/logo/特殊形狀/風格;可選;預設用 game_art_reference.png 若存在)')
    g.add_argument('--no-reference-image', action='store_true',
                   help='不使用任何參考圖(含預設 game_art_reference.png 與 --style-image)')
    g.add_argument('--assets', metavar='NAME,...',
                   help='逗號分隔 asset 名稱(預設全部)。執行 list-assets 或 generate --help 可看完整清單')
    g.add_argument('--family', choices=family_choices, metavar='FAMILY',
                   help='只生成某個 family(與 --assets 可擇一,或同時用於再篩選)')
    g.add_argument('--reference-run', metavar='RUN',
                   help='restyle 專用:用 generated_art/<RUN>/sprites/ 當 Reference A; '
                        'reference run 沒有的 asset 跳過,不 fallback 官方圖')
    g.add_argument('--image-model', default=None, help='生圖模型(預設 gemini-3.5-flash-image)')
    g.add_argument('--critic-model', default=None, help='評審模型(預設 gemini-3.5-flash)')
    g.add_argument('--max-iters', type=int, default=3, help='每張 asset 最多迭代次數(預設 3)')
    g.add_argument('--force', action='store_true', help='重生已 pass 的 asset')
    g.add_argument('--dry-run', action='store_true', help='只列出目標與範例 prompt,不呼叫 API')

    a = sub.add_parser('apply', help='把生成結果套進 Godot sprites(自動備份原版)')
    a.add_argument('--run', required=True)

    sub.add_parser('restore', help='還原原版 sprites')

    list_roles = sub.add_parser('list-roles', help='列出 asset_roles.json 中的 gameplay role class')
    list_roles.add_argument('--role', help='只顯示某個 role class 的詳細定義')

    args = parser.parse_args()

    if args.cmd == 'manifest':
        from art_pipeline.manifest import save_manifest, families
        m = save_manifest()
        print('\nFamily 一覽:')
        for fam, names in sorted(families(m).items()):
            print(f'  {fam:18s} {len(names):2d} 張  {", ".join(names)}')

    elif args.cmd == 'list-assets':
        _, grouped, _ = _load_asset_options()
        if args.family:
            names = grouped[args.family]
            print(f'{args.family} ({len(names)}):')
            print(', '.join(names))
        else:
            print('Family 選項 (--family):')
            for fam in sorted(grouped):
                print(f'  {fam}')
            print()
            for fam in sorted(grouped):
                names = grouped[fam]
                print(f'{fam} ({len(names)}): {", ".join(names)}')

    elif args.cmd == 'list-roles':
        from art_pipeline.roles import get_role_class, list_role_classes, load_config
        if args.role:
            rc = get_role_class(args.role)
            print(f'=== {args.role} ===')
            print(json.dumps(rc, ensure_ascii=False, indent=2))
        else:
            cfg = load_config()
            print(f'Role classes ({len(cfg["role_classes"])}):')
            for item in list_role_classes():
                print(f'  {item["id"]:28s} [{item["category"]}] {item["label"]}')
            print(f'\n定義檔: art_pipeline/asset_roles.json')
            print('詳細: python scripts/ai_art_gen.py list-roles --role match_element')

    elif args.cmd == 'generate':
        from art_pipeline import gemini_api, pipeline
        mode = 'theme_swap' if args.mode == 'theme-swap' else 'restyle'
        expand_theme = pipeline.resolve_expand_theme(
            mode, args.theme,
            expand_theme_flag=args.expand_theme,
            no_expand_theme=args.no_expand_theme,
        )
        refine_style = pipeline.resolve_refine_style(
            no_refine_style=args.no_refine_style,
        )
        try:
            pipeline.run(
                style_text=args.style,
                run_name=args.run,
                style_image_path=args.style_image,
                asset_names=args.assets.split(',') if args.assets else None,
                family=args.family,
                image_model=args.image_model or gemini_api.DEFAULT_IMAGE_MODEL,
                critic_model=args.critic_model or gemini_api.DEFAULT_CRITIC_MODEL,
                max_iters=args.max_iters,
                force=args.force,
                dry_run=args.dry_run,
                mode=mode,
                theme_text=args.theme,
                reference_image=not args.no_reference_image,
                expand_theme=expand_theme,
                refine_style=refine_style,
                reference_run=args.reference_run,
            )
        except (ValueError, FileNotFoundError) as e:
            raise SystemExit(str(e)) from e

    elif args.cmd == 'apply':
        from art_pipeline.apply import apply_run
        apply_run(args.run)

    elif args.cmd == 'restore':
        from art_pipeline.apply import restore
        restore()


if __name__ == '__main__':
    main()
