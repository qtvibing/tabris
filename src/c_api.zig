const std = @import("std");
const tabris = @import("tabris");

const distance_error = std.math.maxInt(u8);

pub export fn tabris_hash_rgba(
    pixels: ?[*]const u8,
    width: usize,
    height: usize,
    output: ?*[16]u8,
) callconv(.c) bool {
    const pixel_count = @mulWithOverflow(width, height);
    if (pixel_count[1] != 0) return false;
    const byte_count = @mulWithOverflow(pixel_count[0], 4);
    if (byte_count[1] != 0 or byte_count[0] == 0) return false;

    const source = pixels orelse return false;
    const destination = output orelse return false;
    destination.* = tabris.hash(.{
        .pixels = source[0..byte_count[0]],
        .width = width,
        .height = height,
    }) catch return false;
    return true;
}

pub export fn tabris_distance(a: ?*const [16]u8, b: ?*const [16]u8) callconv(.c) u8 {
    return tabris.distance((a orelse return distance_error).*, (b orelse return distance_error).*);
}

test "C API hashes packed RGBA" {
    const pixels = [_]u8{
        255, 0, 0,   255, 0,   255, 0,   255,
        0,   0, 255, 255, 255, 255, 255, 255,
    };
    const expected = [_]u8{
        0x64, 0x0f, 0x8b, 0x20, 0x0b, 0x0a, 0xce, 0xd0,
        0x60, 0x66, 0xd0, 0x0d, 0x1f, 0x73, 0x3e, 0x26,
    };
    var output: [16]u8 = undefined;

    try std.testing.expect(tabris_hash_rgba(&pixels, 2, 2, &output));
    try std.testing.expectEqual(expected, output);
    try std.testing.expectEqual(@as(u8, 0), tabris_distance(&output, &expected));
}

test "C API rejects null pointers" {
    const pixel = [_]u8{ 0, 0, 0, 255 };
    var output: [16]u8 = undefined;
    try std.testing.expect(!tabris_hash_rgba(null, 1, 1, &output));
    try std.testing.expect(!tabris_hash_rgba(&pixel, 1, 1, null));
    try std.testing.expectEqual(distance_error, tabris_distance(null, null));
}
