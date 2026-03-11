"""
物件定義與障礙物配置（資料驅動）

所有物件的屬性都在 TILE_REGISTRY 中定義，包括：
  category        - 分類 (element/powerup/obstacle/modifier)
  layer           - 所在層 (bottom/middle/upper)
  movement        - 盤面運動 (fixed/movable)
  health          - 生命值
  elimination_type - 消除類型 (single/multi/mixed)
  can_adjacent_elim - 可否被鄰邊消除
  can_prop_elim     - 可否被道具消除
  can_inplace_elim  - 可否被原地消除
  blocks_fall       - 是否阻擋重力下落
  color             - 顏色 (僅元素)
"""

# ---------------------------------------------------------------------------
# 顏色定義
# ---------------------------------------------------------------------------
COLORS = ['Red', 'Grn', 'Blu', 'Yel', 'Pur', 'Brn']
DEFAULT_NUM_COLORS = 4  # 預設使用前 4 色

# ---------------------------------------------------------------------------
# 道具 ID 集合
# ---------------------------------------------------------------------------
POWERUP_IDS = {'Soda0d', 'Soda90', 'TNT', 'TrPr', 'LtBl'}

# ---------------------------------------------------------------------------
# 物件註冊表
# ---------------------------------------------------------------------------
TILE_REGISTRY = {}


def _reg(tile_id, **kwargs):
    """註冊一個物件定義到 TILE_REGISTRY"""
    defaults = {
        'category': 'obstacle',
        'layer': 'middle',
        'movement': 'fixed',
        'health': 1,
        'elimination_type': 'single',
        'can_adjacent_elim': True,
        'can_prop_elim': True,
        'can_inplace_elim': False,
        'blocks_fall': True,
        'color': None,
    }
    defaults.update(kwargs)
    TILE_REGISTRY[tile_id] = defaults


# ======================== 基本元素 ========================
for _color in COLORS:
    _reg(_color,
         category='element',
         movement='movable',
         health=1,
         elimination_type='single',
         can_adjacent_elim=False,   # 元素不是被「鄰邊消除」的對象
         can_prop_elim=True,
         can_inplace_elim=False,
         blocks_fall=False,
         color=_color)

# ======================== 道具 ========================
# 火箭（水平方向）
_reg('Soda0d',
     category='powerup', movement='movable', health=1,
     can_adjacent_elim=False, blocks_fall=False, color=None)
# 火箭（垂直方向）
_reg('Soda90',
     category='powerup', movement='movable', health=1,
     can_adjacent_elim=False, blocks_fall=False, color=None)
# 炸彈
_reg('TNT',
     category='powerup', movement='movable', health=1,
     can_adjacent_elim=False, blocks_fall=False, color=None)
# 紙飛機（螺旋槳）
_reg('TrPr',
     category='powerup', movement='movable', health=1,
     can_adjacent_elim=False, blocks_fall=False, color=None)
# 紙風車（光球）
_reg('LtBl',
     category='powerup', movement='movable', health=1,
     can_adjacent_elim=False, blocks_fall=False, color=None)

# ======================== 障礙物 — 紙箱 (Crt1~4) ========================
for _lv in range(1, 5):
    _reg(f'Crt{_lv}',
         health=_lv,
         can_adjacent_elim=True, can_prop_elim=True, can_inplace_elim=False)

# ======================== 障礙物 — 水漥 (Puddle) ========================
for _lv in range(1, 6):
    _reg(f'Puddle_lv{_lv}',
         layer='bottom', health=_lv,
         can_adjacent_elim=False, can_prop_elim=True, can_inplace_elim=True,
         blocks_fall=False)

# ======================== 障礙物 — 木桶 (Barrel) ========================
_reg('Barrel',
     movement='movable', health=1,
     can_adjacent_elim=True, can_prop_elim=True,
     blocks_fall=False)

# ======================== 障礙物 — 交通錐 (TrafficCone) ========================
_reg('TrafficCone_lv1',
     movement='movable', health=1,
     can_adjacent_elim=True, can_prop_elim=True,
     blocks_fall=False)
_reg('TrafficCone_lv2',
     movement='movable', health=2,
     can_adjacent_elim=True, can_prop_elim=True,
     blocks_fall=False)

# ======================== 障礙物 — 罐頭 (SalmonCan) ========================
_reg('SalmonCan',
     health=1,
     can_adjacent_elim=False, can_prop_elim=True,  # 只能道具消除
     can_inplace_elim=False)

