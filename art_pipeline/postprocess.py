"""
程式化後處理與驗證 — 不靠 LLM 的客觀檢查。

去背流程參考 Philschmid「Transparent PNG Stickers with Nano Banana」:
https://www.philschmid.de/generate-stickers
做法是讓模型把主體畫在純色 chromakey 背景(+白色描邊)上,再用 HSV 色彩空間
精準偵測並移除該背景色,比叫模型「直接輸出透明」乾淨得多。

robustness:
- chromakey 顏色按 asset 自動選:綠色主體(Grn / 綠瓶)用洋紅背景,其它用綠色背景
- 邊緣:僅移除與畫布邊緣連通的 chromakey(flood-fill)+choke,保護主體反鋸齒邊
- 內部:未連到邊界的 chromakey 島(模型用背景色填洞)一併移除
- 生圖 prompt 禁止在空洞/縫隙使用 chromakey 色
- 模型若真的輸出透明 → 直接採用;若 chromakey 偵測不到 → 退回四角同色去背
- edge cleanup 去 halo; chromakey 路徑不再額外 alpha erode
"""

from __future__ import annotations

import io
from collections import deque

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# 物件外接框至少要佔畫面面積比例(填滿畫面,不要縮在角落)
_MIN_BBOX_COVERAGE = 0.30
# 不透明像素至少要佔畫面比例(擋掉細長/稀疏的形狀)
_MIN_OPAQUE_COVERAGE = 0.18
# 退回方案:四角同色去背容差
_CORNER_TOLERANCE = 28
# flood 去背 mask 內縮像素(choke),避免吃到主體反鋸齒邊
_MATTE_CHOKE_PX = 1
# chromakey 後整體 alpha 再內縮 1px,去掉殘留色邊
_ALPHA_CHOKE_PX = 1
# candidate mask 膨脹(僅用於吃掉背景鋸齒,過大會侵蝕主體邊)
_CANDIDATE_DILATE = 1
# 內部島顏色與「實際取樣到的背景純色」的距離(sum of abs per-channel)須小於此值,
# 才算「模型拿背景色填的洞」而移除;主體本身落在同色相區間的高光/區塊(如綠西瓜)
# 距離背景純色很遠,予以保留,避免在主體上打出破洞。
_INTERIOR_BG_TOL = 60

# chromakey 設定 — 純色背景,HSV hue_center 用來偵測
CHROMAKEYS: dict[str, dict] = {
    'green':   {'hex': '#00FF00', 'rgb': (0, 255, 0),   'hue_center': 120, 'name_en': 'green'},
    'magenta': {'hex': '#FF00FF', 'rgb': (255, 0, 255), 'hue_center': 300, 'name_en': 'magenta'},
}


def chromakey_for(asset: dict) -> dict:
    """依 asset 選 chromakey 顏色。綠色主體不能用綠幕,改用洋紅幕。"""
    text = (asset.get('function', '') + ' ' + ' '.join(asset.get('constraints', []))).lower()
    name = asset.get('name', '')
    is_green_subject = (name == 'Grn' or name.endswith('_green')
                        or 'unmistakably green' in text)
    return CHROMAKEYS['magenta'] if is_green_subject else CHROMAKEYS['green']


def chromakey_forbidden_description(ck: dict) -> str:
    """Human-readable hue range the model must avoid inside the subject."""
    if ck['name_en'] == 'green':
        return (f'pure green-screen tones (hue ~95°–145°, high saturation/brightness, '
                f'including {ck["hex"]} RGB {ck["rgb"]})')
    return (f'pure magenta-screen tones (hue ~275°–325°, high saturation/brightness, '
            f'including {ck["hex"]} RGB {ck["rgb"]})')


