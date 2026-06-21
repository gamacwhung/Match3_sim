extends Node
##
## ArtTheme — runtime sprite overrides for AI-generated art.
##
## Web: loads godot_demo/web/live_sprites/*.png over packed defaults.
## Editor / desktop: uses res://resources/sprites/ (live folder ignored).
##

signal theme_ready

const ELEMENT_NAMES: Dictionary = {
	0: "Red",
	1: "Grn",
	2: "Blu",
	3: "Yel",
	4: "Pur",
}

# 非元素的具名美術(用 sprite 檔名),一樣支援 live_sprites 即時替換。
const NAMED_TEXTURES: Array[String] = ["board_bg"]

var theme_revision: int = 0
var _textures: Dictionary = {}
var _named: Dictionary = {}


func _ready() -> void:
	await reload()


func reload() -> void:
	theme_revision = int(Time.get_unix_time_from_system())
	_textures.clear()
	_named.clear()
	_load_packed_defaults()
	if OS.has_feature("web"):
		await _apply_live_overrides()
	theme_ready.emit()


func get_element_texture(color_index: int) -> Texture2D:
	return _textures.get(color_index)


func has_element_texture(color_index: int) -> bool:
	return _textures.has(color_index)


func get_named_texture(name: String) -> Texture2D:
	return _named.get(name)


func has_named_texture(name: String) -> bool:
	return _named.has(name)


func _load_packed_defaults() -> void:
	for color_index in ELEMENT_NAMES:
		var name: String = ELEMENT_NAMES[color_index]
		var path := "res://resources/sprites/%s.png" % name
		if ResourceLoader.exists(path):
			_textures[color_index] = load(path)
	for tex_name in NAMED_TEXTURES:
		var named_path := "res://resources/sprites/%s.png" % tex_name
		if ResourceLoader.exists(named_path):
			_named[tex_name] = load(named_path)


func _apply_live_overrides() -> void:
	var base_url := _live_base_url()
	if base_url.is_empty():
		return
	for color_index in ELEMENT_NAMES:
		var name: String = ELEMENT_NAMES[color_index]
		var url := "%s%s.png?v=%d" % [base_url, name, theme_revision]
		var tex := await _fetch_texture(url)
		if tex:
			_textures[color_index] = tex
	for tex_name in NAMED_TEXTURES:
		var named_url := "%s%s.png?v=%d" % [base_url, tex_name, theme_revision]
		var named_tex := await _fetch_texture(named_url)
		if named_tex:
			_named[tex_name] = named_tex


func _live_base_url() -> String:
	if not OS.has_feature("web"):
		return ""
	var js := """
	(function() {
	  var p = window.location.pathname;
	  var i = p.lastIndexOf('/');
	  var base = window.location.origin + (i >= 0 ? p.substring(0, i + 1) : '/');
	  return base + 'live_sprites/';
	})()
	"""
	var result = JavaScriptBridge.eval(js, true)
	return str(result) if result != null else ""


func _fetch_texture(url: String) -> Texture2D:
	var http := HTTPRequest.new()
	add_child(http)
	var err := http.request(url)
	if err != OK:
		http.queue_free()
		return null

	var args = await http.request_completed
	http.queue_free()

	var result: int = args[0]
	var response_code: int = args[1]
	var body: PackedByteArray = args[3]
	if result != HTTPRequest.RESULT_SUCCESS or response_code != 200 or body.is_empty():
		return null

	var image := Image.new()
	if image.load_png_from_buffer(body) != OK:
		return null
	return ImageTexture.create_from_image(image)
