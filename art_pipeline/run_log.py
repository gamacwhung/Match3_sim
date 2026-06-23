"""
終端機簡易 UI — 生成 run 的進度與結果 log。
純文字、無額外依賴,適合 CLI 與 shell script 重導向。
"""

from __future__ import annotations

import pathlib
import re
import sys
from typing import Any


def _supports_color() -> bool:
    return sys.stdout.isatty() and (
        getattr(sys.stdout, 'encoding', None) or ''
    ).lower().replace('-', '') in ('utf8', 'utf_8')


class _C:
    RESET = '\033[0m'
    DIM = '\033[2m'
    BOLD = '\033[1m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    RED = '\033[31m'
    CYAN = '\033[36m'
    BLUE = '\033[34m'


def _c(code: str, text: str) -> str:
    if not _supports_color():
        return text
    return f'{code}{text}{_C.RESET}'


def _bar(done: int, total: int, width: int = 20) -> str:
    if total <= 0:
        return '[' + ' ' * width + ']'
    filled = round(width * done / total)
    return '[' + '█' * filled + '░' * (width - filled) + ']'


def _box(title: str, lines: list[str], width: int = 52) -> None:
    inner = width - 4

    def _fit(text: str) -> str:
        plain = re.sub(r'\033\[[0-9;]*m', '', text)
        if len(plain) <= inner:
            return text.ljust(inner)
        # 保留 ANSI 前綴,截斷可見文字
        m = re.match(r'^(\033\[[0-9;]*m)*', text)
        prefix = m.group(0) if m else ''
        suffix = _C.RESET if prefix and _supports_color() else ''
        visible = re.sub(r'\033\[[0-9;]*m', '', text)
        return prefix + visible[: inner - 1] + '…' + suffix

    print('┌' + '─' * (width - 2) + '┐')
    print(f'│ {_c(_C.BOLD, title.ljust(inner))} │')
    print('├' + '─' * (width - 2) + '┤')
    for line in lines:
        print(f'│ {_fit(line)} │')
    print('└' + '─' * (width - 2) + '┘')


class RunLog:
    """一次 generate run 的 log 輸出。"""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._asset_idx = 0
        self._asset_total = 0

    def _print(self, *args, **kwargs) -> None:
        if self.enabled:
            print(*args, **kwargs)

    def run_header(self, *, run_name: str, style: str, image_model: str, critic_model: str,
                   max_iters: int, targets: list[dict], run_dir: pathlib.Path,
                   style_image_path: pathlib.Path | None, dry_run: bool = False,
                   reference_run: str | None = None) -> None:
        names = [a['name'] for a in targets]
        if len(names) <= 6:
            assets_line = ', '.join(names)
        else:
            assets_line = f'{len(names)} 張 ({", ".join(names[:4])}, …)'

        mode = _c(_C.YELLOW, 'DRY-RUN') if dry_run else _c(_C.CYAN, 'GENERATE')
        ref = str(style_image_path) if style_image_path else _c(_C.DIM, '(無)')
        ref_a = reference_run if reference_run else _c(_C.DIM, 'official sprites')
        style_line = style if len(style) <= 42 else style[:39] + '…'
        lines = [
            f'mode     {mode}',
            f'run      {run_name}',
            f'style    {style_line}',
            f'model    img {image_model}',
            f'         crt {critic_model}',
            f'iters    ≤{max_iters} / asset',
            f'assets   {assets_line}',
            f'ref A    {ref_a}',
            f'ref B    {ref}',
            f'output   {run_dir}',
        ]
        _box('AI Art Generation', lines)
        self._asset_total = len(targets)

    def asset_skip(self, idx: int, name: str) -> None:
        self._print(f'\n{_bar(idx - 1, self._asset_total)} {_c(_C.DIM, f"[{idx}/{self._asset_total}] {name}  — 已 pass,跳過")}')

    def asset_start(self, idx: int, name: str, family: str | None) -> None:
        self._asset_idx = idx
        fam = f'  {_c(_C.DIM, f"[{family}]")}' if family else ''
        self._print(f'\n{_bar(idx - 1, self._asset_total)} {_c(_C.BOLD, f"[{idx}/{self._asset_total}] {name}")}{fam}')

    def iter_start(self, i: int, max_iters: int) -> None:
        self._print(f'  ├─ iter {i}/{max_iters}  generating…')

    def iter_error(self, i: int, stage: str, error: str) -> None:
        short = error if len(error) <= 60 else error[:57] + '…'
        self._print(f'  │  {_c(_C.RED, "✗")} {stage}  {_c(_C.DIM, short)}')

    def iter_postprocess_fail(self, i: int, issues: list[str]) -> None:
        msg = issues[0] if issues else 'postprocess failed'
        if len(msg) > 50:
            msg = msg[:47] + '…'
        self._print(f'  │  {_c(_C.YELLOW, "✗")} postprocess  {_c(_C.DIM, msg)}')

    def iter_critique(self, i: int, elapsed: float, verdict: dict, score: int,
                      passed: bool, has_style_image: bool) -> None:
        style = verdict.get('style_score', '?')
        func = verdict.get('function_score', '?')
        bg = '✓' if verdict.get('background_ok') else '✗'
        parts = [f'style {style}', f'fn {func}', f'bg {bg}', f'score {score}']
        if has_style_image:
            parts.insert(2, f'ref {verdict.get("reference_element_score", "?")}')
        detail = '  '.join(parts)
        tag = _c(_C.GREEN, 'pass') if passed else _c(_C.YELLOW, verdict.get('verdict', 'retry'))
        self._print(f'  │  iter {i}  {tag}  {_c(_C.DIM, detail)}  ({elapsed:.1f}s)')

    def asset_done(self, result: dict) -> None:
        status = result['status']
        icons = {'pass': '✅', 'needs_review': '🟡', 'failed': '❌'}
        labels = {'pass': 'PASS', 'needs_review': 'NEEDS REVIEW', 'failed': 'FAILED'}
        icon = icons.get(status, '•')
        label = labels.get(status, status.upper())
        v = result.get('verdict') or {}
        chosen = result.get('chosen_iter')
        iters = result.get('iters', '?')
        extra = ''
        if v:
            extra = (f'  style {v.get("style_score", "?")}  '
                     f'fn {v.get("function_score", "?")}  '
                     f'iter {chosen or iters}')
        color = {'pass': _C.GREEN, 'needs_review': _C.YELLOW, 'failed': _C.RED}.get(status, '')
        self._print(f'  └─ {icon} {_c(color, label)}{extra}')

    def run_summary(self, *, n_pass: int, n_review: int, n_fail: int, n_skip: int,
                    run_dir: pathlib.Path, sprites_out: pathlib.Path,
                    history_dir: pathlib.Path, report_path: pathlib.Path,
                    run_name: str) -> None:
        total = n_pass + n_review + n_fail + n_skip
        lines = [
            f'{"✅ pass":12s} {n_pass}',
            f'{"🟡 review":12s} {n_review}',
            f'{"❌ failed":12s} {n_fail}',
            f'{"⏭ skip":12s} {n_skip}',
            f'{"total":12s} {total}',
            '',
            f'sprites  {sprites_out}',
            f'history  {history_dir}/<asset>/',
            f'report   {report_path}',
            '',
            f'apply    python scripts/ai_art_gen.py apply --run {run_name}',
        ]
        _box('Run Complete', lines)

    def dry_run_targets(self, targets: list[dict]) -> None:
        self._print(f'\n將生成 {len(targets)} 張 asset:\n')
        for a in targets:
            fam = a.get('family') or 'misc'
            self._print(f'  • {a["name"]:28s} {a["width"]:>4}x{a["height"]:<4}  [{fam}]')
        self._print()

    def dry_run_prompt(self, prompt: str) -> None:
        self._print(_c(_C.DIM, '─' * 50))
        self._print(_c(_C.BOLD, '範例 prompt (第一張):'))
        self._print(_c(_C.DIM, '─' * 50))
        self._print(prompt)
        self._print()