def chromakey_generation_rules(asset: dict) -> str:
    """Chromakey background + forbidden-in-subject rules for image generation prompts."""
    ck = chromakey_for(asset)
    r, g, b = ck['rgb']
    name = ck['name_en']
    forbidden = chromakey_forbidden_description(ck)
    return (
        f"""- BACKGROUND: render the subject on a SOLID, FLAT, UNIFORM {name} background using
  EXACTLY hex {ck['hex']} (RGB {r}, {g}, {b}). The whole background must be this single pure
  color — no gradients, no shadows, no lighting effects. This background will be removed
  programmatically by chromakey, so it must be clean.
- NO OUTLINE/BORDER: do NOT add any outline, stroke, border, halo, glow or sticker frame around
  the subject (no black/white/colored ink lines). The subject must touch the {name} background
  directly with crisp, clean edges defined by shading only.
- FORBIDDEN IN SUBJECT: the subject must NEVER use {forbidden} anywhere — not on surfaces,
  highlights, leaves, gaps, cavities, holes, or negative space between parts. Use clearly
  different hues (shift hue away from the key color, lower saturation, or darken).
- NO CHROMAKEY IN GAPS: hollow areas, interior holes, gaps between limbs/parts, and negative
  space must NOT be filled with the background key color. Fill them with deep neutral shadow
  (dark grey/brown), a darker local material color, or imply emptiness — never the key color.
- SHARP EDGES: crisp, well-defined edges — no soft or blurry boundaries.""")


