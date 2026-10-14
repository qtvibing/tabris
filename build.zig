const std = @import("std");

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});

    const tabris = b.addModule("tabris", .{
        .root_source_file = b.path("src/root.zig"),
        .target = target,
        .optimize = optimize,
    });

    const c_api = b.createModule(.{
        .root_source_file = b.path("src/c_api.zig"),
        .target = target,
        .optimize = optimize,
        .strip = optimize != .Debug,
        .imports = &.{.{ .name = "tabris", .module = tabris }},
    });
    const shared_library = b.addLibrary(.{
        .name = "tabris",
        .root_module = c_api,
        .linkage = .dynamic,
    });
    shared_library.installHeader(b.path("include/tabris.h"), "tabris.h");
    b.installArtifact(shared_library);

    const static_library = b.addLibrary(.{
        .name = "tabris",
        .root_module = c_api,
        .linkage = .static,
    });
    b.installArtifact(static_library);

    const wasm_target = b.resolveTargetQuery(.{
        .cpu_arch = .wasm32,
        .os_tag = .freestanding,
    });
    const wasm_core = b.createModule(.{
        .root_source_file = b.path("src/root.zig"),
        .target = wasm_target,
        .optimize = optimize,
    });
    const wasm = b.addExecutable(.{
        .name = "tabris",
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/wasm_api.zig"),
            .target = wasm_target,
            .optimize = optimize,
            .strip = optimize != .Debug,
            .imports = &.{.{ .name = "tabris", .module = wasm_core }},
        }),
    });
    wasm.entry = .disabled;
    wasm.rdynamic = true;
    wasm.export_memory = true;
    const install_wasm = b.addInstallArtifact(wasm, .{});
    const wasm_step = b.step("wasm", "Build the WebAssembly module");
    wasm_step.dependOn(&install_wasm.step);

    const install_js_wasm = b.addInstallArtifact(wasm, .{
        .dest_dir = .{ .override = .prefix },
        .dest_sub_path = "js/tabris.wasm",
    });
    const install_js = b.addInstallFile(b.path("js/index.mjs"), "js/index.mjs");
    const install_js_types = b.addInstallFile(b.path("js/index.d.mts"), "js/index.d.mts");
    const js_step = b.step("js", "Stage the JavaScript and WebAssembly library");
    js_step.dependOn(&install_js_wasm.step);
    js_step.dependOn(&install_js.step);
    js_step.dependOn(&install_js_types.step);

    const run_js_tests = b.addSystemCommand(&.{ "node", "js/index.test.mjs" });
    run_js_tests.addFileArg(wasm.getEmittedBin());
    const js_test_step = b.step("test-js", "Test the JavaScript binding");
    js_test_step.dependOn(&run_js_tests.step);

    const benchmark_core = b.createModule(.{
        .root_source_file = b.path("src/root.zig"),
        .target = target,
        .optimize = .ReleaseFast,
    });
    const benchmark = b.addExecutable(.{
        .name = "benchmark",
        .root_module = b.createModule(.{
            .root_source_file = b.path("bench/benchmark.zig"),
            .target = target,
            .optimize = .ReleaseFast,
            .imports = &.{.{ .name = "tabris", .module = benchmark_core }},
        }),
    });
    const run_benchmark = b.addRunArtifact(benchmark);
    const benchmark_step = b.step("bench", "Run the throughput benchmark");
    benchmark_step.dependOn(&run_benchmark.step);

    const c_api_module = b.createModule(.{
        .target = target,
        .optimize = optimize,
        .link_libc = true,
    });
    c_api_module.addCSourceFile(.{
        .file = b.path("tests/c_api.c"),
        .flags = &.{ "-std=c11", "-Wall", "-Wextra", "-Werror" },
    });
    c_api_module.addIncludePath(b.path("include"));
    c_api_module.linkLibrary(static_library);
    const run_c_api_test = b.addRunArtifact(b.addExecutable(.{
        .name = "c-api-test",
        .root_module = c_api_module,
    }));

    const core_tests = b.addRunArtifact(b.addTest(.{ .root_module = tabris }));
    const api_tests = b.addRunArtifact(b.addTest(.{ .root_module = c_api }));
    const test_step = b.step("test", "Run the Zig tests");
    test_step.dependOn(&core_tests.step);
    test_step.dependOn(&api_tests.step);

    const check_step = b.step("check", "Run Zig, C, and JavaScript tests");
    check_step.dependOn(&core_tests.step);
    check_step.dependOn(&api_tests.step);
    check_step.dependOn(&run_c_api_test.step);
    check_step.dependOn(&run_js_tests.step);
}
