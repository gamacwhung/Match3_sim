"""
Tile ID → M8 美術 PNG 對應表

ASSET_SOURCES：對應到 M8/ 內的原始檔案路徑（給 build_assets.py 複製用）
ASSET_TRANSFORMS：複製時要對 PNG 套用的轉換（例如 rotate）
RUNTIME_RESOLVER：執行時依 tile_id + hp 解析出 image_key（給 Python wrapper 用）
"""

# (tile_id, asset_key) → M8 相對路徑
# asset_key 是 frontend/assets/ 下的檔名（不含 .png）
# 一個 asset_key 對應一張圖；多個 tile 可共用同一張
ASSET_SOURCES = {
    # ---- 元素 ----
    'Red': '基本4元素/帽子/red.png',
    'Grn': '基本4元素/背包/green.png',
    'Blu': '基本4元素/水壺/blue.png',
    'Yel': '基本4元素/相機/yellow.png',
    'Pur': '障礙物/025_彩色紙箱/ColorBox_purple/ColorBox_purple_body_lv1.png',
    # 'Brn' 沒有合適的 M8 替代，runtime 走 CSS fallback

    # ---- 道具 ----
    'Soda0d': '盤內道具013-018/013-014_汽水瓶火箭/SodaRocket.png',
    # Soda90 = SodaRocket 旋轉 90 度。共用同一張，frontend 端 CSS rotate
    'TNT': '盤內道具013-018/016_氣球炸彈/BlnTNT.png',
    'TrPr': '盤內道具013-018/015_三葉圓盤迴旋鏢/TriPropeller.png',
    'LtBl': '盤內道具013-018/017_七彩光球/LightBall.png',

    # ---- 紙箱 ----
    'Crt1': '障礙物/001_紙箱/Carton_body_lv1.png',
    'Crt2': '障礙物/001_紙箱/Carton_body_lv2.png',
    'Crt3': '障礙物/001_紙箱/Carton_body_lv3.png',
    'Crt4': '障礙物/001_紙箱/Carton_body_lv4.png',

    # ---- 水漥（bottom）----
    'Puddle_lv1': '障礙物/002_水漥/Puddle_lv1.png',
    'Puddle_lv2': '障礙物/002_水漥/Puddle_lv2.png',

    # ---- 木桶 ----
    'Barrel': '障礙物/003_木桶/Barrel.png',

    # ---- 礦泉水櫃（lv1~10 為開門逐血量，lv11 為關門）----
    'WaterChiller_closed': '障礙物/004_礦泉水櫃/WaterChiller_lv11.png',
    **{f'WaterChiller_lv{i}': f'障礙物/004_礦泉水櫃/WaterChiller_lv{i}.png'
       for i in range(1, 11)},

    # ---- 印章 ----
    'Stamp': '障礙物/005_郵戳印章/Postmark_img.png',

    # ---- 交通錐 ----
    'TrafficCone_lv1': '障礙物/006_交通錐/TrafficCone_lv1.png',
    'TrafficCone_lv2': '障礙物/006_交通錐/TrafficCone_lv2.png',

    # ---- 飲料櫃（lv1~4 為開門 hp4→1，lv5 為關門）----
    'BeverageChiller_closed': '障礙物/007_飲料櫃/BaverageChiller_lv5.png',
    'BeverageChiller_open_lv1': '障礙物/007_飲料櫃/BaverageChiller_lv1.png',
    'BeverageChiller_open_lv2': '障礙物/007_飲料櫃/BaverageChiller_lv2.png',
    'BeverageChiller_open_lv3': '障礙物/007_飲料櫃/BaverageChiller_lv3.png',
    'BeverageChiller_open_lv4': '障礙物/007_飲料櫃/BaverageChiller_lv4.png',

    # ---- 鮭魚罐頭 ----
    'SalmonCan': '障礙物/009_鮭魚罐頭/SalmonCan_body.png',

    # ---- 充氣游泳池 ----
    'Pool_lv1': '障礙物/010_充氣游泳池/Pool_lv1.png',
    'Pool_lv2': '障礙物/010_充氣游泳池/Pool_lv2.png',
    'Pool_lv3': '障礙物/010_充氣游泳池/Pool_lv3.png',
    'Pool_lv4': '障礙物/010_充氣游泳池/Pool_lv4.png',
    'Pool_lv5': '障礙物/010_充氣游泳池/Pool_lv5.png',

    # ---- 繩索（upper）----
    'Rope_lv1': '障礙物/011_繩索/Rope_lv1.png',
    'Rope_lv2': '障礙物/011_繩索/Rope_lv2.png',

    # ---- 泥巴（upper）----
    'Mud': '障礙物/012_泥巴/Mud.png',
}


# CSS fallback 顏色（找不到圖時用）
CSS_FALLBACK = {
    'Red': '#FF4444',
    'Grn': '#44BB44',
    'Blu': '#4488FF',
    'Yel': '#FFCC00',
    'Pur': '#AA44CC',
    'Brn': '#886644',
}


def resolve_image_key(tile_id, hp=1):
    """
    把 (tile_id, hp) 轉換為 frontend/assets/ 下對應的 asset_key。
    回傳 None 表示沒有對應圖（component 會走 CSS fallback）。
    """
    if tile_id is None:
        return None

    # BeverageChiller_open 依 hp 顯示不同等級
    if tile_id == 'BeverageChiller_open':
        lv = max(1, min(4, hp or 1))
        return f'BeverageChiller_open_lv{lv}'

    # Puddle lv3+ 退到 lv2 圖
    if tile_id.startswith('Puddle_lv'):
        try:
            lv = int(tile_id.split('lv')[-1])
            if lv > 2:
                return 'Puddle_lv2'
        except ValueError:
            pass

    # 直接查表
    if tile_id in ASSET_SOURCES:
        return tile_id

    return None
