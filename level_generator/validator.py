"""
關卡 JSON 驗證器

驗證生成的關卡是否符合格式規範並可被遊戲引擎載入。
"""

import sys
import os
import re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import dataclass, field
from tile_defs import TILE_REGISTRY, get_def, is_element


@dataclass
class ValidationResult:
    valid: bool = True
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def validate_level(level_dict: dict) -> ValidationResult:
    """驗證關卡 dict，回傳 ValidationResult"""
    result = ValidationResult()
    _check_required_fields(level_dict, result)
    if not result.errors:  # 只有基本欄位正確才繼續
        _check_board_dimensions(level_dict, result)
        _check_tile_names(level_dict, result)
        _check_layer_assignments(level_dict, result)
        _check_goal_consistency(level_dict, result)
        _check_warnings(level_dict, result)
    result.valid = len(result.errors) == 0
    return result


def _check_required_fields(d: dict, result: ValidationResult):
    for field_name in ('rows', 'cols', 'max_steps', 'goals'):
        if field_name not in d:
            result.errors.append(f'缺少必填欄位: {field_name}')

    if 'rows' in d and not isinstance(d['rows'], int):
        result.errors.append('rows 必須是整數')
    if 'cols' in d and not isinstance(d['cols'], int):
        result.errors.append('cols 必須是整數')
    if 'max_steps' in d:
        if not isinstance(d['max_steps'], int) or d['max_steps'] <= 0:
            result.errors.append('max_steps 必須是正整數')
    if 'goals' in d:
        if not isinstance(d['goals'], dict) or len(d['goals']) == 0:
            result.errors.append('goals 必須是非空的 dict')
    if 'rows' in d and isinstance(d['rows'], int):
        if not (4 <= d['rows'] <= 20):
            result.warnings.append(f'rows={d["rows"]} 不在建議範圍 4-20')
    if 'cols' in d and isinstance(d['cols'], int):
        if not (4 <= d['cols'] <= 15):
            result.warnings.append(f'cols={d["cols"]} 不在建議範圍 4-15')


def _check_board_dimensions(d: dict, result: ValidationResult):
    board = d.get('board')
    if board is None:
        return  # 不提供盤面是合法的（隨機）

    rows, cols = d['rows'], d['cols']

    def _check_2d(layer_data, layer_name):
        if not isinstance(layer_data, list):
            result.errors.append(f'{layer_name} 必須是二維陣列')
            return
        if len(layer_data) != rows:
            result.errors.append(
                f'{layer_name} 行數 {len(layer_data)} 與 rows={rows} 不符'
            )
        for i, row in enumerate(layer_data):
            if not isinstance(row, list):
                result.errors.append(f'{layer_name}[{i}] 必須是陣列')
                continue
            if len(row) != cols:
                result.errors.append(
                    f'{layer_name}[{i}] 列數 {len(row)} 與 cols={cols} 不符'
                )

    if isinstance(board, list):
        _check_2d(board, 'board')
    elif isinstance(board, dict):
        for layer_name in ('middle', 'bottom', 'upper'):
            layer_data = board.get(layer_name)
            if layer_data is not None:
                _check_2d(layer_data, f'board.{layer_name}')
    else:
        result.errors.append('board 必須是陣列或 dict')


def _parse_raw_id(raw_id: str):
    """解析 tile_id，去除 #N 實例標記"""
    if '#' in raw_id:
        return raw_id.rsplit('#', 1)[0]
    return raw_id


def _tile_family(raw_id) -> str:
    """tile_id → 家族名：取第一個底線前的字再去尾端數字。
    Crt1/Crt4→Crt、Puddle_lv1→Puddle、WaterChiller_closed/_lv5→WaterChiller、
    BeverageChiller_bottle_red→BeverageChiller、SalmonCan_top1→SalmonCan、Barrel→Barrel"""
    s = _parse_raw_id(str(raw_id))
    s = s.split('_', 1)[0]      # 去複合後綴（_closed/_lv5/_body/_top1…）
    s = re.sub(r'\d+$', '', s)  # Crt1 → Crt
    return s