# ======================== 障礙物 — 礦泉水櫃 (WaterChiller) ========================
# 關門狀態（單次消除打開）
_reg('WaterChiller_closed',
     health=1, elimination_type='single',
     can_adjacent_elim=True, can_prop_elim=True)
# 開門狀態（多次消除，每格傷害都算）
for _lv in range(1, 11):
    _reg(f'WaterChiller_lv{_lv}',
         health=_lv, elimination_type='multi',
         can_adjacent_elim=True, can_prop_elim=True)

# ======================== 障礙物 — 飲料櫃 (BeverageChiller) ========================
# 關門狀態
_reg('BeverageChiller_closed',
     health=1, elimination_type='single',
     can_adjacent_elim=True, can_prop_elim=True)
# 開門狀態（需要對應顏色）
_reg('BeverageChiller_open',
     health=4, elimination_type='single',
     can_adjacent_elim=True, can_prop_elim=True)

# ======================== 障礙物 — 繩索 (Rope) ========================
for _lv in range(1, 3):
    _reg(f'Rope_lv{_lv}',
         category='modifier', layer='upper',
         health=_lv,
         can_adjacent_elim=False, can_prop_elim=True, can_inplace_elim=True,
         blocks_fall=False)

# ======================== 障礙物 — 泥巴 (Mud) ========================
_reg('Mud',
     category='modifier', layer='upper',
     health=1,
     can_adjacent_elim=True, can_prop_elim=True,
     blocks_fall=False)

# ======================== 障礙物 — 充氣游泳池 (Pool) ========================
for _lv in range(1, 6):
    _reg(f'Pool_lv{_lv}',
         health=_lv,
         can_adjacent_elim=True, can_prop_elim=True)

# ======================== 障礙物 — 郵戳印章 (Stamp) ========================
# 製造機：受消除時不會被消除，而是生產明信片（通關目標）
# health 設為高值（不可消除），消除次數由關卡目標控制
_reg('Stamp',
     category='manufacturer',
     health=9999,
     elimination_type='multi',
     can_adjacent_elim=True, can_prop_elim=True)

# ---------------------------------------------------------------------------
# 紙飛機優先級權重表（決定飛行目標）
# ---------------------------------------------------------------------------
TRPR_TARGET_WEIGHTS = {
    'element': 1,
    'powerup': 0,
    'Crt': 10,
    'Rope': 10,
    'Puddle': 10,
    'Barrel': 10,
    'TrafficCone': 10,
    'SalmonCan': 10,
    'WaterChiller': 10,
    'BeverageChiller': 10,
    'Pool': 10,
    'Mud': 10,
    'Stamp': 10,
}
TRPR_GOAL_BONUS = 100   # 物件為通關目標時 +100
TRPR_LAST_HIT_BONUS = 1  # 物件血量=1 時 +1

# ---------------------------------------------------------------------------
# 查詢輔助函數
# ---------------------------------------------------------------------------

def get_def(tile_id: str) -> dict:
    """取得物件定義，若不存在回傳 None"""
    if tile_id in TILE_REGISTRY:
        return TILE_REGISTRY[tile_id]
    # 嘗試前綴匹配（如 Crt3 匹配不到時用 Crt1 作為 fallback）
    for key in TILE_REGISTRY:
        if tile_id.startswith(key):
            return TILE_REGISTRY[key]
    return None


def is_element(tile_id: str) -> bool:
    d = get_def(tile_id)
    return d is not None and d['category'] == 'element'


def is_powerup(tile_id: str) -> bool:
    return tile_id in POWERUP_IDS


def is_obstacle(tile_id: str) -> bool:
    d = get_def(tile_id)
    return d is not None and d['category'] == 'obstacle'


def is_movable(tile_id: str) -> bool:
    d = get_def(tile_id)
    return d is not None and d['movement'] == 'movable'


def can_adjacent_elim(tile_id: str) -> bool:
    d = get_def(tile_id)
    return d is not None and d.get('can_adjacent_elim', False)


def can_prop_elim(tile_id: str) -> bool:
    d = get_def(tile_id)
    return d is not None and d.get('can_prop_elim', False)


def can_inplace_elim(tile_id: str) -> bool:
    d = get_def(tile_id)
    return d is not None and d.get('can_inplace_elim', False)


def blocks_fall(tile_id: str) -> bool:
    d = get_def(tile_id)
    return d is not None and d.get('blocks_fall', True)


def get_color(tile_id: str):
    d = get_def(tile_id)
    if d is None:
        return None
    return d.get('color')
