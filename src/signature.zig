const sample = @import("sample.zig");

const side = sample.plane_side;
const plane_len = side * side;
const regions = 16;

const bit = struct {
    const center_light = 63;
    const horizontal_edge = 64;
    const vertical_edge = 80;
    const orientation = 96;
    const activity = 102;
    const contrast = 106;
    const center_activity = 110;
    const center_contrast = 111;
    const color = 112;
    const saturation = 118;
    const red_blue_detail = 120;
    const green_detail = 124;
};

pub fn build(planes: *const sample.Planes) [16]u8 {
    var result = [_]u8{0} ** 16;

    var coarse: [64]i32 = undefined;
    for (0..8) |y| {
        for (0..8) |x| {
            const i = (y * 2) * side + x * 2;
            coarse[y * 8 + x] = planes.light[i] + planes.light[i + 1] +
                planes.light[i + side] + planes.light[i + side + 1];
        }
    }
    hadamard2d(8, &coarse);
    for (1..64) |i| set(&result, i - 1, coarse[i] > 0);

    var center: i32 = 0;
    var border: i32 = 0;
    for (0..side) |y| {
        for (0..side) |x| {
            if (x >= 4 and x < 12 and y >= 4 and y < 12)
                center += planes.light[y * side + x]
            else
                border += planes.light[y * side + x];
        }
    }
    set(&result, bit.center_light, center * 3 > border);

    var horizontal = [_]u32{0} ** regions;
    var vertical = [_]u32{0} ** regions;
    for (0..side) |y| {
        for (0..side) |x| {
            const block = (y / 4) * 4 + x / 4;
            const left = if (x == 0) x else x - 1;
            const right = if (x == side - 1) x else x + 1;
            const top = if (y == 0) y else y - 1;
            const bottom = if (y == side - 1) y else y + 1;
            horizontal[block] += absDiff(
                planes.light[y * side + left],
                planes.light[y * side + right],
            );
            vertical[block] += absDiff(
                planes.light[top * side + x],
                planes.light[bottom * side + x],
            );
        }
    }

    var horizontal_total: u32 = 0;
    var vertical_total: u32 = 0;
    for (0..regions) |i| {
        horizontal_total += horizontal[i];
        vertical_total += vertical[i];
    }
    for (0..regions) |i| {
        set(&result, bit.horizontal_edge + i, horizontal[i] * regions > horizontal_total);
        set(&result, bit.vertical_edge + i, vertical[i] * regions > vertical_total);
    }
    encodeGeometry(&result, &planes.light);

    const red_blue = colorTransform(&planes.red_blue);
    const green = colorTransform(&planes.green);
    encodeColor(&result, coarse[0], red_blue[0] * 2, green[0]);

    // Haar 4x4 detail coefficients of the chroma planes. Coefficient 0 is the
    // mean and is consumed by encodeColor. 1 and 2 carry horizontal and
    // vertical structure. 4 and 5 carry the first diagonal band. Signs only.
    const chroma_coefficients = [_]usize{ 1, 4, 5, 2 };
    for (chroma_coefficients, bit.red_blue_detail..) |coefficient, index|
        set(&result, index, red_blue[coefficient] > 0);
    for (chroma_coefficients, bit.green_detail..) |coefficient, index|
        set(&result, index, green[coefficient] > 0);
    return result;
}

fn encodeGeometry(result: *[16]u8, light: *const [plane_len]i16) void {
    var orientation = [_]u32{0} ** 4;
    var activity = [_]u32{0} ** 4;
    var contrast = [_]u32{0} ** 4;
    var light_total: i32 = 0;
    for (light) |value| light_total += value;

    var center_activity: u32 = 0;
    var center_contrast: u32 = 0;
    var total_activity: u32 = 0;
    var total_contrast: u32 = 0;
    for (1..side - 1) |y| {
        for (1..side - 1) |x| {
            const i = y * side + x;
            const dx = @as(i32, light[i + 1]) - light[i - 1];
            const dy = @as(i32, light[i + side]) - light[i - side];
            const local_activity = magnitude(dx) + magnitude(dy);
            const local_contrast = magnitude(@as(i32, light[i]) * 256 - light_total);
            const quadrant = (y / 8) * 2 + x / 8;

            orientation[0] += magnitude(dx);
            orientation[1] += magnitude(dx + dy);
            orientation[2] += magnitude(dy);
            orientation[3] += magnitude(dx - dy);
            activity[quadrant] += local_activity;
            contrast[quadrant] += local_contrast;
            total_activity += local_activity;
            total_contrast += local_contrast;
            if (x >= 4 and x < 12 and y >= 4 and y < 12) {
                center_activity += local_activity;
                center_contrast += local_contrast;
            }
        }
    }

    // 181 is 256 / sqrt(2). The diagonal projections (dx + dy, dx - dy) run
    // sqrt(2) times longer than the axial ones. Scale them down before the
    // pairwise comparisons.
    const pairs = [_][2]u8{ .{ 0, 1 }, .{ 0, 2 }, .{ 0, 3 }, .{ 1, 2 }, .{ 1, 3 }, .{ 2, 3 } };
    const scale = [_]u32{ 256, 181, 256, 181 };
    for (pairs, bit.orientation..) |pair, index|
        set(result, index, orientation[pair[0]] * scale[pair[0]] >
            orientation[pair[1]] * scale[pair[1]]);
    for (0..4) |i| {
        set(result, bit.activity + i, activity[i] * 4 > total_activity);
        set(result, bit.contrast + i, contrast[i] * 4 > total_contrast);
    }
    // The interior is 14x14 cells and the center is 8x8, so the center holds
    // 64 of the 196 samples. 33/16 is 64/132 in lowest terms. The test asks
    // whether the center is denser than the rest.
    set(result, bit.center_activity, center_activity * 33 > (total_activity - center_activity) * 16);
    set(result, bit.center_contrast, center_contrast * 33 > (total_contrast - center_contrast) * 16);
}

