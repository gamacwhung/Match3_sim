"""
迭代生成 pipeline — 每張 asset 跑「生成 → 程式化驗證 → vision 評審 → 帶修正指示重生成」。

robust 設計:
- 以原 sprite 作為結構參考(restyle 而非從零生成),功能偏離小
- 兩層驗證:postprocess(客觀)+ critic(風格/功能語意)
- 迭代有上限,全程記錄每次嘗試,失敗時保留「分數最高」的版本並標記 needs_review
- 結果寫到 staging 目錄(generated_art/<run>/),絕不直接覆寫原圖
- 已 pass 的 asset 重跑時自動跳過(可 --force 重生)

產出目錄結構(generated_art/<run>/):
  sprites/            最終選用的圖(apply 會用這個)
  history/<asset>/    每一次迭代保留的圖,檔名含 iter 次數、分數與 tag
                      例: iter01_s16_critiqued.png(第 1 次,critic 總分 16)
                          iter02_rejected_raw.png(第 2 次沒過 postprocess,留模型原始輸出)
  report.json         完整紀錄(每次 attempt 的 verdict + 對應 history 圖路徑 + chosen_iter)
"""

from __future__ import annotations

import json
import pathlib
import time

from .manifest import PROJECT_ROOT, SPRITES_DIR, build_manifest
from . import gemini_api, postprocess

GENERATED_ROOT = PROJECT_ROOT / 'generated_art'

# 預設元素參考圖(圖騰/logo/特殊形狀/風格;沒指定 --style-image 時自動使用,若存在)
DEFAULT_STYLE_IMAGE = PROJECT_ROOT / 'game_art_reference.png'

PASS_STYLE = 7
PASS_FUNCTION = 7
PASS_ELEMENT = 7


def _chromakey_block(asset: dict) -> str:
    """產生 chromakey 背景指示(供程式精準去背用)。"""
    ck = postprocess.chromakey_for(asset)
    r, g, b = ck['rgb']
    name = ck['name_en']
    return (
        f"""- BACKGROUND: render the subject on a SOLID, FLAT, UNIFORM {name} background using
  EXACTLY hex {ck['hex']} (RGB {r}, {g}, {b}). The whole background must be this single pure
  color — no gradients, no shadows, no lighting effects. This background will be removed
  programmatically by chromakey, so it must be clean.
- NO OUTLINE/BORDER: do NOT add any white outline, border, halo, glow or sticker frame around
  the subject. The subject must touch the {name} background directly with crisp, clean edges.
- NO {name.upper()} IN SUBJECT: the subject itself must NOT contain any {name} color (use a
  clearly different shade if needed) so it is not mistaken for the chromakey background.
- SHARP EDGES: crisp, well-defined edges — no soft or blurry boundaries.""")


def build_generation_prompt(asset: dict, style_text: str, family_names: list[str],
                            feedback: str | None, has_style_image: bool = False) -> str:
    constraints = '\n'.join(f'- {c}' for c in asset.get('constraints', []))
    family_note = ''
    if len(family_names) > 1:
        family_note = (f'\n[Series consistency] This asset belongs to the "{asset["family"]}" '
                       f'series (members: {", ".join(family_names)}). Every member will be '
                       f'redrawn separately, so keep a consistent design language that lets '
                       f'them sit next to each other.')
    feedback_note = (f'\n[Fix instructions from the previous attempt — MUST follow] {feedback}'
                     if feedback else '')
    if asset.get('transparent', True):
        bg_rule = _chromakey_block(asset)
    else:
        bg_rule = '- This is a full-canvas opaque background image — fill the entire canvas.'

    if has_style_image:
        intro = (
            "Combine the two reference images to generate a single 2D match-3 game asset.\n\n"
            "[Subject & composition — Reference A] Fully preserve the object/subject and its "
            "shape, pose and overall composition from Reference A (the original asset). After "
            "the redraw players must still recognize its gameplay function at a glance.\n"
            "[Design elements — Reference B] Treat Reference B as a design-element reference: "
            "incorporate its distinctive visual elements — motifs/totems, logos/emblems, "
            "ornamental patterns and special shapes — together with its art style, color palette "
            "and lighting/mood, and tastefully integrate them into the subject from Reference A "
            "without breaking its silhouette or gameplay readability.\n\n"
            f"[Additional text style guidance] {style_text}")
    else:
        intro = ("Redraw the match-3 game asset shown in the reference image in a new art style.\n\n"
                 f"[Target art style] {style_text}")

    return f"""{intro}

[Asset name] {asset['name']}
[Gameplay function — after the redraw, players must still recognize this function at a glance]
{asset['function']}

[Visual constraints]
{constraints}

[Output requirements]
{bg_rule}
- Preserve the original composition, silhouette proportions and meaning; change ONLY the art style
- Square canvas, a single image — no collage, no multiple views{family_note}{feedback_note}"""


