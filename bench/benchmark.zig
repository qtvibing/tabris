const std = @import("std");
const tabris = @import("tabris");

pub fn main(init: std.process.Init) !void {
    const width = 1920;
    const height = 1080;
    const rounds = 200_000;

    const pixels = try init.arena.allocator().alloc(u8, width * height * 4);
    var state: u32 = 0x9e3779b9;
    for (0..width * height) |i| {
        for (0..3) |channel| {
            state = state *% 1_664_525 +% 1_013_904_223;
            pixels[i * 4 + channel] = @truncate(state >> 16);
        }
        pixels[i * 4 + 3] = 255;
    }

    const image: tabris.Image = .{
        .pixels = pixels,
        .width = width,
        .height = height,
    };
    for (0..100) |_| std.mem.doNotOptimizeAway(try tabris.hash(image));

    const start = std.Io.Clock.awake.now(init.io);
    for (0..rounds) |_| std.mem.doNotOptimizeAway(try tabris.hash(image));
    const elapsed = start.durationTo(std.Io.Clock.awake.now(init.io));

    const nanoseconds: f64 = @floatFromInt(elapsed.nanoseconds);
    const per_hash = nanoseconds / rounds;
    std.debug.print("{d:.0} hashes/s  {d:.2} us/hash\n", .{
        1_000_000_000.0 / per_hash,
        per_hash / 1_000.0,
    });
}
