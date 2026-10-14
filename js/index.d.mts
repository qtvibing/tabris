export type ByteArray = Uint8Array | Uint8ClampedArray;

export interface ImageDataLike {
  readonly data: ByteArray;
  readonly width: number;
  readonly height: number;
}

export interface Tabris {
  hash(image: ImageDataLike): Uint8Array;
  distance(a: ByteArray, b: ByteArray): number;
}

export type WasmSource = BufferSource | WebAssembly.Module | {
  arrayBuffer(): Promise<ArrayBuffer>;
};

export function createTabris(source: WasmSource): Promise<Tabris>;
export function distance(a: ByteArray, b: ByteArray): number;