def _save_iteration(history_dir: pathlib.Path, asset: dict, i: int,
                    raw_bytes: bytes | None, processed: bytes | None,
                    score: int | None, status_tag: str) -> dict:
    """把單次迭代的圖存進 history 目錄,回傳記錄(相對 run_dir 的路徑)。

    status_tag: 'critiqued' / 'rejected'(postprocess 沒過)/ 'error'。
    raw_bytes  : 模型原始輸出(沒過 postprocess 時也保留,方便事後檢視)。
    processed  : postprocess 後、實際會被選用的圖(可能為 None)。
    """
    asset_dir = history_dir / asset['name']
    asset_dir.mkdir(parents=True, exist_ok=True)
    saved: dict = {}
    score_tag = f'_s{score}' if score is not None else ''
    if processed is not None:
        fn = f'iter{i:02d}{score_tag}_{status_tag}{asset["file"][len(asset["name"]):]}'
        (asset_dir / fn).write_bytes(processed)
        saved['image_file'] = str((asset_dir / fn).relative_to(history_dir.parent))
    if raw_bytes is not None and processed is None:
        # postprocess 沒過 → 留模型原始輸出(可能含底色),檔名標 raw
        fn = f'iter{i:02d}_{status_tag}_raw.png'
        (asset_dir / fn).write_bytes(raw_bytes)
        saved['raw_file'] = str((asset_dir / fn).relative_to(history_dir.parent))
    return saved


def generate_one(client, asset: dict, style_text: str, style_image: bytes | None,
                 family_names: list[str], image_model: str, critic_model: str,
                 max_iters: int, history_dir: pathlib.Path | None = None) -> dict:
    """對單一 asset 跑迭代循環。回傳結果 dict(含 attempts log 與最佳圖 bytes)。

    history_dir 有給時,每一次迭代的圖都會被保留到 history_dir/<asset>/ 並標上 tag。
    """
    original = (PROJECT_ROOT / asset['path']).read_bytes()
    refs: list[tuple[bytes, str]] = [
        (original, 'Reference A — the original asset; preserve its subject, shape and composition')]
    if style_image:
        refs.append(
            (style_image, 'Reference B — design-element reference; weave in its motifs, logos, '
                          'special shapes, patterns, palette and style'))

    attempts = []
    best = None  # (score, png_bytes, verdict, iter)
    feedback = None

    for i in range(1, max_iters + 1):
        prompt = build_generation_prompt(asset, style_text, family_names, feedback,
                                         has_style_image=style_image is not None)
        t0 = time.time()
        try:
            raw = gemini_api.generate_image(client, image_model, prompt, refs)
        except Exception as e:  # noqa: BLE001
            attempts.append({'iter': i, 'stage': 'generate', 'ok': False, 'error': str(e)})
            feedback = None
            continue

        ok, issues, processed = postprocess.process(raw, asset)
        if not ok:
            entry = {'iter': i, 'stage': 'postprocess', 'ok': False, 'issues': issues}
            if history_dir is not None:
                entry.update(_save_iteration(history_dir, asset, i, raw, None, None, 'rejected'))
            attempts.append(entry)
            feedback = ('; '.join(issues)
                        + '. Output a single centered object on a fully transparent background.')
            continue

        verdict = gemini_api.critique_image(
            client, critic_model, original, processed, style_text, asset, style_image)
        score = verdict['style_score'] + verdict['function_score'] + (2 if verdict['background_ok'] else 0)
        if style_image is not None:
            score += verdict.get('reference_element_score', 0)
        entry = {
            'iter': i, 'stage': 'critique', 'ok': True,
            'elapsed_sec': round(time.time() - t0, 1),
            'postprocess_warnings': issues, 'verdict': verdict, 'score': score,
        }
        if history_dir is not None:
            entry.update(_save_iteration(history_dir, asset, i, raw, processed, score, 'critiqued'))
        attempts.append(entry)
        if best is None or score > best[0]:
            best = (score, processed, verdict, i)

        passed = (verdict['verdict'] == 'pass'
                  and verdict['style_score'] >= PASS_STYLE
                  and verdict['function_score'] >= PASS_FUNCTION
                  and verdict['background_ok']
                  and (style_image is None
                       or verdict.get('reference_element_score', 0) >= PASS_ELEMENT))
        if passed:
            return {'name': asset['name'], 'status': 'pass', 'iters': i,
                    'attempts': attempts, 'image': processed, 'verdict': verdict,
                    'chosen_iter': i}
        feedback = verdict.get('fix_instructions') or ';'.join(verdict.get('issues', []))

    if best is not None:
        return {'name': asset['name'], 'status': 'needs_review', 'iters': max_iters,
                'attempts': attempts, 'image': best[1], 'verdict': best[2],
                'chosen_iter': best[3]}
    return {'name': asset['name'], 'status': 'failed', 'iters': max_iters,
            'attempts': attempts, 'image': None, 'verdict': None, 'chosen_iter': None}


