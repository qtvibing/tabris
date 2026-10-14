from __future__ import annotations

import ctypes
import subprocess
import sys
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

HashMethod = Callable[[Image.Image], bytes]


class Tabris:
    def __init__(self, root: Path) -> None:
        subprocess.run(
            ["zig", "build", "-Doptimize=ReleaseFast"],
            cwd=root,
            check=True,
        )
        candidates = {
            "linux": [root / "zig-out/lib/libtabris.so"],
            "darwin": [root / "zig-out/lib/libtabris.dylib"],
            "win32": [root / "zig-out/bin/tabris.dll", root / "zig-out/lib/tabris.dll"],
        }.get(sys.platform, [])
        library = next((path for path in candidates if path.is_file()), None)
        if library is None:
            raise RuntimeError(f"cannot locate the Tabris shared library for {sys.platform}")

        self.library = ctypes.CDLL(str(library))
        self.library.tabris_hash_rgba.argtypes = [
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
        ]
        self.library.tabris_hash_rgba.restype = ctypes.c_bool

    def __call__(self, image: Image.Image) -> bytes:
        rgba = image.convert("RGBA")
        raw = rgba.tobytes()
        source = (ctypes.c_uint8 * len(raw)).from_buffer_copy(raw)
        output = (ctypes.c_uint8 * 16)()
        if not self.library.tabris_hash_rgba(source, rgba.width, rgba.height, output):
            raise RuntimeError("tabris rejected a decoded image")
        return bytes(output)


def average_hash(image: Image.Image) -> bytes:
    values = np.asarray(
        image.convert("L").resize((8, 8), Image.Resampling.LANCZOS),
        dtype=np.float32,
    )
    return np.packbits(values > values.mean(), bitorder="little").tobytes()


def difference_hash(image: Image.Image) -> bytes:
    values = np.asarray(
        image.convert("L").resize((9, 8), Image.Resampling.LANCZOS),
        dtype=np.int16,
    )
    return np.packbits(values[:, :-1] > values[:, 1:], bitorder="little").tobytes()


def dct_hash(image: Image.Image) -> bytes:
    values = np.asarray(
        image.convert("L").resize((32, 32), Image.Resampling.LANCZOS),
        dtype=np.float64,
    )
    low = (_DCT @ values @ _DCT.T)[:8, :8]
    threshold = np.median(low.ravel()[1:])
    return np.packbits(low > threshold, bitorder="little").tobytes()


def methods(root: Path) -> dict[str, tuple[int, HashMethod]]:
    return {
        "tabris": (128, Tabris(root)),
        "phash": (64, dct_hash),
        "dhash": (64, difference_hash),
        "ahash": (64, average_hash),
    }


_axis = np.arange(32)
_frequency = np.arange(32)[:, None]
_DCT = np.cos(np.pi / 32 * (_axis + 0.5) * _frequency) * np.sqrt(2 / 32)
_DCT[0, :] /= np.sqrt(2)
