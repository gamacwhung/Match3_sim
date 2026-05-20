extends Node

signal fill_complete

var grid: Array = []
var width: int = 9
var height: int = 9
var cell_size: float = 70.0
var board_offset: Vector2 = Vector2.ZERO
var blocked_cells: Array[Vector2i] = []
var candy_scene: PackedScene
var candy_container: Node2D
var num_colors: int = 6

func setup(w: int, h: int, c_size: float, offset: Vector2, container: Node2D, scene: PackedScene, blocked: Array[Vector2i] = []) -> void:
	width = w
	height = h
	cell_size = c_size
	board_offset = offset
	candy_container = container
	candy_scene = scene
	blocked_cells = blocked
	grid.clear()
	for x in width:
		var col: Array = []
		col.resize(height)
		col.fill(null)
		grid.append(col)

func grid_to_world(grid_pos: Vector2i) -> Vector2:
	return board_offset + Vector2(grid_pos.x * cell_size + cell_size / 2.0, grid_pos.y * cell_size + cell_size / 2.0)

func fill_initial() -> void:
	var MatchFinder = preload("res://scripts/board/match_finder.gd")
	for y in height:
		for x in width:
			if Vector2i(x, y) in blocked_cells:
				continue
			var color = _pick_no_match_color(x, y)
			var candy = _create_candy(color, Vector2i(x, y))
			grid[x][y] = candy

func _pick_no_match_color(x: int, y: int) -> int:
	var attempts = 0
	while attempts < 100:
		var color = randi() % num_colors
		var h_match = false
		if x >= 2:
			if grid[x - 1][y] != null and grid[x - 2][y] != null:
				if grid[x - 1][y].candy_color == color and grid[x - 2][y].candy_color == color:
					h_match = true
		var v_match = false
		if y >= 2:
			if grid[x][y - 1] != null and grid[x][y - 2] != null:
				if grid[x][y - 1].candy_color == color and grid[x][y - 2].candy_color == color:
					v_match = true
		if not h_match and not v_match:
			return color
		attempts += 1
	return randi() % num_colors

func _create_candy(color: int, grid_pos: Vector2i, candy_type: int = 0) -> Node2D:
	var candy = candy_scene.instantiate()
	candy_container.add_child(candy)
	candy.init(color, grid_pos, candy_type)
	candy.cell_size = cell_size
	candy.position = grid_to_world(grid_pos)
	return candy

# 共用的掉落時長(秒/格)— gravity 跟 fill 用同一個公式,
# 才能在視覺上「連成一條下落的列車」,不會出現兩段斷層。
const _FALL_TIME_PER_CELL: float = 0.07
const _FALL_TIME_BASE: float = 0.08

static func _fall_duration(dist: int) -> float:
	return _FALL_TIME_PER_CELL * dist + _FALL_TIME_BASE


func apply_gravity() -> Array[Tween]:
	# 重力演算法 — 3-phase iterative,跟 Streamlit 端類似但多了一條關鍵限制:
	#
	#   Phase 1:每一欄都直落到底(repeated column drop)
	#   Phase 2:左斜落 — 「正下方被擋」+「左下空」+ **左下那格從頂部下不來** → 才落
	#   Phase 3:右斜落 — 同理
	#
	# 「左下/右下那格從頂部下不來」= 目標欄從 (x, 0) 到目標位置中間有 blocked 障礙物
	#   截斷 — 也就是 fill_empty_cells 不會從頂部補它的那種空格(被困在 cavity 裡)。
	#
	# 為什麼加這條?user 報的 bug:
	#   「在空位上明明有元素可以降落,卻是由隔壁col的元素降落在它上面」
	#   也就是:本來這格空格應該等同 col 上方的新糖從頂部補進來,
	#         結果隔壁 col 的糖搶先斜落進來,看起來很怪。
	# 修法:**只有目標那格從頂部進不來時(被障礙物截斷,卡在 cavity 裡)**
	#       才允許斜落。一般場合(目標欄頂部暢通)就讓 fill_empty_cells 補,
	#       不讓鄰邊的糖搶這位置。
	#
	# 對 lvl 26 之類 cavity 場景仍正確:cavity 因為上方有 Crt 擋住,fill 進不去,
	# 所以斜落是它能被補滿的**唯一**管道,仍然會啟動。
	var tweens: Array[Tween] = []

	var origin_pos: Dictionary = {}
	for x in width:
		for y in height:
			var c = grid[x][y]
			if c != null:
				origin_pos[c] = Vector2i(x, y)

	var overall_moved = true
	var safety = 0
	while overall_moved and safety < (width * height * 4):
		safety += 1
		overall_moved = false

		# Phase 1: 全欄直落到底
		for x in width:
			while _column_drop(x):
				overall_moved = true

		# Phase 2: 左斜落 — 反覆直到沒有任何左斜可動
		var left_moved = true
		while left_moved:
			left_moved = false
			for y in range(height - 2, -1, -1):
				for x in range(width):
					var c = grid[x][y]
					if c == null:
						continue
					# 正下方是 blocked / 被佔(意即不能直落)才嘗試斜落
					if _can_fall_to(x, y + 1):
						continue
					if x > 0 and _can_fall_to(x - 1, y + 1) and not _reachable_from_top(x - 1, y + 1):
						grid[x - 1][y + 1] = c
						grid[x][y] = null
						# 落到 x-1 後立刻一路直落
						while _column_drop(x - 1):
							pass
						left_moved = true
						overall_moved = true

		# Phase 3: 右斜落 — 反覆直到沒有任何右斜可動
		var right_moved = true
		while right_moved:
			right_moved = false
			for y in range(height - 2, -1, -1):
				for x in range(width):
					var c = grid[x][y]
					if c == null:
						continue
					if _can_fall_to(x, y + 1):
						continue
					if x < width - 1 and _can_fall_to(x + 1, y + 1) and not _reachable_from_top(x + 1, y + 1):
						grid[x + 1][y + 1] = c
						grid[x][y] = null
						while _column_drop(x + 1):
							pass
						right_moved = true
						overall_moved = true

	# 為移動過的糖建立 tween:從 origin 一直線飛到最終位置
	for x in width:
		for y in height:
			var c = grid[x][y]
			if c == null:
				continue
			if not origin_pos.has(c):
				continue
			var orig: Vector2i = origin_pos[c]
			if orig != Vector2i(x, y):
				c.grid_pos = Vector2i(x, y)
				var dist = max(absi(x - orig.x), absi(y - orig.y))
				var target = grid_to_world(Vector2i(x, y))
				var tween = c.animate_fall(target, _fall_duration(dist))
				tweens.append(tween)
	return tweens


