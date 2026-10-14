from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from typing import Callable

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

Apply = Callable[[Image.Image, str], Image.Image]


@dataclass(frozen=True)
class Transform:
    name: str
    group: str
    apply: Apply


def _simple(function: Callable[[Image.Image], Image.Image]) -> Apply:
    return lambda image, _: function(image)


def _encoded(image: Image.Image, format_: str, **options: object) -> Image.Image:
    stream = BytesIO()
    image.convert("RGB").save(stream, format_, **options)
    stream.seek(0)
    with Image.open(stream) as decoded:
        return decoded.convert("RGB")


def _crop(image: Image.Image, fraction: float) -> Image.Image:
    x = round(image.width * fraction)
    y = round(image.height * fraction)
    return image.crop((x, y, image.width - x, image.height - y))


def _gamma(image: Image.Image, exponent: float) -> Image.Image:
    table = [round(255 * (value / 255) ** exponent) for value in range(256)]
    return image.point(table * 3)


def _noise(image: Image.Image, sigma: int, key: str) -> Image.Image:
    digest = hashlib.blake2b(
        f"{key}:noise:{sigma}".encode(), digest_size=8
    ).digest()
    seed = int.from_bytes(digest, "little")
    rng = np.random.default_rng(seed)
    values = np.asarray(image.convert("RGB"), dtype=np.int16)
    changed = np.clip(values + rng.normal(0, sigma, values.shape), 0, 255).astype(np.uint8)
    return Image.fromarray(changed)


def _hue(image: Image.Image, offset: int) -> Image.Image:
    hsv_image = image.convert("HSV")
    hsv = np.asarray(hsv_image, dtype=np.uint8).copy()
    hsv[:, :, 0] = (hsv[:, :, 0].astype(np.uint16) + offset) % 256
    return Image.frombytes("HSV", hsv_image.size, hsv.tobytes()).convert("RGB")


def _grade(image: Image.Image, gains: tuple[float, float, float]) -> Image.Image:
    values = np.asarray(image.convert("RGB"), dtype=np.float32)
    values *= np.asarray(gains, dtype=np.float32)
    return Image.fromarray(np.clip(values, 0, 255).astype(np.uint8))


def _duotone(
    image: Image.Image,
    shadows: tuple[int, int, int],
    highlights: tuple[int, int, int],
) -> Image.Image:
    return ImageOps.colorize(image.convert("L"), shadows, highlights)


def transformations() -> list[Transform]:
    return [
        Transform("jpeg_70", "codec", _simple(lambda image: _encoded(image, "JPEG", quality=70))),
        Transform("jpeg_30", "codec", _simple(lambda image: _encoded(image, "JPEG", quality=30))),
        Transform("jpeg_10", "codec", _simple(lambda image: _encoded(image, "JPEG", quality=10))),
        Transform("webp_40", "codec", _simple(lambda image: _encoded(image, "WEBP", quality=40))),
        Transform("resize_25", "filter", _simple(lambda image: image.resize(
            (max(1, image.width // 4), max(1, image.height // 4)), Image.Resampling.LANCZOS
        ))),
        Transform(
            "brightness_70",
            "photometric",
            _simple(lambda image: ImageEnhance.Brightness(image).enhance(0.7)),
        ),
        Transform(
            "brightness_130",
            "photometric",
            _simple(lambda image: ImageEnhance.Brightness(image).enhance(1.3)),
        ),
        Transform(
            "contrast_70",
            "photometric",
            _simple(lambda image: ImageEnhance.Contrast(image).enhance(0.7)),
        ),
        Transform(
            "contrast_130",
            "photometric",
            _simple(lambda image: ImageEnhance.Contrast(image).enhance(1.3)),
        ),
        Transform("gamma_70", "photometric", _simple(lambda image: _gamma(image, 0.7))),
        Transform("gamma_140", "photometric", _simple(lambda image: _gamma(image, 1.4))),
        Transform("grayscale", "color", _simple(lambda image: image.convert("L"))),
        Transform(
            "saturation_50",
            "color",
            _simple(lambda image: ImageEnhance.Color(image).enhance(0.5)),
        ),
        Transform(
            "saturation_150",
            "color",
            _simple(lambda image: ImageEnhance.Color(image).enhance(1.5)),
        ),
        Transform("hue_30", "color", lambda image, _: _hue(image, 21)),
        Transform("hue_90", "color", lambda image, _: _hue(image, 64)),
        Transform("hue_180", "color", lambda image, _: _hue(image, 128)),
        Transform("warm_grade", "color", _simple(lambda image: _grade(image, (1.12, 1.0, 0.86)))),
        Transform("cool_grade", "color", _simple(lambda image: _grade(image, (0.88, 1.0, 1.14)))),
        Transform(
            "sepia",
            "color",
            _simple(lambda image: _duotone(image, (24, 12, 5), (245, 220, 170))),
        ),
        Transform(
            "cyanotype",
            "color",
            _simple(lambda image: _duotone(image, (0, 18, 35), (190, 235, 245))),
        ),
        Transform(
            "red_duotone",
            "color",
            _simple(lambda image: _duotone(image, (20, 0, 10), (255, 175, 120))),
        ),
        Transform(
            "blur_1_5",
            "filter",
            _simple(lambda image: image.filter(ImageFilter.GaussianBlur(1.5))),
        ),
        Transform("noise_5", "filter", lambda image, key: _noise(image, 5, key)),
        Transform("noise_15", "filter", lambda image, key: _noise(image, 15, key)),
        Transform("squeeze_90", "filter", _simple(lambda image: image.resize(
            (max(1, round(image.width * 0.9)), image.height), Image.Resampling.LANCZOS
        ))),
        Transform("crop_2", "mild_geometry", _simple(lambda image: _crop(image, 0.02))),
        Transform("crop_5", "mild_geometry", _simple(lambda image: _crop(image, 0.05))),
        Transform(
            "rotate_1",
            "mild_geometry",
            _simple(lambda image: image.rotate(1, Image.Resampling.BICUBIC)),
        ),
        Transform(
            "rotate_2",
            "mild_geometry",
            _simple(lambda image: image.rotate(2, Image.Resampling.BICUBIC)),
        ),
        Transform("crop_10", "severe_geometry", _simple(lambda image: _crop(image, 0.10))),
        Transform(
            "rotate_5",
            "severe_geometry",
            _simple(lambda image: image.rotate(5, Image.Resampling.BICUBIC)),
        ),
        Transform("mirror", "destructive", _simple(ImageOps.mirror)),
        Transform(
            "solarize",
            "destructive",
            _simple(lambda image: ImageOps.solarize(image, threshold=128)),
        ),
    ]
