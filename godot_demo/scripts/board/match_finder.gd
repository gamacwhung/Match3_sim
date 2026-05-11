extends Node
##
## MatchFinder
##
## 重寫版 — 對齊 Python match_engine.py 的設計:
##   1. 找所有水平 3+ 連 / 垂直 3+ 連 / 2x2 同色方塊(raw lines + raw blocks)
##   2. 同色 + overlap 的 raw 用 Union-Find 合併成 group
##   3. 對每個 group 依優先級判定 shape:
##        FIVE_PLUS > L_T > FOUR > BLOCK_2x2 > THREE
##      (對應 Python 的 LtBl > TNT > Soda > TrPr > 三消)
##
## match dict 結構:
##   {
##     "cells": Array[Vector2i],   # 全部 group 內的 cell
##     "shape": String,            # "five" / "special" / "four" / "block_2x2" / "line"
##     "direction": String,        # 對 "four" 才有意義:"horizontal" / "vertical"
##     "special_pos": Vector2i,    # 合成 special 的座標(L_T pivot / FOUR 中段 / 2x2 角)
##     "color": int,
##     "directions": Array[String],# 舊欄位,給仍用它的程式碼相容
##   }
##

const CandyScene = preload("res://scripts/candy/candy.gd")


static func find_all_matches(grid: Array, width: int, height: int, blocked: Array[Vector2i] = []) -> Array[Dictionary]:
	# 對齊 Python match_engine.find_matches:只有 NORMAL 元素(有 color)才參與 match 配對,
	# 道具(STRIPED/WRAPPED/SPIRAL/COLOR_BOMB)在 match line 中當成 break point,不會被吃進來。
	# Python 端 powerup tile.color == None,find_matches 開頭就 skip 掉。
	
	# ------- 1. raw 水平連線 -------
	var raw_lines: Array = []  # 每筆 {color, positions: Array[Vector2i], kind: "h"/"v"/"block"}
	for y in height:
		var x = 0
		while x < width:
			var p0 = Vector2i(x, y)
			if p0 in blocked or grid[x][y] == null:
				x += 1
				continue
			var candy0 = grid[x][y] as CandyScene
			if candy0 == null or candy0.candy_type != CandyScene.CandyType.NORMAL:
				x += 1
				continue
			var color = candy0.candy_color
			var run: Array = [p0]
			var xx = x + 1
			while xx < width:
				if Vector2i(xx, y) in blocked or grid[xx][y] == null:
					break
				var c2 = grid[xx][y] as CandyScene
				if c2 == null or c2.candy_color != color or c2.candy_type != CandyScene.CandyType.NORMAL:
					break
				run.append(Vector2i(xx, y))
				xx += 1
			if run.size() >= 3:
				raw_lines.append({"color": color, "positions": run, "kind": "h"})
			x = xx if xx > x else x + 1
	
	# ------- 2. raw 垂直連線 -------
	for x in width:
		var y = 0
		while y < height:
			var p0 = Vector2i(x, y)
			if p0 in blocked or grid[x][y] == null:
				y += 1
				continue
			var candy0 = grid[x][y] as CandyScene
			if candy0 == null or candy0.candy_type != CandyScene.CandyType.NORMAL:
				y += 1
				continue
			var color = candy0.candy_color
			var run: Array = [p0]
			var yy = y + 1
			while yy < height:
				if Vector2i(x, yy) in blocked or grid[x][yy] == null:
					break
				var c2 = grid[x][yy] as CandyScene
				if c2 == null or c2.candy_color != color or c2.candy_type != CandyScene.CandyType.NORMAL:
					break
				run.append(Vector2i(x, yy))
				yy += 1
			if run.size() >= 3:
				raw_lines.append({"color": color, "positions": run, "kind": "v"})
			y = yy if yy > y else y + 1
	
	# ------- 3. raw 2x2 方塊(同色 4 格)-------
	for x in range(width - 1):
		for y in range(height - 1):
			var positions := _check_2x2_at(grid, x, y, width, height, blocked)
			if positions.size() == 4:
				var c00 = grid[x][y] as CandyScene
				raw_lines.append({"color": c00.candy_color, "positions": positions, "kind": "block"})
	
	if raw_lines.size() == 0:
		return [] as Array[Dictionary]
	
	# ------- 4. Union-Find 合併同色 + overlap -------
	var n = raw_lines.size()
	var parent: Array[int] = []
	for i in n:
		parent.append(i)
	# 直接 inline find/union(GDScript Lambdas 對 parent 的 mutation 不太穩)
	# 找 raw_lines 中互相 overlap 的 same-color pair,合併它們
	for i in range(n):
		for j in range(i + 1, n):
			if raw_lines[i]["color"] != raw_lines[j]["color"]:
				continue
			var overlap := false
			for p in raw_lines[i]["positions"]:
				if p in raw_lines[j]["positions"]:
					overlap = true
					break
			if overlap:
				var ri := _find_root(parent, i)
				var rj := _find_root(parent, j)
				if ri != rj:
					parent[ri] = rj
	
	# ------- 5. 收集 group -------
	# groups[root] = {color, positions, has_block}
	var groups: Dictionary = {}
	for i in n:
		var root := _find_root(parent, i)
		if not groups.has(root):
			groups[root] = {
				"color": raw_lines[i]["color"],
				"positions": [] as Array[Vector2i],
				"has_block": false,
			}
		var arr: Array = groups[root]["positions"]
		for p in raw_lines[i]["positions"]:
			if not (p in arr):
				arr.append(p)
		if raw_lines[i]["kind"] == "block":
			groups[root]["has_block"] = true
	
	# ------- 6. classify shape per group -------
	var matches: Array[Dictionary] = []
	for g in groups.values():
		var positions: Array[Vector2i] = g["positions"]
		if positions.size() < 3:
			continue
		var has_block: bool = g["has_block"]
		
		# 對每個 cell 算 h_run / v_run(within group)
		var pset: Dictionary = {}
		for p in positions:
			pset[p] = true
		var max_h := 0
		var max_v := 0
		var max_h_run_positions: Array[Vector2i] = []
		var max_v_run_positions: Array[Vector2i] = []
		var l_t_pivot: Vector2i = positions[0]
		var has_cross := false
		for p in positions:
			var h_run := 1
			var hp_start: int = p.x
			var hp_end: int = p.x
			var px := p.x + 1
			while pset.has(Vector2i(px, p.y)):
				h_run += 1
				hp_end = px
				px += 1
			px = p.x - 1
			while pset.has(Vector2i(px, p.y)):
				h_run += 1
				hp_start = px
				px -= 1
			var v_run := 1
			var vp_start: int = p.y
			var vp_end: int = p.y
			var py := p.y + 1
			while pset.has(Vector2i(p.x, py)):
				v_run += 1
				vp_end = py
				py += 1
			py = p.y - 1
			while pset.has(Vector2i(p.x, py)):
				v_run += 1
				vp_start = py
				py -= 1
			if h_run > max_h:
				max_h = h_run
				max_h_run_positions.clear()
				for cx in range(hp_start, hp_end + 1):
					max_h_run_positions.append(Vector2i(cx, p.y))
			if v_run > max_v:
				max_v = v_run
				max_v_run_positions.clear()
				for cy in range(vp_start, vp_end + 1):
					max_v_run_positions.append(Vector2i(p.x, cy))
			if h_run >= 3 and v_run >= 3 and not has_cross:
				has_cross = true
				l_t_pivot = p
		
		var shape := "line"
		var direction := "horizontal"
		var special_pos: Vector2i = positions[0]
		
		# 優先級對齊 Python:FIVE_PLUS > L_T > FOUR > 2x2 > THREE
		if max(max_h, max_v) >= 5:
			shape = "five"
			# 取最長線的中段為合成位置(整數除法 OK,5/2=2 第 3 個是中段)
			if max_h >= max_v:
				special_pos = max_h_run_positions[int(max_h_run_positions.size() / 2)]
			else:
				special_pos = max_v_run_positions[int(max_v_run_positions.size() / 2)]
		elif has_cross:
			shape = "special"  # L_T
			special_pos = l_t_pivot
		elif max(max_h, max_v) == 4:
			shape = "four"
			if max_h >= max_v:
				direction = "horizontal"
				special_pos = max_h_run_positions[1]  # 4 連的第 2 個
			else:
				direction = "vertical"
				special_pos = max_v_run_positions[1]
		elif has_block:
			shape = "block_2x2"
			# 找其中一個 2x2 角(取最左上)
			special_pos = positions[0]
			for p in positions:
				if p.x <= special_pos.x and p.y <= special_pos.y:
					special_pos = p
		else:
			shape = "line"
			if max_h >= max_v:
				special_pos = max_h_run_positions[int(max_h_run_positions.size() / 2)]
			else:
				special_pos = max_v_run_positions[int(max_v_run_positions.size() / 2)]
		
		matches.append({
			"cells": positions,
			"shape": shape,
			"direction": direction,
			"special_pos": special_pos,
			"color": g["color"],
			"directions": [direction],  # 相容舊欄位
		})
	
	return matches