# 把第 x 欄的糖往下推一格 — 回傳是否有動。
# 由下往上掃:每顆糖看正下方是不是空(且不是 blocked),空就放下去。
# 同一輪內每顆糖最多動一格,呼叫端 while 迴圈會反覆呼叫直到無法再動。
func _column_drop(x: int) -> bool:
	var moved = false
	for y in range(height - 2, -1, -1):
		var c = grid[x][y]
		if c == null:
			continue
		if not _can_fall_to(x, y + 1):
			continue
		grid[x][y + 1] = c
		grid[x][y] = null
		moved = true
	return moved


# 可否把糖放到 (x, y):在範圍內、不是 blocked、且目前空著
func _can_fall_to(x: int, y: int) -> bool:
	if x < 0 or x >= width or y < 0 or y >= height:
		return false
	if Vector2i(x, y) in blocked_cells:
		return false
	return grid[x][y] == null


# 從 (x, 0) 到 (x, y) 之間有沒有 blocked 障礙物截斷 — 若有則目標 (x, y) 在 cavity 裡,
# 普通 fill_empty_cells 無法從頂部補它,要靠斜落補。
# 若回傳 true 表示「頂部下得來」,斜落應該避讓(讓新糖從頂部補)。
func _reachable_from_top(x: int, y: int) -> bool:
	for ty in range(y):
		if Vector2i(x, ty) in blocked_cells:
			return false
	return true


func fill_empty_cells() -> Array[Tween]:
	# 物理上:從天上掉下來,**第一顆會穿過空格落到最底**,然後第二顆停在它上面...
	# 視覺上要呈現「一列連續往下掉的隊列」:
	#   - 排在最上方(start_y=-1)的 candy 落到最深的空格(y 最大)
	#   - 排在 start_y=-2 的 candy 落到次深空格
	#   - 每顆 dist 相同 → 等速一起到位,看起來像「整條糖果列車滑下來」
	#
	# 多了 blocking 障礙之後:
	#   - 只 fill「從盤面上方有暢通路徑」可達的空格
	#     → 中間有 blocked 截斷的空格本回合就先空著,
	#       等下一次 cascade 從鄰欄斜向補位過來(避免糖視覺上穿過 crate)
	var tweens: Array[Tween] = []
	for x in width:
		# 從上往下掃,只收「上方沒有 blocked 截斷」的空格
		var reachable_empty_ys: Array[int] = []
		var path_clear = true
		for y in height:
			if Vector2i(x, y) in blocked_cells:
				path_clear = false
				continue
			if grid[x][y] == null and path_clear:
				reachable_empty_ys.append(y)
		# 反向 fill:第 i 顆 spawn(start_y=-i-1)落到第 i 個最底的可達空格
		for i in reachable_empty_ys.size():
			var target_y = reachable_empty_ys[reachable_empty_ys.size() - 1 - i]
			var start_y = -(i + 1)
			var color = randi() % num_colors
			var candy = _create_candy(color, Vector2i(x, target_y))
			candy.position = grid_to_world(Vector2i(x, start_y))
			grid[x][target_y] = candy
			var target = grid_to_world(Vector2i(x, target_y))
			var dist = abs(target_y - start_y)
			var tween = candy.animate_fall(target, _fall_duration(dist))
			tweens.append(tween)
	return tweens

func remove_candy_at(pos: Vector2i) -> Node2D:
	if pos.x < 0 or pos.x >= width or pos.y < 0 or pos.y >= height:
		return null
	var candy = grid[pos.x][pos.y]
	grid[pos.x][pos.y] = null
	return candy

func set_candy_at(pos: Vector2i, candy: Node2D) -> void:
	grid[pos.x][pos.y] = candy
	if candy != null:
		candy.grid_pos = pos

func get_candy_at(pos: Vector2i) -> Node2D:
	if pos.x < 0 or pos.x >= width or pos.y < 0 or pos.y >= height:
		return null
	return grid[pos.x][pos.y]

func create_special_candy(color: int, grid_pos: Vector2i, candy_type: int) -> Node2D:
	var candy = _create_candy(color, grid_pos, candy_type)
	grid[grid_pos.x][grid_pos.y] = candy
	candy.animate_spawn()
	return candy
