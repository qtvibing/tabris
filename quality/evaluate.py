from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import time
from pathlib import Path

import numpy as np
from PIL import Image, __version__ as pillow_version

from fetch import CALTECH_MD5
from methods import methods
from report import write_report
from transforms import transformations

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parent
POPCOUNT = np.array([value.bit_count() for value in range(256)], dtype=np.uint8)


def image_identity(image: Image.Image) -> bytes:
    digest = hashlib.sha256()
    digest.update(image.width.to_bytes(4, "little"))
    digest.update(image.height.to_bytes(4, "little"))
    digest.update(image.tobytes())
    return digest.digest()


def hamming(left: bytes, right: bytes) -> int:
    return sum((a ^ b).bit_count() for a, b in zip(left, right, strict=True))


def negative_histogram(hashes: np.ndarray, block: int = 256) -> tuple[np.ndarray, np.ndarray]:
    histogram = np.zeros(hashes.shape[1] * 8 + 1, dtype=np.int64)
    exact: list[tuple[int, int]] = []
    count = len(hashes)
    for start in range(0, count, block):
        stop = min(count, start + block)
        xor = np.bitwise_xor(hashes[start:stop, None, :], hashes[None, :, :])
        distances = POPCOUNT[xor].sum(axis=2, dtype=np.uint16)
        rows, columns = np.indices(distances.shape)
        mask = columns > rows + start
        histogram += np.bincount(distances[mask], minlength=len(histogram))
        for row, column in np.argwhere(mask & (distances == 0)):
            exact.append((start + int(row), int(column)))
    return histogram, np.asarray(exact, dtype=np.int32).reshape(-1, 2)


def corpus_paths(data: Path, quick: bool) -> list[Path]:
    caltech = sorted((data / "caltech/101_ObjectCategories").glob("*/*.jpg"))
    picsum = sorted((data / "picsum").glob("*.jpg"), key=lambda path: int(path.stem))
    if not caltech or not picsum:
        raise RuntimeError("the corpora are missing. run `uv run python fetch.py` first")
    if quick:
        return caltech[:512] + picsum[:128]
    return caltech + picsum


def variant_paths(records: list[tuple[Path, str, str]], quick: bool) -> list[tuple[Path, str, str]]:
    picsum = [record for record in records if record[2] == "picsum"]
    caltech = [record for record in records if record[2] != "picsum"]
    holdout = sorted(
        caltech,
        key=lambda record: hashlib.sha256(record[1].encode()).digest(),
    )
    if quick:
        return picsum[:64] + holdout[:64]
    return picsum + holdout[:1024]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="evaluate tabris against real-image transformations"
    )
    parser.add_argument("--data", type=Path, default=ROOT / "data")
    parser.add_argument("--results", type=Path, default=ROOT / "results")
    parser.add_argument("--quick", action="store_true", help="run a small workflow check")
    args = parser.parse_args()

    started = time.monotonic()
    method_map = methods(REPOSITORY)
    names = list(method_map)
    widths = np.asarray([method_map[name][0] for name in names], dtype=np.uint16)
    paths = corpus_paths(args.data, args.quick)

    hashes: dict[str, list[bytes]] = {name: [] for name in names}
    records: list[tuple[Path, str, str]] = []
    duplicates: list[tuple[str, str]] = []
    seen: dict[bytes, str] = {}
    for index, path in enumerate(paths, 1):
        with Image.open(path) as source:
            image = source.convert("RGB")
        label = str(path.relative_to(args.data))
        identity = image_identity(image)
        if identity in seen:
            duplicates.append((label, seen[identity]))
            continue
        seen[identity] = label
        group = "picsum" if path.parent.name == "picsum" else path.parent.name
        records.append((path, label, group))
        for name, (_, function) in method_map.items():
            hashes[name].append(function(image))
        if index % 1000 == 0 or index == len(paths):
            print(f"originals  {index:,}/{len(paths):,}")

    hash_arrays = {
        name: np.frombuffer(b"".join(values), dtype=np.uint8).reshape(
            len(values), widths[i] // 8
        )
        for i, (name, values) in enumerate(hashes.items())
    }
    record_labels = np.asarray([record[1] for record in records])
    record_groups = np.asarray([record[2] for record in records])

    transforms = transformations()
    variants = variant_paths(records, args.quick)
    distances: dict[str, list[list[int]]] = {name: [] for name in names}
    for index, (path, label, _) in enumerate(variants, 1):
        with Image.open(path) as source:
            image = source.convert("RGB")
        originals = {name: function(image) for name, (_, function) in method_map.items()}
        rows = {name: [] for name in names}
        for transform in transforms:
            changed = transform.apply(image, label)
            for name, (_, function) in method_map.items():
                rows[name].append(hamming(originals[name], function(changed)))
        for name in names:
            distances[name].append(rows[name])
        if index % 100 == 0 or index == len(variants):
            print(f"variants   {index:,}/{len(variants):,}")

    output: dict[str, np.ndarray] = {
        "methods": np.asarray(names),
        "widths": widths,
        "labels": record_labels,
        "groups": record_groups,
        "duplicate_labels": np.asarray(duplicates).reshape(-1, 2),
        "transform_names": np.asarray([transform.name for transform in transforms]),
        "transform_groups": np.asarray([transform.group for transform in transforms]),
        "transform_source_labels": np.asarray([record[1] for record in variants]),
        "transform_source_suites": np.asarray([
            "picsum" if record[2] == "picsum" else "caltech_sample"
            for record in variants
        ]),
    }
    picsum = record_groups == "picsum"
    for name in names:
        print(f"pairs      {name}")
        histogram, exact = negative_histogram(hash_arrays[name])
        natural_histogram, _ = negative_histogram(hash_arrays[name][picsum])
        output[f"{name}_hashes"] = hash_arrays[name]
        output[f"{name}_negative_hist"] = histogram
        output[f"{name}_picsum_negative_hist"] = natural_histogram
        output[f"{name}_exact_pairs"] = exact
        output[f"{name}_variant_distances"] = np.asarray(distances[name], dtype=np.uint8)

    mode = "quick" if args.quick else "full"
    target = args.results / mode
    target.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(target / "measurements.npz", **output)
    corpus_digest = hashlib.sha256(b"".join(sorted(seen))).hexdigest()
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=REPOSITORY,
        text=True,
    )
    metadata = {
        "mode": mode,
        "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True
        ).strip(),
        "dirty": bool(status.strip()),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pillow": pillow_version,
        "zig": subprocess.check_output(["zig", "version"], text=True).strip(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "uv_lock_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "caltech_archive_md5": CALTECH_MD5,
        "picsum_manifest_sha256": hashlib.sha256(
            (ROOT / "picsum_sha256.txt").read_bytes()
        ).hexdigest(),
        "corpus_sha256": corpus_digest,
        "source_files": len(paths),
        "unique_images": len(records),
        "pixel_duplicates": len(duplicates),
        "transform_source_images": len(variants),
        "transformations": len(transforms),
        "transformed_variants": len(variants) * len(transforms),
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    (target / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    write_report(target / "measurements.npz", target / "report.md", target / "summary.json")
    print(f"report     {target / 'report.md'}")


if __name__ == "__main__":
    main()
