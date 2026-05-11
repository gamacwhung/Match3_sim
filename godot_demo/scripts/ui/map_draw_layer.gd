extends Node2D

var map_parent: Control
# 字型用 nullable load — 缺檔不阻塞 godot 啟動,改用預設字型
var custom_font: Font = null
const _FONT_PATH = "res://resources/fonts/NotoSans-Regular.ttf"

func _ready() -> void:
	map_parent = get_parent() as Control
	if ResourceLoader.exists(_FONT_PATH):
		custom_font = load(_FONT_PATH)
	else:
		# fallback 用 ThemeDB 的預設字型
		custom_font = ThemeDB.fallback_font

func _draw() -> void:
	if map_parent == null or map_parent.level_positions.size() == 0:
		return

	for i in range(map_parent.level_positions.size() - 1):
		var from_pos = map_parent.level_positions[i]
		var to_pos = map_parent.level_positions[i + 1]
		var unlocked = SaveManager.is_level_unlocked(i + 1)
		var color = Color(0.5, 0.4, 0.7) if unlocked else Color(0.25, 0.2, 0.35)
		draw_line(from_pos, to_pos, color, map_parent.PATH_WIDTH)

	for i in map_parent.level_positions.size():
		var pos = map_parent.level_positions[i]
		var level_id = i + 1
		var unlocked = SaveManager.is_level_unlocked(level_id)
		var stars = SaveManager.get_level_stars(level_id)

		if unlocked:
			draw_circle(pos, map_parent.NODE_RADIUS + 3, Color(0.9, 0.75, 0.3, 0.5))
			var hue = fmod(float(i) * 0.1, 1.0)
			draw_circle(pos, map_parent.NODE_RADIUS, Color.from_hsv(hue, 0.6, 0.9))
		else:
			draw_circle(pos, map_parent.NODE_RADIUS, Color(0.3, 0.25, 0.4))

		var font = custom_font
		var font_size = 20
		var num_text = str(level_id)
		var text_size = font.get_string_size(num_text, HORIZONTAL_ALIGNMENT_CENTER, -1, font_size)
		var font_color = Color.WHITE if unlocked else Color(0.5, 0.5, 0.5)
		draw_string(font, pos - Vector2(text_size.x / 2.0, -font_size / 3.0), num_text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, font_color)

		if stars > 0:
			var star_y = pos.y + map_parent.NODE_RADIUS + 14
			var star_spacing = 14.0
			var total_width = (3 - 1) * star_spacing
			var star_start_x = pos.x - total_width / 2.0
			for s in 3:
				var star_center = Vector2(star_start_x + s * star_spacing, star_y)
				if s < stars:
					var pts = _star_points(star_center, 6.0, 2.7, 5)
					draw_colored_polygon(pts, Color.GOLD)
				else:
					var pts = _star_points(star_center, 6.0, 2.7, 5)
					draw_colored_polygon(pts, Color(0.5, 0.4, 0.2))

static func _star_points(center: Vector2, outer_r: float, inner_r: float, points: int) -> PackedVector2Array:
	var result = PackedVector2Array()
	for i in points * 2:
		var angle = TAU * i / (points * 2) - PI / 2
		var r = outer_r if i % 2 == 0 else inner_r
		result.append(center + Vector2(cos(angle), sin(angle)) * r)
	return result
