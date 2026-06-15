"""
Game Art AI Generation — CLI 入口

用法:
  # 1. 盤點 asset(輸出 art_pipeline/asset_manifest.json)
  python scripts/ai_art_gen.py manifest

  # 2. 生成(text 風格描述,可加風格參考圖;先 --dry-run 看 prompt)
  python scripts/ai_art_gen.py generate --style "像素風格 pixel art" --run pixel --dry-run
  python scripts/ai_art_gen.py generate --style "像素風格 pixel art" --run pixel
  python scripts/ai_art_gen.py generate --style "水彩手繪" --style-image ref.png --run watercolor

  # 只生部分 asset / 某個 family
  python scripts/ai_art_gen.py generate --style "像素風格" --run pixel --assets Red,Grn,Blu,Yel
  python scripts/ai_art_gen.py generate --style "像素風格" --run pixel --family powerups

  # 3. 審核 generated_art/<run>/ 後套用(自動備份原版)/ 還原
  python scripts/ai_art_gen.py apply --run pixel
  python scripts/ai_art_gen.py restore

API key: config.py / .streamlit/secrets.toml / 環境變數 GOOGLE_API_KEY(或 Vertex AI GCP_PROJECT_ID)
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    parser = argparse.ArgumentParser(description='Game Art AI Generation pipeline (Gemini)')
    sub = parser.add_subparsers(dest='cmd', required=True)

    sub.add_parser('manifest', help='盤點 asset,輸出 manifest JSON')

    g = sub.add_parser('generate', help='生成新風格美術(staging,不動原圖)')
    g.add_argument('--style', required=True, help='美術風格 text 描述,例如 "像素風格 pixel art"')
    g.add_argument('--run', required=True, help='run 名稱(輸出到 generated_art/<run>/)')
    g.add_argument('--style-image', help='風格參考圖路徑(可選)')
    g.add_argument('--assets', help='逗號分隔的 asset 名單(預設全部)')
    g.add_argument('--family', help='只生成某個 family(elements/powerups/crate/...)')
    g.add_argument('--image-model', default=None, help='生圖模型(預設 gemini-2.5-flash-image)')
    g.add_argument('--critic-model', default=None, help='評審模型(預設 gemini-2.5-flash)')
    g.add_argument('--max-iters', type=int, default=3, help='每張 asset 最多迭代次數(預設 3)')
    g.add_argument('--force', action='store_true', help='重生已 pass 的 asset')
    g.add_argument('--dry-run', action='store_true', help='只列出目標與範例 prompt,不呼叫 API')

    a = sub.add_parser('apply', help='把生成結果套進 Godot sprites(自動備份原版)')
    a.add_argument('--run', required=True)

    sub.add_parser('restore', help='還原原版 sprites')

    args = parser.parse_args()

    if args.cmd == 'manifest':
        from art_pipeline.manifest import save_manifest, families
        m = save_manifest()
        print('\nFamily 一覽:')
        for fam, names in families(m).items():
            print(f'  {fam:18s} {len(names):2d} 張')

    elif args.cmd == 'generate':
        from art_pipeline import gemini_api, pipeline
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
        )

    elif args.cmd == 'apply':
        from art_pipeline.apply import apply_run
        apply_run(args.run)

    elif args.cmd == 'restore':
        from art_pipeline.apply import restore
        restore()


if __name__ == '__main__':
    main()
