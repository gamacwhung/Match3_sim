"""
程式化後處理與驗證 — 不靠 LLM 的客觀檢查。

去背流程參考 Philschmid「Transparent PNG Stickers with Nano Banana」:
https://www.philschmid.de/generate-stickers
做法是讓模型把主體畫在純色 chromakey 背景(+白色描邊)上,再用 HSV 色彩空間
精準偵測並移除該背景色,比叫模型「直接輸出透明」乾淨得多。

robustness:
- chromakey 顏色按 asset 自動選:綠色主體(Grn / 綠瓶)用洋紅背景,其它用綠色背景,
  避免把主體本身的顏色一起 key 掉
- 模型若真的輸出透明 → 直接採用;若 chromakey 偵測不到 → 退回四角同色去背
- HSV mask 用 PIL MaxFilter 膨脹以吃掉反鋸齒邊緣,再做 edge cleanup 去 halo
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageFilter

# 物件至少要佔畫面面積比例
_MIN_BBOX_COVERAGE = 0.15
# 退回方案:四角同色去背容差
_CORNER_TOLERANCE = 28

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


def _remove_chromakey(im: Image.Image, hue_center: float,
                      hue_range: float = 25, min_sat: float = 55, min_val: float = 55,
                      dilate: int = 2) -> tuple[Image.Image, float]:
    """HSV chromakey 去背。回傳 (image, 被移除像素比例)。"""
    im = im.convert('RGBA')
    data = np.array(im)
    h, s, v = _rgb_to_hsv(data[..., :3])
    hue_diff = np.abs(h - hue_center)
    hue_diff = np.minimum(hue_diff, 360 - hue_diff)
    mask = (hue_diff < hue_range) & (s > min_sat) & (v > min_val)
    if dilate > 0 and mask.any():
        # 膨脹 mask 吃掉反鋸齒邊緣(用 PIL MaxFilter,免 scipy 依賴)
        m = Image.fromarray((mask * 255).astype(np.uint8))
        m = m.filter(ImageFilter.MaxFilter(2 * dilate + 1))
        mask = np.array(m) > 0
    removed_ratio = float(mask.mean())
    alpha = data[..., 3].copy()
    alpha[mask] = 0
    data[..., 3] = alpha
    return Image.fromarray(data), removed_ratio


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
            keyed, removed = _remove_chromakey(im, ck['hue_center'])
            if removed >= 0.05:
                im = _cleanup_edges(keyed)
                issues.append(f'background removed via {ck["name_en"]} chromakey '
                              f'({removed:.0%} of pixels)')
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

        # 物件佔比檢查
        bbox = im.getchannel('A').getbbox()
        if bbox is None:
            return False, ['Image is fully transparent after background removal (no object present)'], None
        coverage = ((bbox[2] - bbox[0]) * (bbox[3] - bbox[1])) / (im.width * im.height)
        if coverage < _MIN_BBOX_COVERAGE:
            return False, [f'Object too small (bbox coverage {coverage:.0%} '
                           f'< {_MIN_BBOX_COVERAGE:.0%})'], None

    # resize 回原始尺寸
    target = (asset['width'], asset['height'])
    if im.size != target:
        im = im.resize(target, Image.LANCZOS)

    buf = io.BytesIO()
    im.save(buf, format='PNG')
    return True, issues, buf.getvalue()
