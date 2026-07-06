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
from typing import Callable

from .manifest import PROJECT_ROOT, SPRITES_DIR, build_manifest
from .roles import GenerationMode, role_mode_brief
from .theme_planner import (
    expand_theme_for_targets,
    format_assignments,
    theme_note_for_asset,
    theme_plan_complete_for_targets,
    _assignment_order,
)
from .family_style_planner import (
    expand_family_styles,
    should_plan_family_styles,
)
from .style_planner import refine_style_prompt, resolved_style_text
from .stage_planner import (
    expand_stage_progression,
    is_stage_family,
    stage_note_for_asset,
    stage_order,
)
from .visual_guidance import (
    FAMILY_ANCHOR_REF_LABEL,
    format_family_visual_block,
    get_family_anchor_asset,
    order_targets_for_family_anchors,
)
from . import gemini_api, postprocess
from .gemini_api import (
    PASS_COHESION,
    PASS_ELEMENT,
    PASS_FUNCTION,
    PASS_PROGRESSION,
    PASS_REASONABLENESS,
    PASS_STYLE,
)
from .sprite_sheet import write_sprite_contact_sheet
from .run_config import build_run_config
from .run_log import RunLog

GENERATED_ROOT = PROJECT_ROOT / 'generated_art'

# 鏈式 stage 生成:前一級(HP 較高)當參考,鎖住演進方向。與 family anchor(鎖畫風)並用。
PREV_STAGE_REF_LABEL = (
    'Reference — PREVIOUS stage of this same object (one HP level HIGHER, i.e. less damaged). '
    'Keep the exact same base object, material, palette and rendering. Show this stage as '
    'clearly MORE damaged/depleted than it, in one discrete step obvious at ~70px. '
    'Do NOT redraw a different object.')

# 預設元素參考圖(圖騰/logo/特殊形狀/風格;沒指定 --style-image 時自動使用,若存在)
DEFAULT_STYLE_IMAGE = PROJECT_ROOT / 'game_art_reference.png'

# 全域規則:遊戲素材不要有臉部五官(眼睛/嘴巴/表情等擬人化特徵),除非物件本身就是角色。
NO_FACE_RULE = (
    '- NO FACIAL FEATURES: do NOT add eyes, mouths, faces, expressions or any anthropomorphic '
    'features to the asset. Keep objects as inanimate objects — no cartoon eyes or smiley faces.')

NO_OUTLINE_RULE = (
    '- NO OUTLINE/STROKE: do NOT add any ink outline, stroke, border contour, or edge line '
    'around the subject — no black, white, or colored strokes. Define form with shading and '
    'color only.')

# 全域規則:主體要填滿畫面、不要細長。細長的東西縮到 ~70px 會又小又難辨識。
FILL_FRAME_RULE = (
    '- FILL THE FRAME: make the subject large and fill most of the square canvas (roughly '
    '85–95% of the width or height), centered, leaving only a thin even margin — never leave '
    'large empty areas.\n'
    '- NO THIN/ELONGATED SHAPES: keep the subject a chunky, compact, well-rounded form. Avoid '
    'thin, spindly, sliver-like or highly elongated silhouettes. If the object must imply a '
    'direction, express it with a bold thick shape, never a thin stick or bar.')

# on_progress(current_index, total, asset_name, result_or_none)
# result_or_none: generate_one 回傳 dict(含 image bytes),或跳過時為先前 report 條目 + image
GenerationProgressCallback = Callable[[int, int, str, dict | None], None]


def resolve_expand_theme(
    mode: GenerationMode,
    theme_text: str | None,
    *,
    expand_theme_flag: bool = False,
    no_expand_theme: bool = False,
) -> bool:
    """與 CLI / Web 共用的主題展開邏輯。"""
    auto_expand = bool(mode == 'theme_swap' and theme_text and '=' not in theme_text)
    return (not no_expand_theme) and (expand_theme_flag or auto_expand)


def resolve_refine_style(*, no_refine_style: bool = False) -> bool:
    """預設精煉 --style；--no-refine-style 關閉。"""
    return not no_refine_style