def run(style_text: str, run_name: str,
        style_image_path: str | None = None,
        asset_names: list[str] | None = None,
        family: str | None = None,
        image_model: str = gemini_api.DEFAULT_IMAGE_MODEL,
        critic_model: str = gemini_api.DEFAULT_CRITIC_MODEL,
        max_iters: int = 3,
        force: bool = False,
        dry_run: bool = False) -> pathlib.Path:
    """跑整批生成。回傳 run 目錄。"""
    manifest = build_manifest()
    by_family: dict[str, list[str]] = {}
    for a in manifest:
        by_family.setdefault(a.get('family') or 'misc', []).append(a['name'])

    targets = manifest
    if asset_names:
        wanted = set(asset_names)
        targets = [a for a in targets if a['name'] in wanted]
        missing = wanted - {a['name'] for a in targets}
        if missing:
            raise SystemExit(f'找不到這些 asset: {sorted(missing)}')
    if family:
        targets = [a for a in targets if a.get('family') == family]
    if not targets:
        raise SystemExit('沒有符合條件的 asset')

    run_dir = GENERATED_ROOT / run_name
    sprites_out = run_dir / 'sprites'
    sprites_out.mkdir(parents=True, exist_ok=True)
    # 每一次迭代的圖都保留在這裡(history/<asset>/iterNN_sXX_<tag>.png)
    history_dir = run_dir / 'history'
    report_path = run_dir / 'report.json'
    report = json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {
        'style': style_text, 'image_model': image_model, 'critic_model': critic_model, 'results': {},
    }

    # 元素參考圖:優先用 --style-image,否則用預設 game_art_reference.png(若存在)
    resolved_style_path: pathlib.Path | None = None
    if style_image_path:
        resolved_style_path = pathlib.Path(style_image_path)
    elif DEFAULT_STYLE_IMAGE.exists():
        resolved_style_path = DEFAULT_STYLE_IMAGE
    if resolved_style_path and not resolved_style_path.exists():
        raise SystemExit(f'找不到元素參考圖: {resolved_style_path}')
    style_image = resolved_style_path.read_bytes() if resolved_style_path else None
    if style_image:
        print(f'元素參考圖: {resolved_style_path}')
    else:
        print('未使用元素參考圖(純文字風格)')

    if dry_run:
        print(f'[dry-run] 將生成 {len(targets)} 張 asset(風格: {style_text}):')
        for a in targets:
            print(f'  - {a["name"]:32s} {a["width"]}x{a["height"]}  [{a.get("family")}] {a["function"][:40]}')
        print('\n[dry-run] 範例 prompt(第一張):\n')
        print(build_generation_prompt(targets[0], style_text,
                                      by_family.get(targets[0].get('family') or 'misc', []), None,
                                      has_style_image=style_image is not None))
        return run_dir

    client = gemini_api.get_client()
    print(f'開始生成 {len(targets)} 張 asset → {run_dir}')
    n_pass = n_review = n_fail = n_skip = 0

    for idx, asset in enumerate(targets, 1):
        prev = report['results'].get(asset['name'])
        if prev and prev.get('status') == 'pass' and not force:
            n_skip += 1
            print(f'[{idx}/{len(targets)}] {asset["name"]} — 已 pass,跳過(--force 可重生)')
            continue

        print(f'[{idx}/{len(targets)}] {asset["name"]} 生成中…')
        result = generate_one(client, asset, style_text, style_image,
                              by_family.get(asset.get('family') or 'misc', []),
                              image_model, critic_model, max_iters,
                              history_dir=history_dir)
        image = result.pop('image')
        if image:
            (sprites_out / asset['file']).write_bytes(image)
        report['results'][asset['name']] = result
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

        v = result.get('verdict') or {}
        tag = {'pass': '✅ pass', 'needs_review': '🟡 needs_review', 'failed': '❌ failed'}[result['status']]
        print(f'    {tag} (iters={result["iters"]}, style={v.get("style_score")}, '
              f'function={v.get("function_score")})')
        n_pass += result['status'] == 'pass'
        n_review += result['status'] == 'needs_review'
        n_fail += result['status'] == 'failed'

    print(f'\n完成: pass={n_pass}  needs_review={n_review}  failed={n_fail}  skipped={n_skip}')
    print(f'最終選用圖在 {sprites_out}')
    print(f'每次迭代的歷史圖在 {history_dir}/<asset>/(檔名含 iter 次數 + 分數)')
    print(f'報告在 {report_path}')
    print(f'確認後執行: python scripts/ai_art_gen.py apply --run {run_name}')
    return run_dir