def _rgb_to_hsv(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """RGB(HxWx3 uint8) → (hue 0-360, sat 0-100, val 0-100)。向量化。"""
    a = rgb.astype(np.float32) / 255.0
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx = np.max(a, axis=-1)
    mn = np.min(a, axis=-1)
    d = mx - mn
    h = np.zeros_like(mx)
    nz = d != 0
    mr = (mx == r) & nz
    h[mr] = (60 * ((g[mr] - b[mr]) / d[mr]) + 360) % 360
    mg = (mx == g) & nz
    h[mg] = (60 * ((b[mg] - r[mg]) / d[mg]) + 120)
    mb = (mx == b) & nz
    h[mb] = (60 * ((r[mb] - g[mb]) / d[mb]) + 240)
    s = np.zeros_like(mx)
    s[mx != 0] = d[mx != 0] / mx[mx != 0]
    return h, s * 100.0, mx * 100.0


def _chromakey_candidate_mask(
    rgb: np.ndarray,
    hue_center: float,
    *,
    hue_range: float = 25,
    min_sat: float = 55,
    min_val: float = 55,
    dilate: int = 2,
) -> np.ndarray:
    """HSV pixels that match the chromakey color (before border flood)."""
    h, s, v = _rgb_to_hsv(rgb)
    hue_diff = np.abs(h - hue_center)
    hue_diff = np.minimum(hue_diff, 360 - hue_diff)
    mask = (hue_diff < hue_range) & (s > min_sat) & (v > min_val)
    if dilate > 0 and mask.any():
        m = Image.fromarray((mask * 255).astype(np.uint8))
        m = m.filter(ImageFilter.MaxFilter(2 * dilate + 1))
        mask = np.array(m) > 0
    return mask


def _flood_fill_from_border(candidate: np.ndarray) -> np.ndarray:
    """Pixels in candidate that are 4-connected to any image border."""
    h, w = candidate.shape
    connected = np.zeros((h, w), dtype=bool)
    q: deque[tuple[int, int]] = deque()

    def _seed(y: int, x: int) -> None:
        if candidate[y, x] and not connected[y, x]:
            connected[y, x] = True
            q.append((y, x))

    for x in range(w):
        _seed(0, x)
        _seed(h - 1, x)
    for y in range(h):
        _seed(y, 0)
        _seed(y, w - 1)

    while q:
        y, x = q.popleft()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and candidate[ny, nx] and not connected[ny, nx]:
                connected[ny, nx] = True
                q.append((ny, nx))
    return connected


def _choke_mask(mask: np.ndarray, pixels: int) -> np.ndarray:
    """Shrink a True mask inward — standard matte choke to protect subject edges."""
    if pixels <= 0 or not mask.any():
        return mask
    m = Image.fromarray((mask * 255).astype(np.uint8))
    m = m.filter(ImageFilter.MinFilter(2 * pixels + 1))
    return np.array(m) > 0


def _remove_chromakey_connected(
    im: Image.Image,
    hue_center: float,
    hue_range: float = 25,
    min_sat: float = 55,
    min_val: float = 55,
    dilate: int = _CANDIDATE_DILATE,
    choke: int = _MATTE_CHOKE_PX,
) -> tuple[Image.Image, float, float]:
    """Remove border-connected + interior chromakey islands. Returns (image, total, interior)."""
    im = im.convert('RGBA')
    data = np.array(im)
    rgb = data[..., :3]
    candidate = _chromakey_candidate_mask(
        rgb, hue_center,
        hue_range=hue_range, min_sat=min_sat, min_val=min_val, dilate=dilate,
    )
    border_connected = _flood_fill_from_border(candidate)
    interior = candidate & ~border_connected
    # 內部島只移除「顏色貼近實際背景純色」的像素(模型拿背景色填的洞)。
    # 主體本身的同色相高光/區塊距離背景純色很遠 → 保留,不在主體上打出破洞。
    if interior.any() and border_connected.any():
        bg = np.median(rgb[border_connected].astype(np.int32), axis=0)
        dist = np.abs(rgb.astype(np.int32) - bg).sum(axis=-1)
        interior = interior & (dist < _INTERIOR_BG_TOL)
    remove_mask = _choke_mask(border_connected, choke) | interior
    removed_ratio = float(remove_mask.mean())
    interior_ratio = float(interior.mean())
    alpha = data[..., 3].copy()
    alpha[remove_mask] = 0
    data[..., 3] = alpha
    return Image.fromarray(data), removed_ratio, interior_ratio


def _remove_chromakey(im: Image.Image, hue_center: float,
                      hue_range: float = 25, min_sat: float = 55, min_val: float = 55,
                      dilate: int = _CANDIDATE_DILATE) -> tuple[Image.Image, float, float]:
    """HSV chromakey 去背(邊緣 flood + 內部島)。回傳 (image, 總移除比例, 內部島比例)。"""
    return _remove_chromakey_connected(
        im, hue_center,
        hue_range=hue_range, min_sat=min_sat, min_val=min_val, dilate=dilate,
    )


def _strip_white_edge(data: np.ndarray, white_thresh: int = 205,
                      max_layers: int = 12) -> np.ndarray:
    """從邊緣逐層剝掉「貼著透明區的近白色像素」,去掉白色描邊/halo(任意厚度)。

    碰到有顏色的主體像素就停,不會吃進主體內部。就地修改並回傳 alpha。
    """
    rgb = data[..., :3].astype(int)
    alpha = data[..., 3]
    whiteish = ((rgb[..., 0] > white_thresh)
                & (rgb[..., 1] > white_thresh)
                & (rgb[..., 2] > white_thresh))
    for _ in range(max_layers):
        opaque = alpha > 16
        transparent = ~opaque
        # 把透明區膨脹 1px,找出「緊鄰透明」的不透明像素
        t_img = Image.fromarray((transparent * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))
        adj_transparent = np.array(t_img) > 0
        peel = opaque & whiteish & adj_transparent
        if not peel.any():
            break
        alpha[peel] = 0
    return alpha


def _cleanup_edges(im: Image.Image, threshold: int = 64, erode: int = 1) -> Image.Image:
    """邊緣清理:半透明 → 全透明/全不透明 → 剝掉白邊 → 輕微內縮去反鋸齒 halo。"""
    data = np.array(im.convert('RGBA'))
    alpha = data[..., 3]
    alpha[alpha < threshold] = 0
    data[..., 3] = alpha
    # 逐層剝掉白色描邊/halo(任意厚度,碰到主體顏色即止)
    data[..., 3] = _strip_white_edge(data)
    if erode > 0:
        # 再輕微內縮 1px 吃掉殘餘反鋸齒邊
        a_img = Image.fromarray(data[..., 3]).filter(ImageFilter.MinFilter(2 * erode + 1))
        data[..., 3] = np.array(a_img)
    return Image.fromarray(data)


def _frame_fill_ok(alpha: np.ndarray) -> tuple[bool, str]:
    """填滿畫面 + 非細長 的客觀檢查。回傳 (ok, 失敗訊息)。"""
    opaque = alpha > 16
    if not opaque.any():
        return False, 'Image is fully transparent (no object present)'
    ys, xs = np.where(opaque)
    bbox_cov = ((xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1)) / alpha.size
    opaque_cov = float(opaque.mean())
    if bbox_cov < _MIN_BBOX_COVERAGE:
        return False, (f'Object too small (bbox coverage {bbox_cov:.0%} '
                       f'< {_MIN_BBOX_COVERAGE:.0%}). Make it larger and fill the frame.')
    if opaque_cov < _MIN_OPAQUE_COVERAGE:
        return False, (f'Object too thin/sparse (fills {opaque_cov:.0%} of the frame '
                       f'< {_MIN_OPAQUE_COVERAGE:.0%}). Make it a chunky, compact shape that '
                       f'fills the sprite.')
    return True, ''


def preview_on_checkerboard(png_bytes: bytes, cell: int = 16) -> bytes:
    """把透明 PNG 疊到高對比洋紅/白棋盤格上。

    給 critic 看用:主體內若有透明破洞或鋸齒缺口,棋盤格會直接透出來,一眼可辨。
    """
    im = Image.open(io.BytesIO(png_bytes)).convert('RGBA')
    w, h = im.size
    yy, xx = np.mgrid[0:h, 0:w]
    checker = (((xx // cell) + (yy // cell)) % 2).astype(bool)
    bg = np.empty((h, w, 4), dtype=np.uint8)
    bg[checker] = (255, 0, 255, 255)
    bg[~checker] = (255, 255, 255, 255)
    out = Image.alpha_composite(Image.fromarray(bg, 'RGBA'), im).convert('RGB')
    buf = io.BytesIO()
    out.save(buf, format='PNG')
    return buf.getvalue()


def _corner_key(im: Image.Image) -> tuple[Image.Image, bool]:
    """退回方案:四角同色的不透明圖 → 把該色 key 成透明。回傳 (image, was_keyed)。"""
    rgba = im.convert('RGBA')
    data = np.array(rgba)
    h, w = data.shape[:2]
    corners = [data[0, 0, :3], data[0, w - 1, :3], data[h - 1, 0, :3], data[h - 1, w - 1, :3]]
    base = corners[0].astype(int)
    if not all(int(np.abs(c.astype(int) - base).sum()) < _CORNER_TOLERANCE * 3 for c in corners):
        return rgba, False
    diff = np.abs(data[..., :3].astype(int) - base).sum(axis=-1)
    mask = diff < _CORNER_TOLERANCE * 3
    data[..., 3][mask] = 0
    return Image.fromarray(data), True


def process(generated_bytes: bytes, asset: dict) -> tuple[bool, list[str], bytes | None]:
    """
    驗證 + 後處理生成圖。
    回傳 (ok, issues/warnings, processed_png_bytes)。ok=False 時 bytes 為 None。
    """
    issues: list[str] = []
    try:
        im = Image.open(io.BytesIO(generated_bytes))
        im.load()
    except Exception as e:  # noqa: BLE001
        return False, [f'Image could not be decoded: {e}'], None

    need_transparent = asset.get('transparent', True)
    im = im.convert('RGBA')

    if need_transparent:
        existing_transparent = float((np.array(im)[..., 3] < 16).mean())
        if existing_transparent >= 0.05:
            # 模型已經輸出透明背景 → 直接採用
            issues.append('model already produced transparency; kept as is')
        else:
            ck = chromakey_for(asset)
            keyed, removed, interior = _remove_chromakey(im, ck['hue_center'])
            if removed >= 0.05:
                im = _cleanup_edges(keyed, erode=_ALPHA_CHOKE_PX)
                msg = (f'background removed via {ck["name_en"]} chromakey '
                       f'({removed:.0%} of pixels)')
                if interior >= 0.005:
                    msg += f', including {interior:.0%} interior islands'
                issues.append(msg)
            else:
                # chromakey 偵測不到 → 退回四角同色去背
                im2, ok2 = _corner_key(im)
                if ok2:
                    im = _cleanup_edges(im2)
                    issues.append(f'warning: {ck["name_en"]} chromakey not detected; '
                                  f'used corner-color fallback')
                else:
                    return False, [f'Opaque background with no detectable {ck["name_en"]} '
                                   f'chromakey nor uniform corner color'], None

        # 物件佔比檢查:要填滿畫面、不要細長
        ok_fill, msg = _frame_fill_ok(np.array(im)[..., 3])
        if not ok_fill:
            return False, [msg], None

    # resize 回原始尺寸
    target = (asset['width'], asset['height'])
    if im.size != target:
        im = im.resize(target, Image.LANCZOS)

    buf = io.BytesIO()
    im.save(buf, format='PNG')
    return True, issues, buf.getvalue()


def _self_check() -> None:
    """Border flood protects edges; interior chromakey islands are keyed; real greens survive."""
    size = 256
    green = (0, 255, 0, 255)
    red = (255, 0, 0, 255)
    olive = (40, 120, 40, 255)  # subject green, not chromakey candidate

    # Case 1: red subject on green bg — background keyed, subject kept
    img1 = Image.new('RGBA', (size, size), green)
    draw1 = ImageDraw.Draw(img1)
    draw1.ellipse((64, 64, 192, 192), fill=red)
    out1, ratio1, _ = _remove_chromakey_connected(img1, CHROMAKEYS['green']['hue_center'])
    data1 = np.array(out1)
    assert ratio1 > 0.2
    assert data1[128, 128, 3] > 200  # center of red circle opaque

    # Case 2: chromakey-filled interior hole inside subject — hole keyed out
    img2 = Image.new('RGBA', (size, size), green)
    draw2 = ImageDraw.Draw(img2)
    draw2.ellipse((48, 48, 208, 208), fill=red)
    draw2.ellipse((96, 96, 160, 160), fill=green)
    out2, _, interior2 = _remove_chromakey_connected(img2, CHROMAKEYS['green']['hue_center'])
    data2 = np.array(out2)
    assert interior2 > 0.01
    assert data2[128, 128, 3] < 16   # interior chromakey hole transparent
    assert data2[0, 0, 3] < 16       # corner background transparent

    # Case 2b: non-chromakey green inside subject — kept
    img2b = Image.new('RGBA', (size, size), green)
    draw2b = ImageDraw.Draw(img2b)
    draw2b.ellipse((48, 48, 208, 208), fill=red)
    draw2b.ellipse((96, 96, 160, 160), fill=olive)
    out2b, _, _ = _remove_chromakey_connected(img2b, CHROMAKEYS['green']['hue_center'])
    data2b = np.array(out2b)
    assert data2b[128, 128, 3] > 200

    # Case 3: yellow subject on green bg — edge should not develop interior holes
    img3 = Image.new('RGBA', (size, size), green)
    draw3 = ImageDraw.Draw(img3)
    draw3.ellipse((72, 72, 184, 184), fill=(255, 220, 0, 255))
    out3, _, _ = _remove_chromakey_connected(img3, CHROMAKEYS['green']['hue_center'])
    data3 = np.array(out3)
    assert data3[128, 128, 3] > 200
    # left edge column near mid-height should stay mostly opaque (no bite notch)
    assert data3[96:160, 80, 3].mean() > 180

    # Case 4: subject-colored green highlight island (same hue as key, NOT pure key)
    # must survive — this is the watermelon-hole regression guard.
    img4 = Image.new('RGBA', (size, size), green)
    draw4 = ImageDraw.Draw(img4)
    draw4.ellipse((48, 48, 208, 208), fill=red)
    draw4.ellipse((104, 104, 152, 152), fill=(120, 230, 60, 255))  # in-key-hue highlight
    out4, _, _ = _remove_chromakey_connected(img4, CHROMAKEYS['green']['hue_center'])
    data4 = np.array(out4)
    assert data4[128, 128, 3] > 200  # highlight kept, no hole punched into subject

    # Case 4b: composite-on-checkerboard preview keeps the same pixel dimensions
    buf4 = io.BytesIO()
    out4.save(buf4, format='PNG')
    prev = Image.open(io.BytesIO(preview_on_checkerboard(buf4.getvalue())))
    assert prev.size == (size, size)

    # Case 5: frame-fill guard — chunky centered object passes, thin sliver fails
    a_full = np.zeros((size, size), np.uint8)
    a_full[40:216, 40:216] = 255  # fills ~47% of frame
    assert _frame_fill_ok(a_full)[0]
    a_thin = np.zeros((size, size), np.uint8)
    a_thin[:, 120:136] = 255       # tall thin sliver, ~6% opaque
    assert not _frame_fill_ok(a_thin)[0]
    a_tiny = np.zeros((size, size), np.uint8)
    a_tiny[8:40, 8:40] = 255       # small object in a corner
    assert not _frame_fill_ok(a_tiny)[0]


if __name__ == '__main__':
    _self_check()
    print('postprocess self-check ok')
