// The wrapper resamples the input to 64x64 RGBA before it enters wasm.
// This bounds the wasm memory transfer and keeps the allocation to one
// fixed-size block. It mirrors the fixed-point arithmetic of src/sample.zig
// so both entry points produce identical hashes.
export async function createTabris(source) {
  if (source && typeof source.arrayBuffer === "function") {
    source = await source.arrayBuffer();
  }

  const result = await WebAssembly.instantiate(source);
  const wasm = result.instance?.exports ?? result.exports;
  if (!(wasm.memory instanceof WebAssembly.Memory) ||
      typeof wasm.tabris_alloc !== "function" ||
      typeof wasm.tabris_free !== "function" ||
      typeof wasm.tabris_hash_rgba !== "function") {
    throw new TypeError("incompatible tabris WebAssembly module");
  }

  function hash(image) {
    const { data, width, height } = image;
    const byteLength = width * height * 4;
    if (!Number.isSafeInteger(width) || !Number.isSafeInteger(height) ||
        !Number.isSafeInteger(byteLength) || width < 1 || height < 1 ||
        !isBytes(data, byteLength)) {
      throw new TypeError("expected packed RGBA image data");
    }

    const sampleLength = 64 * 64 * 4;
    const allocationLength = sampleLength + 16;
    const pointer = wasm.tabris_alloc(allocationLength) >>> 0;
    if (!pointer) throw new RangeError("unable to allocate WebAssembly memory");

    try {
      const sampled = new Uint8Array(wasm.memory.buffer, pointer, sampleLength);
      const columns = Array.from({ length: 64 }, (_, x) => axisSample(width, x));
      for (let sampleY = 0; sampleY < 64; sampleY++) {
        const y = axisSample(height, sampleY);
        for (let sampleX = 0; sampleX < 64; sampleX++) {
          const target = (sampleY * 64 + sampleX) * 4;
          samplePixel(sampled, target, data, width, columns[sampleX], y);
        }
      }

      const output = pointer + sampleLength;
      if (!wasm.tabris_hash_rgba(pointer, 64, 64, output)) {
        throw new Error("the WebAssembly hash call failed");
      }
      return new Uint8Array(wasm.memory.buffer, output, 16).slice();
    } finally {
      wasm.tabris_free(pointer, allocationLength);
    }
  }

  return Object.freeze({ hash, distance });
}

export function distance(a, b) {
  if (!isBytes(a, 16) || !isBytes(b, 16)) {
    throw new TypeError("expected two 128-bit hashes");
  }

  let total = 0;
  for (let i = 0; i < 16; i++) {
    let value = a[i] ^ b[i];
    while (value) {
      value &= value - 1;
      total++;
    }
  }
  return total;
}

function axisSample(size, sample) {
  const numerator = sample * 2 + 1;
  const whole = Math.floor(size / 128) * numerator +
    Math.floor((size % 128) * numerator / 128);
  const remainder = (size % 128) * numerator % 128;
  if (whole === 0 && remainder < 64) return [0, 0, 0];

  const low = remainder < 64 ? whole - 1 : whole;
  if (low >= size - 1) return [size - 1, size - 1, 0];
  const weight = remainder < 64 ? remainder + 64 : remainder - 64;
  return [low, low + 1, weight];
}

function samplePixel(output, target, source, width, x, y) {
  const topLeft = (y[0] * width + x[0]) * 4;
  const topRight = (y[0] * width + x[1]) * 4;
  const bottomLeft = (y[1] * width + x[0]) * 4;
  const bottomRight = (y[1] * width + x[1]) * 4;
  const topLeftWeight = (128 - x[2]) * (128 - y[2]);
  const topRightWeight = x[2] * (128 - y[2]);
  const bottomLeftWeight = (128 - x[2]) * y[2];
  const bottomRightWeight = x[2] * y[2];

  for (let channel = 0; channel < 3; channel++) {
    const value = composite(source, topLeft, channel) * topLeftWeight +
      composite(source, topRight, channel) * topRightWeight +
      composite(source, bottomLeft, channel) * bottomLeftWeight +
      composite(source, bottomRight, channel) * bottomRightWeight;
    output[target + channel] = Math.floor((value + 8192) / 16384);
  }
  output[target + 3] = 255;
}

function composite(source, offset, channel) {
  const alpha = source[offset + 3];
  if (alpha === 255) return source[offset + channel];
  const value = source[offset + channel] * alpha + 128 * (255 - alpha) + 128;
  return (value + (value >> 8)) >> 8;
}

function isBytes(value, length) {
  const type = Object.prototype.toString.call(value);
  return ArrayBuffer.isView(value) &&
    (type === "[object Uint8Array]" ||
      type === "[object Uint8ClampedArray]") && value.byteLength === length;
}