fn colorTransform(plane: *const [plane_len]i16) [16]i32 {
    var coarse: [16]i32 = undefined;
    for (0..4) |y| {
        for (0..4) |x| {
            var sum: i32 = 0;
            for (0..4) |dy| {
                for (0..4) |dx|
                    sum += plane[(y * 4 + dy) * side + x * 4 + dx];
            }
            coarse[y * 4 + x] = sum;
        }
    }
    haar2d(4, &coarse);
    return coarse;
}

fn encodeColor(result: *[16]u8, light: i32, x: i32, y: i32) void {
    // Six sign tests of the mean chroma vector (r - b, 2g - r - b). Four
    // projections at 45-degree steps plus the two axes.
    const projections = [_]i32{
        x,
        2 * x + y,
        x + 2 * y,
        y,
        -x + 2 * y,
        -2 * x + y,
    };
    for (projections, bit.color..) |projection, index|
        set(result, index, projection > 0);

    const chroma = @abs(x) + @abs(y);
    // Two saturation thresholds, moderate and strong, in the (chroma, light)
    // plane.
    set(result, bit.saturation, chroma * 4 > light);
    set(result, bit.saturation + 1, chroma * 4 > light * 3);
}

fn hadamard2d(comptime n: usize, values: *[n * n]i32) void {
    var line: [n]i32 = undefined;
    for (0..n) |y| {
        for (0..n) |x| line[x] = values[y * n + x];
        hadamard(n, &line);
        for (0..n) |x| values[y * n + x] = line[x];
    }
    for (0..n) |x| {
        for (0..n) |y| line[y] = values[y * n + x];
        hadamard(n, &line);
        for (0..n) |y| values[y * n + x] = line[y];
    }
}

fn hadamard(comptime n: usize, values: *[n]i32) void {
    var width: usize = 1;
    while (width < n) : (width *= 2) {
        var start: usize = 0;
        while (start < n) : (start += width * 2) {
            for (0..width) |i| {
                const a = values[start + i];
                const b = values[start + width + i];
                values[start + i] = a + b;
                values[start + width + i] = a - b;
            }
        }
    }
}

fn haar2d(comptime n: usize, values: *[n * n]i32) void {
    var line: [n]i32 = undefined;
    for (0..n) |y| {
        for (0..n) |x| line[x] = values[y * n + x];
        haar(n, &line);
        for (0..n) |x| values[y * n + x] = line[x];
    }
    for (0..n) |x| {
        for (0..n) |y| line[y] = values[y * n + x];
        haar(n, &line);
        for (0..n) |y| values[y * n + x] = line[y];
    }
}

fn haar(comptime n: usize, values: *[n]i32) void {
    var tmp: [n]i32 = undefined;
    var width = n;
    while (width > 1) : (width /= 2) {
        const half = width / 2;
        for (0..half) |i| {
            tmp[i] = values[i * 2] + values[i * 2 + 1];
            tmp[half + i] = values[i * 2] - values[i * 2 + 1];
        }
        for (0..width) |i| values[i] = tmp[i];
    }
}

fn absDiff(a: i16, b: i16) u32 {
    return magnitude(@as(i32, a) - b);
}

fn magnitude(value: i32) u32 {
    return @intCast(if (value < 0) -value else value);
}

fn set(hash: *[16]u8, index: usize, value: bool) void {
    if (value) hash[index / 8] |= @as(u8, 1) << @intCast(index % 8);
}
