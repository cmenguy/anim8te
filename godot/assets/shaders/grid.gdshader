// Metric ground grid in world space: 1 m major lines, 10 cm minor lines,
// red X axis and blue Z axis through the origin. Minor lines fade out where
// they would alias (cells smaller than a few pixels).
shader_type spatial;

uniform vec3 base_color : source_color = vec3(0.56, 0.56, 0.56);
uniform vec3 minor_color : source_color = vec3(0.47, 0.47, 0.47);
uniform vec3 major_color : source_color = vec3(0.30, 0.30, 0.30);
uniform vec3 x_axis_color : source_color = vec3(0.75, 0.22, 0.22);
uniform vec3 z_axis_color : source_color = vec3(0.22, 0.38, 0.75);
uniform float minor_width = 0.006;  // metres
uniform float major_width = 0.025;  // metres
uniform float axis_width = 0.05;    // metres

varying vec3 world_pos;

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

// Coverage of grid lines `spacing` apart and `width` wide, antialiased per axis.
vec2 lines(vec2 p, float spacing, float width) {
	vec2 d = abs(fract(p / spacing - 0.5) - 0.5) * spacing;
	vec2 aa = max(fwidth(p), vec2(1e-5));
	return 1.0 - smoothstep(vec2(width * 0.5) - aa, vec2(width * 0.5) + aa, d);
}

void fragment() {
	vec2 p = world_pos.xz;
	vec2 aa = max(fwidth(p), vec2(1e-5));

	vec2 minor = lines(p, 0.1, minor_width);
	float minor_fade = 1.0 - smoothstep(0.015, 0.035, max(aa.x, aa.y));
	vec2 major = lines(p, 1.0, major_width);
	vec2 axis = 1.0 - smoothstep(vec2(axis_width * 0.5) - aa, vec2(axis_width * 0.5) + aa, abs(p));

	vec3 c = mix(base_color, minor_color, max(minor.x, minor.y) * minor_fade);
	c = mix(c, major_color, max(major.x, major.y));
	c = mix(c, z_axis_color, axis.x);  // x == 0 is the Z axis
	c = mix(c, x_axis_color, axis.y);  // z == 0 is the X axis
	ALBEDO = c;
	ROUGHNESS = 0.9;
}