def resolve_style_image(
    style_image_path: str | pathlib.Path | None = None,
    *,
    reference_image: bool = True,
) -> tuple[pathlib.Path | None, bytes | None]:
    """解析風格/主題參考圖。reference_image=False 時完全不使用參考圖。"""
    if not reference_image:
        return None, None
    resolved: pathlib.Path | None = None
    if style_image_path:
        resolved = pathlib.Path(style_image_path)
    elif DEFAULT_STYLE_IMAGE.exists():
        resolved = DEFAULT_STYLE_IMAGE
    if resolved is not None and not resolved.is_file():
        raise FileNotFoundError(f'找不到參考圖: {resolved}')
    return resolved, (resolved.read_bytes() if resolved else None)


def reference_sprite_path(reference_run: str, asset: dict) -> pathlib.Path:
    """Path to a prior run's sprite used as Reference A (restyle)."""
    return GENERATED_ROOT / reference_run / 'sprites' / asset['file']


def has_reference_sprite(reference_run: str, asset: dict) -> bool:
    return reference_sprite_path(reference_run, asset).is_file()


def filter_targets_for_reference_run(
    targets: list[dict], reference_run: str,
) -> tuple[list[dict], list[str]]:
    """Keep only assets present in reference_run/sprites/; no fallback to official art."""
    kept: list[dict] = []
    missing: list[str] = []
    for asset in targets:
        if has_reference_sprite(reference_run, asset):
            kept.append(asset)
        else:
            missing.append(asset['name'])
    return kept, missing


def load_reference_sprite(reference_run: str, asset: dict) -> bytes:
    path = reference_sprite_path(reference_run, asset)
    if not path.is_file():
        raise FileNotFoundError(
            f'Reference sprite missing for {asset["name"]}: {path}')
    return path.read_bytes()


def _chromakey_block(asset: dict) -> str:
    """產生 chromakey 背景指示(供程式精準去背用)。"""
    return postprocess.chromakey_generation_rules(asset)


def build_generation_prompt(asset: dict, style_text: str, family_names: list[str],
                            feedback: str | None, has_style_image: bool = False,
                            *, mode: GenerationMode = 'restyle',
                            theme_text: str | None = None,
                            theme_plan: dict | None = None,
                            family_style_plan: dict | None = None,
                            stage_plan: dict | None = None,
                            has_family_anchor: bool = False) -> str:
    constraints = '\n'.join(f'- {c}' for c in asset.get('constraints', []))
    family_note = format_family_visual_block(
        asset, family_names,
        has_family_anchor=has_family_anchor,
    )
    feedback_note = (f'\n[Fix instructions from the previous attempt — MUST follow] {feedback}'
                     if feedback else '')
    stage_note = stage_note_for_asset(asset['name'], stage_plan)
    if asset.get('transparent', True):
        bg_rule = _chromakey_block(asset)
    else:
        bg_rule = '- This is a full-canvas opaque background image — fill the entire canvas.'

    if mode == 'theme_swap':
        return _build_theme_swap_prompt(
            asset, style_text, family_names, feedback, has_style_image, theme_text, theme_plan,
            family_style_plan=family_style_plan, stage_plan=stage_plan,
            has_family_anchor=has_family_anchor)

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
{family_note}{stage_note}

[Output requirements]
{bg_rule}
{NO_FACE_RULE}
{NO_OUTLINE_RULE}
{FILL_FRAME_RULE}
- Preserve the original composition, silhouette proportions and meaning; change ONLY the art style
- Square canvas, a single image — no collage, no multiple views{feedback_note}"""


def _build_theme_swap_prompt(asset: dict, style_text: str, family_names: list[str],
                             feedback: str | None, has_style_image: bool,
                             theme_text: str | None,
                             theme_plan: dict | None = None,
                             *,
                             family_style_plan: dict | None = None,
                             stage_plan: dict | None = None,
                             has_family_anchor: bool = False) -> str:
    """Theme-swap mode: invent a NEW object from abstract gameplay role (no original sprite ref)."""
    constraints = '\n'.join(f'- {c}' for c in asset.get('constraints', []))
    brief = role_mode_brief(asset, 'theme_swap')
    preserve = '\n'.join(f'- {p}' for p in brief.get('preserve', []))
    avoid = brief.get('avoid', '')
    family_note = format_family_visual_block(
        asset, family_names,
        has_family_anchor=has_family_anchor,
    )
    feedback_note = (f'\n[Fix instructions from the previous attempt — MUST follow] {feedback}'
                     if feedback else '')
    theme_note = theme_note_for_asset(asset['name'], theme_text, theme_plan)
    stage_note = stage_note_for_asset(asset['name'], stage_plan)

    if asset.get('transparent', True):
        bg_rule = _chromakey_block(asset)
    else:
        bg_rule = '- This is a full-canvas opaque background image — fill the entire canvas.'

    if has_style_image:
        ref_block = (
            "[Theme reference image] Use the attached reference image as the visual theme source: "
            "motifs, palette, ornamental patterns and mood. Invent a NEW object that fits both "
            "the gameplay role below AND this theme — do NOT copy any legacy sprite subject.\n\n")
    else:
        ref_block = ''

    return f"""Create a brand-new 2D match-3 game asset from scratch (theme-swap mode).

