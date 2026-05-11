shader_type canvas_item;

uniform float glow_intensity : hint_range(0.0, 2.0) = 0.0;
uniform vec4 glow_color : source_color = vec4(1.0, 1.0, 1.0, 0.5);
uniform float pulse_speed : hint_range(0.0, 10.0) = 3.0;

void fragment() {
	vec4 tex_color = texture(TEXTURE, UV);
	float pulse = (sin(TIME * pulse_speed) + 1.0) * 0.5;
	float edge = smoothstep(0.3, 0.5, length(UV - vec2(0.5)));
	float glow = edge * glow_intensity * (0.5 + pulse * 0.5);
	vec4 glow_add = glow_color * glow;
	COLOR = tex_color + glow_add;
	COLOR.a = tex_color.a;
}
