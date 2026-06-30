"""Labeled grid contact sheet for a run's sprites/ folder."""

from __future__ import annotations

import pathlib

from PIL import Image, ImageDraw, ImageFont

_COLS = 8
_CELL = 200
_PAD = 12
_LABEL_H = 22
_BG = (32, 34, 40, 255)
_FG = (235, 235, 235)


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        '/System/Library/Fonts/Supplemental/Arial.ttf',
        '/System/Library/Fonts/Helvetica.ttc',
        '/Library/Fonts/Arial.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    ):
        p = pathlib.Path(path)
        if p.is_file():
            try:
                return ImageFont.truetype(str(p), size)
            except OSError:
                pass
    return ImageFont.load_default()


def write_sprite_contact_sheet(
    sprites_dir: pathlib.Path,
    out_path: pathlib.Path | None = None,
    *,
    cols: int = _COLS,
    cell: int = _CELL,
) -> pathlib.Path | None:
    """
    Arrange all PNGs in sprites_dir into one labeled grid image.
    Returns output path, or None if sprites_dir has no PNGs.
    """
    sprites_dir = pathlib.Path(sprites_dir)
    out_path = out_path or sprites_dir.parent / 'generated_sprites.png'
    files = sorted(sprites_dir.glob('*.png'))
    if not files:
        return None

    font = _load_font(13)
    n = len(files)
    rows = (n + cols - 1) // cols
    cell_w = cell + _PAD * 2
    cell_h = cell + _LABEL_H + _PAD * 2
    sheet = Image.new('RGBA', (cols * cell_w, rows * cell_h), _BG)
    draw = ImageDraw.Draw(sheet)

    for i, path in enumerate(files):
        r, c = divmod(i, cols)
        x0, y0 = c * cell_w, r * cell_h
        try:
            img = Image.open(path).convert('RGBA')
        except OSError:
            continue
        img.thumbnail((cell, cell), Image.LANCZOS)
        ix = x0 + _PAD + (cell - img.width) // 2
        iy = y0 + _PAD + (cell - img.height) // 2
        sheet.alpha_composite(img, (ix, iy))

        name = path.stem
        label = name
        while draw.textlength(label, font=font) > cell and len(label) > 3:
            label = label[:-2]
        if label != name:
            label = label[:-1] + '\u2026'
        tw = draw.textlength(label, font=font)
        draw.text((x0 + (cell_w - tw) // 2, y0 + _PAD + cell + 3), label, fill=_FG, font=font)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert('RGB').save(out_path)
    return out_path


if __name__ == '__main__':
    import sys
    import tempfile

    td = pathlib.Path(tempfile.mkdtemp())
    for stem, color in (('Red', (255, 0, 0)), ('Grn', (0, 200, 0))):
        Image.new('RGBA', (64, 64), color + (255,)).save(td / f'{stem}.png')
    out = write_sprite_contact_sheet(td, td / 'sheet.png')
    assert out and out.is_file()
    print('sprite_sheet self-check ok')