{ref_block}[Gameplay role] {asset.get('role_label', asset.get('role_class', ''))}
[Creative brief] {brief.get('creative_brief', '')}
[Must preserve for gameplay readability]
{preserve}
{f'[Do NOT] {avoid}' if avoid else ''}

[Asset slot name] {asset['name']}
[Gameplay function — players must recognize this function at a glance]
{asset.get('function_theme_swap', asset['function'])}

[Visual constraints]
{constraints}
{family_note}

[Target art style] {style_text}{theme_note}{stage_note}

[Output requirements]
{bg_rule}
{NO_FACE_RULE}
{NO_OUTLINE_RULE}
{FILL_FRAME_RULE}
- Invent a completely NEW subject — do NOT replicate any original game sprite
- Square canvas, a single image — no collage, no multiple views{feedback_note}"""


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


def _passes_critique(verdict: dict, *, style_image: bool | None,
                     require_cohesion: bool, has_prev_stage: bool = False,
                     transparent: bool = True) -> bool:
    if verdict['verdict'] != 'pass':
        return False
    if verdict['style_score'] < PASS_STYLE:
        return False
    if verdict['function_score'] < PASS_FUNCTION:
        return False
    if not verdict['background_ok']:
        return False
    if transparent and not verdict.get('cutout_ok', False):
        return False
    if style_image and verdict.get('reference_element_score', 0) < PASS_ELEMENT:
        return False
    if verdict.get('reasonableness_score', 0) < PASS_REASONABLENESS:
        return False
    if require_cohesion and verdict.get('cohesion_score', 0) < PASS_COHESION:
        return False
    if has_prev_stage and verdict.get('progression_score', 0) < PASS_PROGRESSION:
        return False
    return True


def _register_family_anchor(
    family_anchors: dict[str, bytes],
    asset: dict,
    image: bytes | None,
    status: str,
) -> None:
    """Set family anchor from first completed image in the family."""
    fam = asset.get('family')
    if not fam or fam in family_anchors or not image:
        return
    if status not in ('pass', 'needs_review'):
        return
    family_anchors[fam] = image


def generate_one(client, asset: dict, style_text: str, style_image: bytes | None,
                 family_names: list[str], image_model: str, critic_model: str,
                 max_iters: int, history_dir: pathlib.Path | None = None,
                 log: RunLog | None = None,
                 *, mode: GenerationMode = 'restyle',
                 theme_text: str | None = None,
                 theme_plan: dict | None = None,
                 family_style_plan: dict | None = None,
                 stage_plan: dict | None = None,
                 family_anchor: bytes | None = None,
                 prev_stage_image: bytes | None = None,
                 reference_run: str | None = None) -> dict:
    """對單一 asset 跑迭代循環。回傳結果 dict(含 attempts log 與最佳圖 bytes)。

    history_dir 有給時,每一次迭代的圖都會被保留到 history_dir/<asset>/ 並標上 tag。
    """
    original: bytes | None = None
    refs: list[tuple[bytes, str]] = []
    if mode == 'restyle':
        if reference_run:
            original = load_reference_sprite(reference_run, asset)
            ref_label = (
                'Reference A — themed asset from a prior generation run; '
                'preserve its subject, shape and composition')
        else:
            original = (PROJECT_ROOT / asset['path']).read_bytes()
            ref_label = (
                'Reference A — the original asset; preserve its subject, shape and composition')
        refs.append((original, ref_label))
    if family_anchor is not None:
        refs.append((family_anchor, FAMILY_ANCHOR_REF_LABEL))
    if prev_stage_image is not None:
        refs.append((prev_stage_image, PREV_STAGE_REF_LABEL))
    if style_image:
        label = ('Reference — theme visual reference; motifs, palette and style'
                 if mode == 'theme_swap' else
                 'Reference B — design-element reference; weave in its motifs, logos, '
                 'special shapes, patterns, palette and style')
        refs.append((style_image, label))

    attempts = []
    best = None  # (score, png_bytes, verdict, iter)
    feedback = None

    require_cohesion = family_anchor is not None or prev_stage_image is not None

    for i in range(1, max_iters + 1):
        if log:
            log.iter_start(i, max_iters)
        prompt = build_generation_prompt(asset, style_text, family_names, feedback,
                                         has_style_image=style_image is not None,
                                         mode=mode, theme_text=theme_text,
                                         theme_plan=theme_plan,
                                         family_style_plan=family_style_plan,
                                         stage_plan=stage_plan,
                                         has_family_anchor=family_anchor is not None)
        t0 = time.time()
        try:
            raw = gemini_api.generate_image(client, image_model, prompt, refs)
        except Exception as e:  # noqa: BLE001
            if log:
                log.iter_error(i, 'generate', str(e))
            attempts.append({'iter': i, 'stage': 'generate', 'ok': False, 'error': str(e)})
            feedback = None
            continue

        ok, issues, processed = postprocess.process(raw, asset)
        if not ok:
            if log:
                log.iter_postprocess_fail(i, issues)
            entry = {'iter': i, 'stage': 'postprocess', 'ok': False, 'issues': issues}
            if history_dir is not None:
                entry.update(_save_iteration(history_dir, asset, i, raw, None, None, 'rejected'))
            attempts.append(entry)
            feedback = ('; '.join(issues)
                        + '. Output a single centered object on a fully transparent background.')
            continue

        verdict = gemini_api.critique_image(
            client, critic_model, original, processed, style_text, asset, style_image,
            mode=mode, family_anchor=family_anchor, family_style_plan=family_style_plan,
            prev_stage_image=prev_stage_image)
        score = (verdict['style_score'] + verdict['function_score']
                 + verdict.get('reasonableness_score', 0)
                 + (2 if verdict['background_ok'] else 0)
                 + (2 if verdict.get('cutout_ok') else 0))
        if style_image is not None:
            score += verdict.get('reference_element_score', 0)
        if require_cohesion:
            score += verdict.get('cohesion_score', 0)
        if prev_stage_image is not None:
            score += verdict.get('progression_score', 0)
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

        passed = _passes_critique(
            verdict, style_image=style_image is not None,
            require_cohesion=require_cohesion,
            has_prev_stage=prev_stage_image is not None,
            transparent=asset.get('transparent', True))
        if log:
            log.iter_critique(i, time.time() - t0, verdict, score, passed,
                              style_image is not None)
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


def prepare_theme_for_targets(
    mode: GenerationMode,
    theme_text: str | None,
    expand_theme: bool,
    targets: list[dict],
    style_text: str,
    critic_model: str,
    report: dict,
    report_path: pathlib.Path,
    *,
    client=None,
) -> tuple[str | None, dict | None]:
    """Expand a theme concept for theme_swap; updates report on disk when expanded."""
    theme_plan: dict | None = report.get('theme_plan')
    resolved_theme = theme_text
    if mode != 'theme_swap' or not theme_text or not expand_theme:
        return resolved_theme, theme_plan

    target_names = [a['name'] for a in targets]
    if theme_plan_complete_for_targets(theme_plan, theme_text, style_text, target_names):
        return theme_plan.get('theme_direction', theme_text), theme_plan

    if client is None:
        client = gemini_api.get_client()

    existing: dict[str, str] = {}
    if (theme_plan and theme_plan.get('concept') == theme_text
            and theme_plan.get('style') == style_text):
        existing = dict(theme_plan.get('assignments', {}))

    missing_targets = [a for a in targets if a['name'] not in existing]
    new_plan = expand_theme_for_targets(
        theme_text, style_text, missing_targets,
        existing_assignments=existing or None,
        client=client, model=critic_model,
    )
    merged = {**existing, **new_plan['assignments']}
    order = _assignment_order(target_names, merged)
    if existing:
        summary = theme_plan.get('summary', '') if theme_plan else ''
    else:
        summary = new_plan.get('summary', '')
    theme_plan = {
        'concept': theme_text,
        'style': style_text,
        'summary': summary or new_plan.get('summary', ''),
        'assignments': merged,
        'theme_direction': format_assignments(merged, order),
    }
    resolved_theme = theme_plan['theme_direction']
    report['theme_plan'] = theme_plan
    report['theme'] = theme_text
    report['theme_expanded'] = resolved_theme
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return resolved_theme, theme_plan


def prepare_style_for_run(
    style_text: str,
    refine_style: bool,
    mode: GenerationMode,
    theme_text: str | None,
    targets: list[dict],
    critic_model: str,
    report: dict,
    report_path: pathlib.Path,
    *,
    client=None,
) -> tuple[str, dict | None]:
    """Refine vague --style into a locked brief; caches in report."""
    if not refine_style:
        return style_text, report.get('style_plan')

    cached = report.get('style_plan')
    if cached and cached.get('input') == style_text:
        return resolved_style_text(cached, style_text), cached

    if client is None:
        client = gemini_api.get_client()
    families = sorted({a.get('family') or 'misc' for a in targets})
    plan = refine_style_prompt(
        style_text,
        mode=mode,
        theme_text=theme_text,
        target_families=families,
        client=client,
        model=critic_model,
    )
    resolved = resolved_style_text(plan, style_text)
    report['style'] = style_text
    report['style_resolved'] = resolved
    report['style_plan'] = plan
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return resolved, plan


def prepare_family_style_for_targets(
    theme_text: str | None,
    targets: list[dict],
    style_text: str,
    critic_model: str,
    report: dict,
    report_path: pathlib.Path,
    *,
    client=None,
) -> dict | None:
    """Expand per-family visual language when theme + multi-asset batch; caches in report."""
    if not should_plan_family_styles(theme_text, targets):
        return None

    family_ids = sorted({a.get('family') or 'misc' for a in targets})
    cached = report.get('family_style_plan')
    if (cached and cached.get('concept') == theme_text
            and sorted(cached.get('families', {}).keys()) == family_ids):
        return cached

    if client is None:
        client = gemini_api.get_client()
    plan = expand_family_styles(
        theme_text, style_text, family_ids,
        client=client, model=critic_model,
    )
    report['family_style_plan'] = plan
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return plan


def prepare_stage_plans_for_targets(
    targets: list[dict],
    style_text: str,
    critic_model: str,
    report: dict,
    report_path: pathlib.Path,
    *,
    theme_text: str | None = None,
    client=None,
) -> dict[str, dict]:
    """Expand a per-stage visual+reference chain for each stage-progression family.

    Returns {family_id: stage_plan}; caches in report['stage_plans'] keyed by family.
    """
    cached: dict = report.get('stage_plans') or {}
    families = []
    for a in targets:
        fam = a.get('family')
        if fam and is_stage_family(fam) and fam not in families:
            families.append(fam)
    if not families:
        return {}

    plans: dict[str, dict] = {}
    dirty = False
    for fam in families:
        prev = cached.get(fam)
        stage_names = stage_order(fam, targets)
        if (prev and prev.get('concept') == theme_text
                and prev.get('order') == stage_names):
            plans[fam] = prev
            continue
        if client is None:
            client = gemini_api.get_client()
        plan = expand_stage_progression(
            fam, targets, style_text, theme_text=theme_text,
            client=client, model=critic_model,
        )
        if plan:
            plans[fam] = plan
            dirty = True
    if dirty:
        report['stage_plans'] = {**cached, **plans}
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return plans


def _reorder_targets_by_stage_chain(
    targets: list[dict],
    stage_plans: dict[str, dict],
) -> list[dict]:
    """Within each stage-progression family, order assets by their chain order.

    Non-stage assets and families keep their relative position; a stage family's
    block is placed where its first member currently sits, then filled in chain order.
    """
    by_name = {a['name']: a for a in targets}
    stage_family_of = {}
    for fam, plan in stage_plans.items():
        for name in plan.get('order', []):
            stage_family_of[name] = fam

    result: list[dict] = []
    emitted_family: set[str] = set()
    for asset in targets:
        fam = stage_family_of.get(asset['name'])
        if fam is None:
            result.append(asset)
            continue
        if fam in emitted_family:
            continue
        emitted_family.add(fam)
        for name in stage_plans[fam].get('order', []):
            if name in by_name:
                result.append(by_name[name])
    return result


def _seed_family_anchors_from_disk(
    targets: list[dict],
    sprites_out: pathlib.Path,
    report: dict,
    force: bool,
) -> dict[str, bytes]:
    """Load existing sprites as anchors for skipped (already-pass) assets."""
    anchors: dict[str, bytes] = {}
    for asset in targets:
        fam = asset.get('family')
        if not fam or fam in anchors:
            continue
        prev = report.get('results', {}).get(asset['name'])
        if prev and prev.get('status') == 'pass' and not force:
            path = sprites_out / asset['file']
            if path.is_file():
                anchors[fam] = path.read_bytes()
    return anchors


def run(style_text: str, run_name: str,
        style_image_path: str | None = None,
        asset_names: list[str] | None = None,
        family: str | None = None,
        image_model: str = gemini_api.DEFAULT_IMAGE_MODEL,
        critic_model: str = gemini_api.DEFAULT_CRITIC_MODEL,
        max_iters: int = 3,
        force: bool = False,
        dry_run: bool = False,
        *, mode: GenerationMode = 'restyle',
        theme_text: str | None = None,
        reference_image: bool = True,
        expand_theme: bool = False,
        reference_run: str | None = None,
        refine_style: bool = True,
        source: str = 'cli',
        cli_extra: dict | None = None,
        on_progress: GenerationProgressCallback | None = None) -> pathlib.Path:
    """跑整批生成。回傳 run 目錄。

    mode:
      restyle     — 以原 sprite 為 Reference A,只換風格(預設)
      theme_swap  — 依 abstract gameplay role 發明新主題物件,不參考原圖
    reference_image:
      False       — 不使用任何參考圖(含 game_art_reference.png 與 style_image_path)
    expand_theme:
      True        — 用 LLM 把 theme_text(主題概念)展開成每個 element 的物件指派
    refine_style:
      True        — 用 LLM 把 --style 精煉成鎖定的畫風規格(預設開啟)
    reference_run:
      先前生成 run 名稱(如 pixar_cartoon); restyle 時用其 sprites/ 當 Reference A,
      不含的 asset 跳過,不 fallback 官方圖。
    """
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
            raise ValueError(f'找不到這些 asset: {sorted(missing)}')
    if family:
        targets = [a for a in targets if a.get('family') == family]
    if not targets:
        raise ValueError('沒有符合條件的 asset')

    if reference_run:
        if mode != 'restyle':
            raise ValueError('--reference-run 僅適用於 restyle 模式')
        ref_dir = GENERATED_ROOT / reference_run / 'sprites'
        if not ref_dir.is_dir():
            raise FileNotFoundError(f'找不到 reference run: {ref_dir}')
        targets, ref_missing = filter_targets_for_reference_run(targets, reference_run)
        if ref_missing:
            print(f'[reference-run] 跳過 {len(ref_missing)} 張(reference run 無此圖): {ref_missing}')
        if not targets:
            raise ValueError(f'reference run {reference_run!r} 沒有任何符合的 sprite')

    log = RunLog()
    run_dir = GENERATED_ROOT / run_name
    sprites_out = run_dir / 'sprites'
    sprites_out.mkdir(parents=True, exist_ok=True)
    # 每一次迭代的圖都保留在這裡(history/<asset>/iterNN_sXX_<tag>.png)
    history_dir = run_dir / 'history'
    report_path = run_dir / 'report.json'
    report = json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {
        'style': style_text, 'generation_mode': mode, 'theme': theme_text,
        'reference_run': reference_run,
        'image_model': image_model, 'critic_model': critic_model, 'results': {},
    }
    if reference_run:
        report['reference_run'] = reference_run

    report['target_assets'] = [a['name'] for a in targets]
    report['cli'] = build_run_config(
        source=source,
        run_name=run_name,
        style_text=style_text,
        mode=mode,
        theme_text=theme_text,
        family=family,
        asset_names=asset_names,
        style_image_path=str(style_image_path) if style_image_path else None,
        reference_run=reference_run,
        image_model=image_model,
        critic_model=critic_model,
        max_iters=max_iters,
        dry_run=dry_run,
        force=force,
        reference_image=reference_image,
        expand_theme=expand_theme,
        refine_style=refine_style,
        extra=cli_extra,
    )
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    client = gemini_api.get_client()
    cached_style = report.get('style_plan')
    had_style_cache = bool(cached_style and cached_style.get('input') == style_text)
    if refine_style:
        if had_style_cache:
            print(f'[style] 使用已快取的精煉結果: {cached_style.get("summary", "")}')
        else:
            print(f'[style] 精煉畫風: {style_text!r}')
    resolved_style, style_plan = prepare_style_for_run(
        style_text, refine_style, mode, theme_text, targets, critic_model,
        report, report_path, client=client,
    )
    if refine_style and style_plan and not had_style_cache:
        print(f'[style] → {style_plan.get("summary", resolved_style[:80])}')

    cached_plan = report.get('theme_plan')
    had_matching_cache = theme_plan_complete_for_targets(
        cached_plan, theme_text, resolved_style, [a['name'] for a in targets],
    ) if mode == 'theme_swap' and theme_text else False
    if mode == 'theme_swap' and expand_theme and theme_text:
        if had_matching_cache:
            print(f'[theme] 使用已快取的展開結果: {cached_plan.get("theme_direction", theme_text)}')
        else:
            print(f'[theme] 展開主題概念: {theme_text!r}')
    resolved_theme, theme_plan = prepare_theme_for_targets(
        mode, theme_text, expand_theme, targets, resolved_style, critic_model,
        report, report_path, client=client,
    )
    if mode == 'theme_swap' and expand_theme and theme_text and theme_plan and not had_matching_cache:
        print(f'[theme] → {resolved_theme}')

    targets = order_targets_for_family_anchors(targets)

    cached_fsp = report.get('family_style_plan')
    had_fsp_cache = bool(
        cached_fsp and cached_fsp.get('concept') == theme_text
    ) if theme_text and should_plan_family_styles(theme_text, targets) else False
    if theme_text and should_plan_family_styles(theme_text, targets):
        if had_fsp_cache:
            print('[family-style] 使用已快取的 family 視覺規劃')
        else:
            print('[family-style] 展開 per-family 視覺語言…')
    family_style_plan = prepare_family_style_for_targets(
        theme_text, targets, resolved_style, critic_model,
        report, report_path, client=client,
    )
    if theme_text and family_style_plan and not had_fsp_cache:
        fams = ', '.join(sorted(family_style_plan.get('families', {})))
        print(f'[family-style] → {fams}')

    stage_families = sorted({a.get('family') for a in targets
                             if a.get('family') and is_stage_family(a.get('family'))})
    if stage_families:
        print(f'[stage] 展開 {len(stage_families)} 個 family 的鏈式階段規格: {", ".join(stage_families)}')
    stage_plans = prepare_stage_plans_for_targets(
        targets, resolved_style, critic_model, report, report_path,
        theme_text=theme_text, client=client,
    )
    for fam in stage_families:
        plan = stage_plans.get(fam)
        if plan:
            print(f'[stage] {fam} → {" → ".join(plan.get("order", []))}')

    # Stage families must be visited in chain order so each stage's prev-stage ref exists.
    if stage_plans:
        targets = _reorder_targets_by_stage_chain(targets, stage_plans)

    # 元素參考圖:reference_image=False 時不使用;否則優先 --style-image,再 fallback game_art_reference.png
    try:
        resolved_style_path, style_image = resolve_style_image(
            style_image_path, reference_image=reference_image)
    except FileNotFoundError as e:
        raise FileNotFoundError(str(e)) from e

    log.run_header(
        run_name=run_name,
        style=resolved_style if refine_style and style_plan else style_text,
        image_model=image_model,
        critic_model=critic_model,
        max_iters=max_iters,
        targets=targets,
        run_dir=run_dir,
        style_image_path=resolved_style_path,
        dry_run=dry_run,
        reference_run=reference_run,
    )

    if dry_run:
        log.dry_run_targets(targets)
        anchor_name = get_family_anchor_asset(targets[0].get('family'))
        dry_anchor = anchor_name and targets[0]['name'] != anchor_name
        log.dry_run_prompt(build_generation_prompt(
            targets[0], resolved_style,
            by_family.get(targets[0].get('family') or 'misc', []), None,
            has_style_image=style_image is not None,
            mode=mode, theme_text=resolved_theme, theme_plan=theme_plan,
            family_style_plan=family_style_plan,
            stage_plan=stage_plans.get(targets[0].get('family')),
            has_family_anchor=dry_anchor))
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        return run_dir

    family_anchors = _seed_family_anchors_from_disk(targets, sprites_out, report, force)
    # 鏈式 stage:每個 stage family 最近一張完成圖(前一級),餵給下一級當「演進」參考。
    prev_stage_images: dict[str, bytes] = {}
    n_pass = n_review = n_fail = n_skip = 0
    total = len(targets)

    for idx, asset in enumerate(targets, 1):
        if on_progress:
            on_progress(idx, total, asset['name'], None)

        fam = asset.get('family') or 'misc'
        stage_plan = stage_plans.get(fam)
        # prev-stage ref: the previous entry in this family's stage chain
        prev_stage_image = None
        if stage_plan:
            ref_name = stage_plan.get('stages', {}).get(asset['name'], {}).get('ref_from')
            if ref_name:
                prev_stage_image = prev_stage_images.get(ref_name)

        prev = report['results'].get(asset['name'])
        if prev and prev.get('status') == 'pass' and not force:
            n_skip += 1
            log.asset_skip(idx, asset['name'])
            skip_image = None
            if (sprites_out / asset['file']).is_file():
                skip_image = (sprites_out / asset['file']).read_bytes()
                _register_family_anchor(family_anchors, asset, skip_image, 'pass')
                if stage_plan:
                    prev_stage_images[asset['name']] = skip_image
            if on_progress:
                on_progress(idx, total, asset['name'], {
                    'name': asset['name'], **prev, 'image': skip_image,
                })
            continue

        anchor = family_anchors.get(fam)
        if force and anchor is not None and asset['name'] == get_family_anchor_asset(fam):
            family_anchors.pop(fam, None)
            anchor = None

        log.asset_start(idx, asset['name'], asset.get('family'))
        result = generate_one(client, asset, resolved_style, style_image,
                              by_family.get(fam, []),
                              image_model, critic_model, max_iters,
                              history_dir=history_dir, log=log,
                              mode=mode, theme_text=resolved_theme, theme_plan=theme_plan,
                              family_style_plan=family_style_plan,
                              stage_plan=stage_plan,
                              family_anchor=anchor,
                              prev_stage_image=prev_stage_image,
                              reference_run=reference_run)
        image = result.pop('image')
        if image:
            (sprites_out / asset['file']).write_bytes(image)
            _register_family_anchor(family_anchors, asset, image, result['status'])
            if stage_plan and result['status'] in ('pass', 'needs_review'):
                prev_stage_images[asset['name']] = image
        report['results'][asset['name']] = result
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

        log.asset_done(result)
        n_pass += result['status'] == 'pass'
        n_review += result['status'] == 'needs_review'
        n_fail += result['status'] == 'failed'
        if on_progress:
            on_progress(idx, total, asset['name'], {**result, 'image': image})

    log.run_summary(
        n_pass=n_pass, n_review=n_review, n_fail=n_fail, n_skip=n_skip,
        run_dir=run_dir, sprites_out=sprites_out, history_dir=history_dir,
        report_path=report_path, run_name=run_name,
    )
    if not dry_run:
        sheet = write_sprite_contact_sheet(sprites_out, run_dir / 'generated_sprites.png')
        if sheet:
            print(f'[contact-sheet] {sheet}')
    return run_dir
