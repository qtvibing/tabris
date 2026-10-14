import { readFile } from "node:fs/promises";
import { createTabris } from "./index.mjs";

const tabris = await createTabris(await readFile(process.argv[2]));

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

async function expectTypeError(action) {
  try {
    await action();
  } catch (error) {
    if (error instanceof TypeError) return;
    throw error;
  }
  throw new Error("expected TypeError");
}
const image = {
  data: new Uint8ClampedArray([
    255, 0, 0, 255, 0, 255, 0, 255,
    0, 0, 255, 255, 255, 255, 255, 255,
  ]),
  width: 2,
  height: 2,
};
const expected = "640f8b200b0aced06066d00d1f733e26";
const first = tabris.hash(image);
const second = tabris.hash(image);

expect(Buffer.from(first).toString("hex") === expected,
  "the WebAssembly result differs from the Zig reference");
expect(tabris.distance(first, second) === 0, "equal hashes differ");
expect(tabris.distance(new Uint8ClampedArray(16), new Uint8ClampedArray(16).fill(255)) === 128,
  "distance does not span the full hash");

await expectTypeError(() => tabris.hash({ data: new Uint8Array(3), width: 1, height: 1 }));
await expectTypeError(() => tabris.distance({
  [Symbol.toStringTag]: "Uint8Array",
  byteLength: 16,
}, first));
await expectTypeError(() => createTabris(Uint8Array.of(0, 97, 115, 109, 1, 0, 0, 0)));

const rgba = new Uint8ClampedArray(7 * 5 * 4);
for (let y = 0; y < 5; y++) {
  for (let x = 0; x < 7; x++) {
    const offset = (y * 7 + x) * 4;
    rgba.set([
      (x * 37 + y * 11) % 256,
      (x * 13 + y * 47) % 256,
      (x * 71 + y * 5) % 256,
      (x * 29 + y * 53) % 256,
    ], offset);
  }
}
const alphaHash = tabris.hash({ data: rgba, width: 7, height: 5 });
expect(Buffer.from(alphaHash).toString("hex") === "40343c4b343bfb8c0896c89abe671f9a",
  "the js sampling differs from the native implementation");