def _check_tile_names(d: dict, result: ValidationResult):
    """所有非 null 的 tile_id 必須在 TILE_REGISTRY 中"""
    board = d.get('board')
    if board is None:
        return

    def _scan_layer(layer_data, layer_name):
        if not isinstance(layer_data, list):
            return
        for r, row in enumerate(layer_data):
            if not isinstance(row, list):
                continue
            for c, raw_id in enumerate(row):
                if raw_id is None or raw_id == 'void':
                    continue
                tile_id = _parse_raw_id(raw_id)
                defn = get_def(tile_id)
                if defn is None:
                    result.errors.append(
                        f'未知 tile_id "{tile_id}" 在 {layer_name}[{r}][{c}]'
                    )

    if isinstance(board, list):
        _scan_layer(board, 'board')
    elif isinstance(board, dict):
        for layer_name in ('middle', 'bottom', 'upper'):
            layer_data = board.get(layer_name)
            if layer_data is not None:
                _scan_layer(layer_data, f'board.{layer_name}')


def _check_layer_assignments(d: dict, result: ValidationResult):
    """驗證 tile 是否放在正確的層"""
    board = d.get('board')
    if not isinstance(board, dict):
        return  # 簡單陣列格式不做層級檢查

    # middle 層：不應有 Puddle 或 Rope/Mud
    middle_data = board.get('middle', [])
    if isinstance(middle_data, list):
        for r, row in enumerate(middle_data):
            if not isinstance(row, list):
                continue
            for c, raw_id in enumerate(row):
                if raw_id is None or raw_id == 'void':
                    continue
                tile_id = _parse_raw_id(raw_id)
                defn = get_def(tile_id)
                if defn is None:
                    continue
                if defn.get('layer') == 'bottom':
                    result.errors.append(
                        f'"{tile_id}" 屬於 bottom 層，不能放在 middle[{r}][{c}]'
                    )
                elif defn.get('layer') == 'upper':
                    result.errors.append(
                        f'"{tile_id}" 屬於 upper 層，不能放在 middle[{r}][{c}]'
                    )

    # bottom 層：只能有 Puddle（layer='bottom'）
    bottom_data = board.get('bottom', [])
    if isinstance(bottom_data, list):
        for r, row in enumerate(bottom_data):
            if not isinstance(row, list):
                continue
            for c, raw_id in enumerate(row):
                if raw_id is None or raw_id == 'void':
                    continue
                tile_id = _parse_raw_id(raw_id)
                defn = get_def(tile_id)
                if defn is None:
                    continue
                if defn.get('layer') != 'bottom':
                    result.errors.append(
                        f'"{tile_id}" 不屬於 bottom 層，不能放在 bottom[{r}][{c}]（底層只能放 Puddle）'
                    )

    # upper 層：只能有 Rope/Mud（layer='upper'）
    upper_data = board.get('upper', [])
    if isinstance(upper_data, list):
        for r, row in enumerate(upper_data):
            if not isinstance(row, list):
                continue
            for c, raw_id in enumerate(row):
                if raw_id is None or raw_id == 'void':
                    continue
                tile_id = _parse_raw_id(raw_id)
                defn = get_def(tile_id)
                if defn is None:
                    continue
                if defn.get('layer') != 'upper':
                    result.errors.append(
                        f'"{tile_id}" 不屬於 upper 層，不能放在 upper[{r}][{c}]（上層只能放 Rope/Mud）'
                    )


def _count_tiles_on_board(d: dict) -> dict:
    """統計盤面上每種 tile 的數量"""
    counts = {}
    board = d.get('board')
    if board is None:
        return counts

    def _scan(layer_data):
        if not isinstance(layer_data, list):
            return
        seen_instances = set()
        for row in layer_data:
            if not isinstance(row, list):
                continue
            for raw_id in row:
                if raw_id is None or raw_id == 'void':
                    continue
                tile_id = _parse_raw_id(raw_id)
                # 2x2 multi-cell instances 按物件數計（4 格只算 1）
                if '#' in raw_id:
                    if raw_id in seen_instances:
                        continue
                    seen_instances.add(raw_id)
                counts[tile_id] = counts.get(tile_id, 0) + 1

    if isinstance(board, list):
        _scan(board)
    elif isinstance(board, dict):
        for layer_data in board.values():
            _scan(layer_data)

    return counts


