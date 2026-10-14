# tabris

this is a small research project made for personal use on a private project.
it is not polished, not ready for real world use, and not really intended to
be public. do not expect maintenance, support, or stability. its usecase is
quite narrow and designed to fit the project it was created for, which is
why some of the methodology might not make perfect sense for general use.

tabris is a dependency-free 128-bit perceptual image hash written in zig.
the input is decoded RGBA8 pixels. the output is a 16-byte hash. you compare
two hashes with the hamming distance, from 0 to 128. images that differ by
compression, resizing, photometric edits, or color grading have similar
hashes. unrelated images have different hashes. tabris is not a
cryptographic hash. it does not recognize objects.

## how it works

the pipeline has two stages. all arithmetic is integer arithmetic. the work
per image is fixed. the core does not allocate memory.

**sampling** (`src/sample.zig`). the algorithm samples each image at
64 x 64 = 4,096 positions. each position maps to a bilinear footprint over
four adjacent pixels. the mapping uses exact fixed-point rational arithmetic.
the result is deterministic on all platforms and needs no floating point.
straight alpha is composited onto neutral gray before sampling. fully
transparent pixels get one canonical color. the algorithm pools the samples
into three 16 x 16 planes: one luminance plane and two opponent-color planes
(r - b, 2g - r - b). each pixel subtracts the green midpoint. the
opponent-color planes are therefore stable under brightness change.

**signature** (`src/signature.zig`). the 128 bits are allocated as follows:

| bits | feature |
|---:|---|
| 0–63 | sign bits of the 8 x 8 hadamard transform of the pooled luminance |
| 64–95 | per-region horizontal and vertical edge activity, above or below the mean region |
| 96–111 | gradient orientation (4 directions, 6 pairwise tests), quadrant activity and contrast, center density |
| 112–127 | mean color sign tests at 45-degree steps, two saturation thresholds, haar chroma detail signs |

the hadamard and haar transforms are fast integer transforms. the algorithm
uses sign bits, not magnitudes, because signs survive quantization and
brightness shifts better. color gets only 16 of 128 bits. this is
intentional: structure is the primary feature. color stays useful but does
not dominate. the tuning and the corpus measurements are in
`quality/README.md`.

## build

zig 0.16.0 or newer is required. node 18 or newer is required for the js
checks.

```sh
zig build test                          # zig tests
zig build check -Doptimize=ReleaseSafe  # zig, C, and js/wasm checks
zig build -Doptimize=ReleaseFast        # C libraries and header
zig build js -Doptimize=ReleaseSmall    # stages js/ with tabris.wasm
zig build bench
```

zig build writes the native libraries to `zig-out/lib` and the header to
`zig-out/include`. zig build js writes the js library to `zig-out/js`. the
js library accepts an `ImageData`-like object:

```js
const tabris = await createTabris(await readFile("zig-out/js/tabris.wasm"));
tabris.hash(imageData);
```

the js wrapper resamples the image to 64 x 64 before the wasm call. this
limits the wasm memory traffic and reproduces the native sampling
arithmetic exactly. C callers use `include/tabris.h`. the quality harness
under `quality/` is a separate uv project. see `quality/README.md`.

## known limits

large crops and rotations are not handled. mirroring and solarization are
intentionally not treated as invariants. the input must be decoded pixels.
image decoding is out of scope.
