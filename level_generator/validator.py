"""
關卡 JSON 驗證器

驗證生成的關卡是否符合格式規範並可被遊戲引擎載入。
"""

import sys
import os
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
                if raw_id is None:
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
                if raw_id is None:
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
                if raw_id is None:
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
                if raw_id is None:
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
        for row in layer_data:
            if not isinstance(row, list):
                continue
            for raw_id in row:
                if raw_id is None:
                    continue
                tile_id = _parse_raw_id(raw_id)
                counts[tile_id] = counts.get(tile_id, 0) + 1

    if isinstance(board, list):
        _scan(board)
    elif isinstance(board, dict):
        for layer_data in board.values():
            _scan(layer_data)

    return counts


def _check_goal_consistency(d: dict, result: ValidationResult):
    """驗證每個 goal tile 在盤面上存在"""
    goals = d.get('goals', {})
    if not goals:
        return

    tile_counts = _count_tiles_on_board(d)
    element_ids = {'Red', 'Grn', 'Blu', 'Yel', 'Pur', 'Brn'}

    for goal_tile, goal_count in goals.items():
        if not isinstance(goal_count, (int, float)) or goal_count <= 0:
            result.errors.append(f'goal "{goal_tile}" 的數量必須是正整數')
            continue

        # 元素顏色可以作為目標（由遊戲動態生成）
        if goal_tile in element_ids:
            continue

        # 非元素目標：盤面上必須存在對應 tile
        if goal_tile not in tile_counts:
            result.warnings.append(
                f'goal "{goal_tile}" 在盤面上找不到對應物件（若盤面為隨機生成則忽略此警告）'
            )
        else:
            defn = get_def(goal_tile)
            health = defn.get('health', 1) if defn else 1
            # Stamp 特殊：health=9999，目標是觸發次數
            if health >= 9999:
                continue
            max_achievable = tile_counts[goal_tile] * health
            if goal_count > max_achievable * 1.2:  # 允許 20% 誤差
                result.warnings.append(
                    f'goal "{goal_tile}" 目標 {goal_count} 可能過高'
                    f'（盤面最多 {max_achievable} 點）'
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
