const std = @import("std");

pub const plane_side = 16;
const samples_per_axis = 64;
const samples_per_cell = samples_per_axis / plane_side;
const samples_per_plane_cell = samples_per_cell * samples_per_cell;

pub const Planes = struct {
    light: [plane_side * plane_side]i16,
    red_blue: [plane_side * plane_side]i16,
    green: [plane_side * plane_side]i16,
};

/// Reduces RGBA to three 16x16 planes. Each cell pools a 4x4 stratified
/// grid. Subpixel interpolation suppresses phase aliasing at constant cost.
pub fn reduce(rgba: []const u8, width: usize, height: usize) Planes {
    var light = [_]i32{0} ** (plane_side * plane_side);
    var red_blue = [_]i32{0} ** (plane_side * plane_side);
    var green = [_]i32{0} ** (plane_side * plane_side);
    var x_samples: [samples_per_axis]AxisSample = undefined;
    for (0..samples_per_axis) |x| x_samples[x] = axisSample(width, x);

    for (0..samples_per_axis) |sample_y| {
        const y = axisSample(height, sample_y);
        const cell_y = sample_y / samples_per_cell;

        for (0..samples_per_axis) |sample_x| {
            const cell = cell_y * plane_side + sample_x / samples_per_cell;
            const color = bilinear(rgba, width, x_samples[sample_x], y);
            const r = color[0];
            const g = color[1];
            const b = color[2];

            light[cell] += 77 * r + 150 * g + 29 * b;
            red_blue[cell] += r - b;
            green[cell] += 2 * g - r - b;
        }
    }

    var result: Planes = undefined;
    for (0..plane_side * plane_side) |i| {
        result.light[i] = @intCast(@divTrunc(
            light[i] + samples_per_plane_cell * 128,
            samples_per_plane_cell * 256,
        ));
        result.red_blue[i] = @intCast(@divTrunc(red_blue[i], samples_per_plane_cell));
        result.green[i] = @intCast(@divTrunc(green[i], samples_per_plane_cell));
    }
    return result;
}

const AxisSample = struct {
    low: usize,
    high: usize,
    weight: u8,
};

/// Maps one of 64 sample positions on an axis to a bilinear footprint: two
/// adjacent pixel centers and a 0...128 blend weight. The arithmetic is exact
/// fixed-point, so the same image always yields the same planes and needs no
/// floating point. The first branch clamps a sample that falls before the
/// first pixel.
fn axisSample(size: usize, sample: usize) AxisSample {
    const numerator = sample * 2 + 1;
    const denominator = samples_per_axis * 2;
    const half = denominator / 2;
    const whole = (size / denominator) * numerator +
        ((size % denominator) * numerator) / denominator;
    const remainder = ((size % denominator) * numerator) % denominator;
    if (whole == 0 and remainder < half) return .{ .low = 0, .high = 0, .weight = 0 };

    const low = if (remainder < half) whole - 1 else whole;
    return .{
        .low = @min(low, size - 1),
        .high = @min(low + 1, size - 1),
        .weight = @intCast((if (remainder < half) remainder + half else remainder - half) *
            128 / denominator),
    };
}

const Color = @Vector(4, i32);

// All weights are fixed-point 1/128 fractions. The divisor 16384 is
// 128 * 128. The +8192 rounds instead of truncates.
fn bilinear(rgba: []const u8, width: usize, x: AxisSample, y: AxisSample) Color {
    const top_left = colorAt(rgba, (y.low * width + x.low) * 4);
    const top_right = colorAt(rgba, (y.low * width + x.high) * 4);
    const bottom_left = colorAt(rgba, (y.high * width + x.low) * 4);
    const bottom_right = colorAt(rgba, (y.high * width + x.high) * 4);
    const x_high: i32 = x.weight;
    const y_high: i32 = y.weight;
    const x_low = 128 - x_high;
    const y_low = 128 - y_high;
    return @divTrunc(
        top_left * @as(Color, @splat(x_low * y_low)) +
            top_right * @as(Color, @splat(x_high * y_low)) +
            bottom_left * @as(Color, @splat(x_low * y_high)) +
            bottom_right * @as(Color, @splat(x_high * y_high)) +
            @as(Color, @splat(8192)),
        @as(Color, @splat(16384)),
    );
}

fn colorAt(rgba: []const u8, offset: usize) Color {
    const pixel: @Vector(4, u8) = rgba[offset..][0..4].*;
    if (pixel[3] == 255) return @intCast(pixel);
    return .{
        composite(pixel[0], pixel[3]),
        composite(pixel[1], pixel[3]),
        composite(pixel[2], pixel[3]),
        255,
    };
}

fn composite(channel: i32, alpha: u8) i32 {
    const value: u32 = @intCast(channel * alpha + 128 * (255 - @as(i32, alpha)));
    const rounded = value + 128;
    return @intCast((rounded + (rounded >> 8)) >> 8);
}

test "sample positions cover image without overflow" {
    try std.testing.expectEqual(AxisSample{ .low = 0, .high = 0, .weight = 0 }, axisSample(1, 0));
    try std.testing.expectEqual(AxisSample{ .low = 63, .high = 63, .weight = 0 }, axisSample(64, 63));
    try std.testing.expectEqual(AxisSample{ .low = 992_187, .high = 992_188, .weight = 0 }, axisSample(1_000_000, 63));
}

test "uniform color remains uniform" {
    const pixel = [_]u8{ 40, 100, 220, 255 };
    const pixels = pixel ** (23 * 19);
    const plane = reduce(&pixels, 23, 19);

    for (plane.light) |value| try std.testing.expectEqual(@as(i16, 96), value);
    for (plane.red_blue) |value| try std.testing.expectEqual(@as(i16, -180), value);
    for (plane.green) |value| try std.testing.expectEqual(@as(i16, -60), value);
}

test "fully transparent pixels have canonical color" {
    var black = [_]u8{ 0, 0, 0, 0 } ** 4;
    var colored = [_]u8{ 250, 17, 90, 0 } ** 4;

    const a = reduce(&black, 2, 2);
    const b = reduce(&colored, 2, 2);
    try std.testing.expectEqualSlices(i16, &a.light, &b.light);
    try std.testing.expectEqualSlices(i16, &a.red_blue, &b.red_blue);
    try std.testing.expectEqualSlices(i16, &a.green, &b.green);
}
