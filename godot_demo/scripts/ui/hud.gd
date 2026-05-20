extends CanvasLayer

@onready var score_label: Label = $TopBar/ScoreLabel
@onready var level_label: Label = $TopBar/LevelLabel
@onready var moves_label: Label = $TopBar/MovesLabel
@onready var objective_label: Label = $TopBar/ObjectiveLabel
@onready var score_bar: ProgressBar = $TopBar/ScoreBar
@onready var star1: Node2D = $TopBar/ScoreBar/Star1
@onready var star2: Node2D = $TopBar/ScoreBar/Star2
@onready var star3: Node2D = $TopBar/ScoreBar/Star3

# Web export 有時不認 project.godot 的 default_font(尤其是 web build cache 過的版本),
# 跟 level_select.gd 用一樣方式:手動 load CJK 字型並 per-label override,確保中文不會顯示成方塊。
const FONT_PATH: String = "res://resources/fonts/NotoSansTC-Regular.otf"
var _font: FontFile = null

var star_thresholds: Array[int] = []
var _score_objective_target: int = 0
var _star_colors: Array[Color] = [Color(0.4, 0.4, 0.4), Color(0.4, 0.4, 0.4), Color(0.4, 0.4, 0.4)]

func _ready() -> void:
	_font = load(FONT_PATH) as FontFile
	_apply_font_overrides()
	GameManager.score_changed.connect(_on_score_changed)
	GameManager.moves_changed.connect(_on_moves_changed)
	GameManager.objective_updated.connect(_on_objective_updated)
	star1.draw.connect(func(): _draw_star(star1, 0))
	star2.draw.connect(func(): _draw_star(star2, 1))
	star3.draw.connect(func(): _draw_star(star3, 2))

func _apply_font_overrides() -> void:
	# 字型沒載成功也不要 crash;繼續用全域 fallback
	if _font == null:
		return
	for lb in [score_label, level_label, moves_label, objective_label]:
		if lb:
			lb.add_theme_font_override("font", _font)

func setup(level_data: Resource) -> void:
	# 方案 A:不顯示分數,只顯示「關卡編號 + 剩餘步數 + 障礙物進度」
	score_label.visible = false
	score_bar.visible = false
	star1.visible = false
	star2.visible = false
	star3.visible = false
	star_thresholds = level_data.star_thresholds.duplicate()
	_score_objective_target = 0
	_apply_font_overrides()
	# 顯示關卡編號(loader 從 JSON name 解析)— 強調醒目讓玩家一眼看到在玩哪關
	var lid = int(level_data.level_id) if level_data and "level_id" in level_data else 0
	level_label.text = "第 %d 關" % lid if lid > 0 else "Demo 關卡"
	level_label.add_theme_color_override("font_color", Color(1, 0.95, 0.55))
	_on_moves_changed(level_data.max_moves)
	_update_objective_display(level_data.objectives)

const TILE_LABELS: Dictionary = {
	"Crt": "紙箱",
	"Barrel": "木桶",
	"TrafficCone": "交通錐",
	"SalmonCan": "鮭魚罐",
	"Stamp": "郵戳",
	"WaterChiller": "礦泉水櫃",
	"BeverageChiller": "飲料櫃",
	"Pool": "充氣泳池",
	"Roadblock": "路障",
	"Puddle": "水漥",
	"Rope": "繩索",
	"Mud": "泥巴",
}


func _on_score_changed(_new_score: int) -> void:
	pass


func _on_moves_changed(remaining: int) -> void:
	moves_label.text = "剩餘步數: %d" % remaining
	if remaining <= 5:
		moves_label.add_theme_color_override("font_color", Color(1.0, 0.3, 0.3))
	else:
		moves_label.add_theme_color_override("font_color", Color.WHITE)


func _on_objective_updated(_obj: Dictionary) -> void:
	# 任一 objective 更新 → 整片重畫
	_update_objective_display(GameManager.level_objectives)


func _update_objective_display(objectives: Array) -> void:
	if objectives.size() == 0:
		objective_label.text = ""
		return
	var parts: Array[String] = []
	for obj in objectives:
		var target = obj.get("target", 0)
		var current = obj.get("current", 0)
		var tile_id = obj.get("tile_id", "")
		var label = _tile_id_to_label(tile_id) if tile_id != "" else _type_to_label(obj.get("type", ""))
		parts.append("%s %d / %d" % [label, current, target])
	objective_label.text = "  ·  ".join(parts)


func _tile_id_to_label(tile_id: String) -> String:
	for prefix in TILE_LABELS.keys():
		if tile_id.begins_with(prefix):
			return TILE_LABELS[prefix]
	return tile_id


func _type_to_label(t: String) -> String:
	match t:
		"collect": return "收集"
		"clear_jelly": return "障礙物"
		"clear_ice": return "冰塊"
		"clear_wire": return "繩索"
		"clear_manufacturer": return "明信片"
		"score": return "分數"
	return "目標"

func _update_stars(score: int) -> void:
	if star_thresholds.size() < 3:
		return
	_star_colors[0] = Color.GOLD if score >= star_thresholds[0] else Color(0.4, 0.4, 0.4)
	_star_colors[1] = Color.GOLD if score >= star_thresholds[1] else Color(0.4, 0.4, 0.4)
	_star_colors[2] = Color.GOLD if score >= star_thresholds[2] else Color(0.4, 0.4, 0.4)
	star1.queue_redraw()
	star2.queue_redraw()
	star3.queue_redraw()

func _draw_star(node: Node2D, idx: int) -> void:
	var color = _star_colors[idx]
	var pts = _star_points(Vector2.ZERO, 10.0, 4.5, 5)
	node.draw_colored_polygon(pts, color)
	var pts_inner = _star_points(Vector2.ZERO, 7.0, 3.5, 5)
	var highlight = lerp(color, Color.WHITE, 0.3)
	node.draw_colored_polygon(pts_inner, highlight)

static func _star_points(center: Vector2, outer_r: float, inner_r: float, points: int) -> PackedVector2Array:
	var result = PackedVector2Array()
	for i in points * 2:
		var angle = TAU * i / (points * 2) - PI / 2
		var r = outer_r if i % 2 == 0 else inner_r
		result.append(center + Vector2(cos(angle), sin(angle)) * r)
	return result

func _animate_score_pop() -> void:
	var tween = create_tween()
	tween.tween_property(score_label, "scale", Vector2(1.1, 1.1), 0.08)
	tween.tween_property(score_label, "scale", Vector2.ONE, 0.08)
