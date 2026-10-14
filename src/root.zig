//! tabris is a compact 128-bit perceptual image hashing library.

const std = @import("std");
const sample = @import("sample.zig");
const signature = @import("signature.zig");

pub const Hash = [16]u8;

pub const Image = struct {
    pixels: []const u8,
    width: usize,
    height: usize,
};

pub const HashError = error{InvalidImage};

pub fn hash(image: Image) HashError!Hash {
    if (image.width == 0 or image.height == 0) return error.InvalidImage;

    const pixels = std.math.mul(usize, image.width, image.height) catch
        return error.InvalidImage;
    const bytes = std.math.mul(usize, pixels, 4) catch
        return error.InvalidImage;
    if (image.pixels.len != bytes) return error.InvalidImage;

    const planes = sample.reduce(image.pixels, image.width, image.height);
    return signature.build(&planes);
}

pub fn distance(a: Hash, b: Hash) u8 {
    var total: u8 = 0;
    for (a, b) |left, right| total += @popCount(left ^ right);
    return total;
}

test "reference hash" {
    const pixels = [_]u8{
        255, 0, 0,   255, 0,   255, 0,   255,
        0,   0, 255, 255, 255, 255, 255, 255,
    };
    const expected: Hash = .{
        0x64, 0x0f, 0x8b, 0x20, 0x0b, 0x0a, 0xce, 0xd0,
        0x60, 0x66, 0xd0, 0x0d, 0x1f, 0x73, 0x3e, 0x26,
    };

    try std.testing.expectEqual(expected, try hash(.{
        .pixels = &pixels,
        .width = 2,
        .height = 2,
    }));
}

test "brightness shift preserves structure" {
    var dark: [32 * 32 * 4]u8 = undefined;
    var bright: [32 * 32 * 4]u8 = undefined;
    for (0..32) |y| {
        for (0..32) |x| {
            const offset = (y * 32 + x) * 4;
            const value: u8 = @intCast(20 + x * 3 + y * 2);
            dark[offset..][0..4].* = .{ value, value, value, 255 };
            bright[offset..][0..4].* = .{ value + 30, value + 30, value + 30, 255 };
        }
    }

    const a = try hash(.{ .pixels = &dark, .width = 32, .height = 32 });
    const b = try hash(.{ .pixels = &bright, .width = 32, .height = 32 });
    try std.testing.expectEqual(a, b);
}

test "uniform hue is represented independently of brightness" {
    const red = [_]u8{ 255, 0, 0, 255 };
    const dark_red = [_]u8{ 128, 0, 0, 255 };
    const blue = [_]u8{ 0, 0, 255, 255 };

    const red_hash = try hash(.{ .pixels = &red, .width = 1, .height = 1 });
    const dark_red_hash = try hash(.{ .pixels = &dark_red, .width = 1, .height = 1 });
    const blue_hash = try hash(.{ .pixels = &blue, .width = 1, .height = 1 });
    try std.testing.expectEqual(red_hash, dark_red_hash);
    try std.testing.expect(distance(red_hash, blue_hash) > 0);
}

test "distance spans the complete hash" {
    const zero = [_]u8{0} ** 16;
    const one = [_]u8{0xff} ** 16;

    try std.testing.expectEqual(@as(u8, 0), distance(zero, zero));
    try std.testing.expectEqual(@as(u8, 128), distance(zero, one));
    try std.testing.expectEqual(distance(zero, one), distance(one, zero));
}

test "invalid images are rejected" {
    try std.testing.expectError(error.InvalidImage, hash(.{
        .pixels = &.{},
        .width = 0,
        .height = 1,
    }));
    try std.testing.expectError(error.InvalidImage, hash(.{
        .pixels = &.{ 0, 0, 0 },
        .width = 1,
        .height = 1,
    }));
}
