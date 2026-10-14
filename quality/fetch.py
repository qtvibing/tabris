from __future__ import annotations

import argparse
import hashlib
import shutil
import tarfile
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

CALTECH_URL = "https://data.caltech.edu/records/mzrjq-6wc02/files/caltech-101.zip?download=1"
CALTECH_MD5 = "3138e1922a9193bfa496528edbbc45d0"
CALTECH_ARCHIVE = "caltech-101/101_ObjectCategories.tar.gz"
CALTECH_IMAGES = 9_144
PICSUM_URL = "https://picsum.photos/id/{id}/640/480"
ROOT = Path(__file__).resolve().parent


def file_hash(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path, max_bytes: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "tabris-quality/0.1"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                length = response.headers.get("Content-Length")
                if length is not None and int(length) > max_bytes:
                    raise RuntimeError(f"the download exceeds the size limit: {url}")
                total = 0
                with temporary.open("wb") as output:
                    while chunk := response.read(1024 * 1024):
                        total += len(chunk)
                        if total > max_bytes:
                            raise RuntimeError(f"the download exceeds the size limit: {url}")
                        output.write(chunk)
            temporary.replace(destination)
            return
        except Exception:
            temporary.unlink(missing_ok=True)
            if attempt == 3:
                raise
            time.sleep(2**attempt)


def valid_caltech(target: Path) -> bool:
    marker = target / ".complete"
    images = target / "101_ObjectCategories"
    return (
        marker.is_file()
        and marker.read_text().strip() == CALTECH_MD5
        and sum(1 for _ in images.glob("*/*.jpg")) == CALTECH_IMAGES
    )


def fetch_caltech(data: Path) -> None:
    target = data / "caltech"
    if valid_caltech(target):
        print("Caltech-101 is already present")
        return
    if target.exists():
        raise RuntimeError(f"the Caltech corpus at {target} is incomplete. remove it and retry")

    archive = data / "caltech-101.zip"
    if not archive.is_file() or file_hash(archive, "md5") != CALTECH_MD5:
        archive.unlink(missing_ok=True)
        print("downloading Caltech-101 (137 MB)")
        download(CALTECH_URL, archive, 150 * 1024 * 1024)
    actual = file_hash(archive, "md5")
    if actual != CALTECH_MD5:
        archive.unlink()
        raise RuntimeError(f"Caltech-101 checksum mismatch: {actual}")

    nested = data / "caltech-101.tar.gz"
    with (
        zipfile.ZipFile(archive) as bundle,
        bundle.open(CALTECH_ARCHIVE) as source,
        nested.open("wb") as output,
    ):
        shutil.copyfileobj(source, output)

    temporary = data / "caltech.extracting"
    shutil.rmtree(temporary, ignore_errors=True)
    temporary.mkdir(parents=True)
    try:
        with tarfile.open(nested, "r:gz") as bundle:
            root = temporary.resolve()
            for member in bundle.getmembers():
                destination = (temporary / member.name).resolve()
                if root not in destination.parents and destination != root:
                    raise RuntimeError(f"unsafe archive member: {member.name}")
            bundle.extractall(temporary, filter="data")
        count = sum(1 for _ in (temporary / "101_ObjectCategories").glob("*/*.jpg"))
        if count != CALTECH_IMAGES:
            raise RuntimeError(f"expected {CALTECH_IMAGES:,} Caltech images, found {count:,}")
        (temporary / ".complete").write_text(CALTECH_MD5 + "\n")
        temporary.replace(target)
    finally:
        nested.unlink(missing_ok=True)
        shutil.rmtree(temporary, ignore_errors=True)
    print(f"extracted {CALTECH_IMAGES:,} Caltech images")


def picsum_manifest() -> dict[str, str]:
    result: dict[str, str] = {}
    for line in (ROOT / "picsum_sha256.txt").read_text().splitlines():
        checksum, filename = line.split("  ", 1)
        result[filename] = checksum
    return result


def fetch_picsum(data: Path, workers: int) -> None:
    manifest = picsum_manifest()
    expected_ids = (ROOT / "picsum_ids.txt").read_text().splitlines()
    expected_files = {f"{id_}.jpg" for id_ in expected_ids}
    if set(manifest) != expected_files:
        raise RuntimeError("the Picsum id and checksum manifests disagree")

    target = data / "picsum"
    target.mkdir(parents=True, exist_ok=True)
    unexpected = {path.name for path in target.glob("*.jpg")} - expected_files
    if unexpected:
        raise RuntimeError(f"unexpected Picsum files: {', '.join(sorted(unexpected)[:5])}")

    def fetch_one(id_: str) -> bool:
        destination = target / f"{id_}.jpg"
        expected = manifest[destination.name]
        if destination.is_file() and file_hash(destination, "sha256") == expected:
            return False
        destination.unlink(missing_ok=True)
        download(PICSUM_URL.format(id=id_), destination, 5 * 1024 * 1024)
        actual = file_hash(destination, "sha256")
        if actual != expected:
            destination.unlink()
            raise RuntimeError(f"the Picsum image {id_} changed: {actual}")
        return True

    print(f"validating {len(expected_ids):,} pinned Picsum images")
    downloaded = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch_one, id_) for id_ in expected_ids]
        for done, future in enumerate(as_completed(futures), 1):
            downloaded += future.result()
            if done % 100 == 0 or done == len(futures):
                print(f"  {done:,}/{len(futures):,}")
    print(f"downloaded {downloaded:,}. validated {len(expected_ids):,}")


def main() -> None:
    parser = argparse.ArgumentParser(description="fetch the tabris quality corpora")
    parser.add_argument("--data", type=Path, default=ROOT / "data")
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()

    args.data.mkdir(parents=True, exist_ok=True)
    fetch_caltech(args.data)
    fetch_picsum(args.data, args.workers)


if __name__ == "__main__":
    main()
