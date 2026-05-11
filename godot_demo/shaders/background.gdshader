shader_type canvas_item;

uniform vec4 color_top : source_color = vec4(0.15, 0.08, 0.3, 1.0);
uniform vec4 color_bottom : source_color = vec4(0.05, 0.02, 0.12, 1.0);
uniform float wave_speed : hint_range(0.0, 2.0) = 0.3;
uniform float wave_amplitude : hint_range(0.0, 0.1) = 0.02;

void fragment() {
	vec2 uv = UV;
	uv.y += sin(uv.x * 6.0 + TIME * wave_speed) * wave_amplitude;
	uv.y += cos(uv.x * 4.0 - TIME * wave_speed * 0.7) * wave_amplitude * 0.5;
	float t = clamp(uv.y, 0.0, 1.0);
	COLOR = mix(color_top, color_bottom, t);
	float sparkle = sin(uv.x * 50.0 + TIME * 2.0) * sin(uv.y * 50.0 - TIME * 1.5);
	sparkle = max(sparkle - 0.97, 0.0) * 30.0;
	COLOR.rgb += vec3(sparkle) * 0.3;
}