def _check_goal_consistency(d: dict, result: ValidationResult):
    """驗證每個 goal 目標數「可達成」(不可達成 → 報錯讓生成器重生):
    - 元素(Red/Grn…)         : 遊戲每回合動態無限補充 → 一定達得到
    - 有 spawner 持續生成該物件 : 引擎會生到滿足目標為止 → 一定達得到
    - 其餘障礙物             : 只能消除盤面上既有的 → 目標數必須 <= 盤面物件數(×每個HP)
                              (目標以「消除幾個物件」計，多格物件算 1 個)
    """
    goals = d.get('goals', {})
    if not goals:
        return

    # 按「家族」統計（容忍 goal 用家族名 Crt 或變體名 Crt1 都對得上）：
    #  - fam_count：物件數（判斷盤面上到底有沒有）
    #  - fam_cap  ：累計可消「點數」上限（目標以累計傷害/觸發計，多 HP 物件如冰箱要乘 HP）
    fam_count = {}
    fam_cap = {}
    for tid, n in _count_tiles_on_board(d).items():
        fam = _tile_family(tid)
        defn = get_def(tid) or {}
        hp = defn.get('health', 1)
        elim = defn.get('elimination_type', 'single')
        fam_count[fam] = fam_count.get(fam, 0) + n
        # 目標只在「物件被消滅」時 +1(match_engine);受擊降血不算、tile_id 不變。
        #   single(紙箱/水漥/木桶/三角錐…):打爆才算 1 → 上限 = 物件數(HP 不乘)
        #   multi (冰箱…):會逐階降階成別的 tile_id → 每階都算 → 上限 = HP 累計
        if hp >= 9999:  # Stamp/Postmark 觸發型 → 可重複觸發,不受盤面數量限制
            fam_cap[fam] = float('inf')
        else:
            contrib = hp if elim == 'multi' else 1
            fam_cap[fam] = fam_cap.get(fam, 0) + n * contrib

    # 有 spawner 持續生成的家族 → 視為可無限補充，目標一定達得到
    spawner_fams = set()
    for sp in (d.get('spawners') or []):
        if not isinstance(sp, dict):
            continue
        for e in sp.get('elements', []):
            if isinstance(e, dict):
                spawner_fams.add(_tile_family(e.get('tile_id', '')))

    for goal_tile, goal_count in goals.items():
        if not isinstance(goal_count, (int, float)) or goal_count <= 0:
            result.errors.append(f'goal "{goal_tile}" 的數量必須是正整數')
            continue
        if is_element(goal_tile):          # 元素：遊戲動態無限補充
            continue
        fam = _tile_family(goal_tile)
        if fam in spawner_fams:            # 有 spawner 補充 → 一定達得到
            continue

        if fam_count.get(fam, 0) == 0:
            result.errors.append(
                f'目標 "{goal_tile}"×{int(goal_count)} 無法達成：盤面上沒有任何 "{goal_tile}"，'
                f'也沒有 spawner 會生成它。請在盤面放足夠的 "{goal_tile}"，或加一個生成它的 spawner。'
            )
            continue
        cap = fam_cap.get(fam, 0)
        if goal_count > cap:
            result.errors.append(
                f'目標 "{goal_tile}"×{int(goal_count)} 無法達成：盤面最多只能消 {int(cap)} 點'
                f'（共 {fam_count[fam]} 個物件），且無 spawner 補充。'
                f'請把目標降到 {int(cap)} 以下，或在盤面增加數量／加一個生成它的 spawner。'
            )


def _check_warnings(d: dict, result: ValidationResult):
    """非阻斷性的設計建議檢查"""
    rows = d.get('rows', 10)
    cols = d.get('cols', 9)
    max_steps = d.get('max_steps', 30)
    goals = d.get('goals', {})

    # 步數過低警告
    if max_steps < 10:
        result.warnings.append(f'max_steps={max_steps} 非常低，關卡可能幾乎無法完成')

    # 步數過高警告
    if max_steps > 100:
        result.warnings.append(f'max_steps={max_steps} 非常高，關卡可能太簡單')

    # 盤面過小
    if rows * cols < 25:
        result.warnings.append(f'盤面 {rows}×{cols} 較小，可能導致洗牌頻繁')

    # 無目標（goals 空）
    if not goals:
        result.warnings.append('goals 為空，關卡永遠無法勝利')
