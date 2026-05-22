extends Resource
class_name LevelData

@export var level_id: int = 1
@export var grid_width: int = 9
@export var grid_height: int = 9
@export var max_moves: int = 30
@export var num_colors: int = 6
@export var star_thresholds: Array[int] = [1000, 3000, 5000]
@export var objectives: Array[Dictionary] = []
@export var obstacle_data: Array[Dictionary] = []
@export var bottom_obstacle_data: Array[Dictionary] = []
@export var blocked_cells: Array[Vector2i] = []
@export var void_cells: Array[Vector2i] = []  # 不存在的格子，糖可穿過掉落

# 下層 Puddle 等「不 blocking 但開局不放糖」的格 — fill_initial 要當作 blocked,
# 但實際遊戲中允許糖從上方掉落經過/停靠在這些格上。
@export var puddle_only_cells: Array[Vector2i] = []

# 開局就放在盤面上的特殊糖(官方關卡內建道具,如 Soda0d、TNT、TrPr、LtBl)。
# 每個 entry: {"pos": Vector2i, "type_name": String}
#   type_name: "striped_h" / "striped_v" / "wrapped" / "spiral" / "color_bomb"
@export var pre_placed_specials: Array[Dictionary] = []

# 頂部生成器 — 某些 column 會以一定比例生成障礙物而非普通糖
# 每個 entry: {"spawn_cols": Array[int], "elements": Array[Dictionary], "set_ratio": int}
#   elements: [{"tile_id": "Barrel", "ratio": 1}, ...]
#   set_ratio: 每 N 次 fill 有一次出障礙
@export var spawner_data: Array[Dictionary] = []
