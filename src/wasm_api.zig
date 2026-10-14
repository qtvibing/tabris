const std = @import("std");
const tabris = @import("tabris");

const allocator = std.heap.wasm_allocator;

pub export fn tabris_alloc(length: usize) ?[*]u8 {
    const memory = allocator.alloc(u8, length) catch return null;
    return memory.ptr;
}

pub export fn tabris_free(memory: ?[*]u8, length: usize) void {
    const pointer = memory orelse return;
    allocator.free(pointer[0..length]);
}

pub export fn tabris_hash_rgba(
    pixels: [*]const u8,
    width: usize,
    height: usize,
    output: *[16]u8,
) bool {
    const pixel_count = @mulWithOverflow(width, height);
    if (pixel_count[1] != 0) return false;
    const byte_count = @mulWithOverflow(pixel_count[0], 4);
    if (byte_count[1] != 0 or byte_count[0] == 0) return false;

    output.* = tabris.hash(.{
        .pixels = pixels[0..byte_count[0]],
        .width = width,
        .height = height,
    }) catch return false;
    return true;
}