static func _check_2x2_at(grid: Array, x: int, y: int, width: int, height: int, blocked: Array[Vector2i]) -> Array[Vector2i]:
	var positions: Array[Vector2i] = []
	if x + 1 >= width or y + 1 >= height:
		return positions
	var c00 = grid[x][y]
	if c00 == null or Vector2i(x, y) in blocked:
		return positions
	# 2x2 也只認 NORMAL,跟橫/縱連線同規則:special candy 不參與 match
	if c00.candy_type != CandyScene.CandyType.NORMAL:
		return positions
	var color = c00.candy_color
	for dx in range(2):
		for dy in range(2):
			var px: int = x + dx
			var py: int = y + dy
			if Vector2i(px, py) in blocked or grid[px][py] == null:
				return [] as Array[Vector2i]
			var cc = grid[px][py]
			if cc.candy_color != color or cc.candy_type != CandyScene.CandyType.NORMAL:
				return [] as Array[Vector2i]
			positions.append(Vector2i(px, py))
	return positions


static func _find_root(parent: Array, i: int) -> int:
	while parent[i] != i:
		parent[i] = parent[parent[i]]
		i = parent[i]
	return i


# ===========================================================================
# 相容介面 — game_board.gd 還在用的
# ===========================================================================

static func has_possible_moves(grid: Array, width: int, height: int, blocked: Array[Vector2i] = []) -> bool:
	return find_hint_move(grid, width, height, blocked).size() > 0


static func find_hint_move(grid: Array, width: int, height: int, blocked: Array[Vector2i] = []) -> Array[Vector2i]:
	for y in height:
		for x in width:
			if Vector2i(x, y) in blocked or grid[x][y] == null:
				continue
			for dir in [Vector2i(1, 0), Vector2i(0, 1)]:
				var nx = x + dir.x
				var ny = y + dir.y
				if nx >= width or ny >= height:
					continue
				if Vector2i(nx, ny) in blocked or grid[nx][ny] == null:
					continue
				_swap_in_grid(grid, x, y, nx, ny)
				var found = find_all_matches(grid, width, height, blocked).size() > 0
				_swap_in_grid(grid, x, y, nx, ny)
				if found:
					return [Vector2i(x, y), Vector2i(nx, ny)]
	return []


static func _swap_in_grid(grid: Array, x1: int, y1: int, x2: int, y2: int) -> void:
	var temp = grid[x1][y1]
	grid[x1][y1] = grid[x2][y2]
	grid[x2][y2] = temp
