#!/usr/bin/env python3
"""
Sattie (virtual) - FastAPI service for serving satellite imagery images.

Run:
  uvicorn app.sattie_api:app --reload --host 0.0.0.0 --port 6001
"""

from __future__ import annotations

import json
import math
import mimetypes
import random
import shutil
import struct
import io
import hashlib
import urllib.request
import urllib.error
from array import array
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Path as ApiPath, Query
from fastapi.responses import FileResponse, HTMLResponse, Response

try:
    from PIL import Image as PILImage
except Exception:
    PILImage = None


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
STORE_DIR = PROJECT_DIR / "mock_store"
RANDOM_STORE_DIR = STORE_DIR / "random"
OSM_STORE_DIR = STORE_DIR / "osm"
UI_HTML_PATH = BASE_DIR / "ui" / "index.html"
CATALOG_PATH = RANDOM_STORE_DIR / "catalog.json"
MOCK_STORE_DISABLED_FLAG = PROJECT_DIR / ".mock_store_disabled"
MOCK_STORE_VERSION = 3
RANDOM_GENERATED_DIR = RANDOM_STORE_DIR / "generated"
OSM_TILE_URL_TEMPLATE = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass
class ImageItem:
    image_id: str
    sensor: str          # eo | sar
    level: str           # L0~L4
    fmt: str             # geotiff | ceos | tiled-geotiff | index-map | classified-raster
    satellite: str       # e.g., KOMPSAT-3, KOMPSAT-5
    acquired_at_utc: str
    file_name: str
    file_size_bytes: int
    path: str
    summary: str


def _write_tiff_gray_u16(path: Path, width: int, height: int, data_u16: list[int]) -> None:
    """
    Minimal uncompressed grayscale TIFF writer (uint16, little-endian).
    """
    if len(data_u16) != width * height:
        raise ValueError("TIFF data length mismatch.")

    path.parent.mkdir(parents=True, exist_ok=True)
    img = array("H", data_u16)
    img_bytes = img.tobytes()

    header = bytearray()
    header += b"II"
    header += struct.pack("<H", 42)
    ifd_offset = 8 + len(img_bytes)
    header += struct.pack("<I", ifd_offset)

    entries = [
        (256, 4, 1, width),          # ImageWidth
        (257, 4, 1, height),         # ImageLength
        (258, 3, 1, 16),             # BitsPerSample
        (259, 3, 1, 1),              # Compression none
        (262, 3, 1, 1),              # BlackIsZero
        (273, 4, 1, 8),              # Strip offset
        (277, 3, 1, 1),              # SamplesPerPixel
        (278, 4, 1, height),         # RowsPerStrip
        (279, 4, 1, len(img_bytes)), # StripByteCounts
        (284, 3, 1, 1),              # PlanarConfiguration
    ]

    ifd = bytearray()
    ifd += struct.pack("<H", len(entries))
    for tag, typ, count, value in entries:
        ifd += struct.pack("<HHII", tag, typ, count, value)
    ifd += struct.pack("<I", 0)

    with path.open("wb") as f:
        f.write(header)
        f.write(img_bytes)
        f.write(ifd)


def _write_tiff_rgb_u8(path: Path, width: int, height: int, data_rgb: list[tuple[int, int, int]]) -> None:
    """
    Minimal uncompressed RGB TIFF writer (uint8, little-endian).
    """
    if len(data_rgb) != width * height:
        raise ValueError("TIFF RGB data length mismatch.")

    path.parent.mkdir(parents=True, exist_ok=True)
    img_bytes = bytearray()
    for r, g, b in data_rgb:
        img_bytes.extend((r & 0xFF, g & 0xFF, b & 0xFF))

    header = bytearray()
    header += b"II"
    header += struct.pack("<H", 42)
    ifd_offset = 8 + len(img_bytes)
    header += struct.pack("<I", ifd_offset)

    entries = [
        (256, 4, 1, width),           # ImageWidth
        (257, 4, 1, height),          # ImageLength
        (258, 3, 3, 0),               # BitsPerSample (offset patched later)
        (259, 3, 1, 1),               # Compression none
        (262, 3, 1, 2),               # Photometric RGB
        (273, 4, 1, 8),               # Strip offset
        (277, 3, 1, 3),               # SamplesPerPixel
        (278, 4, 1, height),          # RowsPerStrip
        (279, 4, 1, len(img_bytes)),  # StripByteCounts
        (284, 3, 1, 1),               # PlanarConfiguration chunky
    ]

    ifd_size = 2 + (len(entries) * 12) + 4
    bits_offset = ifd_offset + ifd_size
    entries[2] = (258, 3, 3, bits_offset)

    ifd = bytearray()
    ifd += struct.pack("<H", len(entries))
    for tag, typ, count, value in entries:
        ifd += struct.pack("<HHII", tag, typ, count, value)
    ifd += struct.pack("<I", 0)
    extra = struct.pack("<HHH", 8, 8, 8)

    with path.open("wb") as f:
        f.write(header)
        f.write(img_bytes)
        f.write(ifd)
        f.write(extra)


def _make_dummy_image(path: Path, width: int = 512, height: int = 512, seed: int = 42, sensor: str = "eo") -> None:
    rng = random.Random(seed)
    if sensor == "eo":
        data_rgb: list[tuple[int, int, int]] = []
        for y in range(height):
            yn = y / max(1, height - 1)
            for x in range(width):
                xn = x / max(1, width - 1)

                # Procedural "continent" mask + terrain variation.
                n1 = math.sin((xn * 7.0) + (seed * 0.01)) + 0.7 * math.sin((yn * 5.2) - (seed * 0.02))
                n2 = 0.6 * math.sin(((xn + yn) * 10.5) + (seed * 0.03))
                n3 = 0.35 * math.sin((xn * 19.0) - (yn * 13.0))
                land_score = n1 + n2 + n3
                coast = -0.18 <= land_score <= 0.22
                is_land = land_score > 0.02

                lat = abs((yn - 0.5) * 2.0)
                elev = max(0.0, min(1.0, 0.5 + 0.5 * math.sin((xn * 16.0) + (yn * 8.0))))

                if is_land:
                    veg = max(0.0, 1.0 - lat * 1.1)
                    dry = max(0.0, lat - 0.35)
                    r = int(52 + 55 * dry + 38 * elev)
                    g = int(78 + 105 * veg + 22 * elev)
                    b = int(42 + 30 * (1.0 - veg))
                    if coast:
                        r, g, b = int(r * 0.95), int(g * 1.03), int(b * 0.9)
                else:
                    depth = max(0.0, min(1.0, (0.2 - land_score) * 0.8))
                    r = int(8 + 18 * (1.0 - depth))
                    g = int(55 + 70 * (1.0 - depth))
                    b = int(112 + 115 * (1.0 - depth))
                    if coast:
                        r, g, b = int(r + 10), int(g + 22), int(b + 20)

                # Cloud layer.
                cloud = (
                    0.55 * math.sin((xn * 21.0) + (seed * 0.07))
                    + 0.45 * math.sin((yn * 24.0) - (seed * 0.05))
                    + 0.35 * math.sin(((xn + yn) * 33.0) + (seed * 0.11))
                )
                cloud = max(0.0, min(1.0, cloud - 0.35))
                if rng.random() < 0.015:
                    cloud = min(1.0, cloud + 0.35)

                # Snow near poles/high elevation.
                snow = max(0.0, (lat - 0.76) * 2.6)
                if is_land:
                    snow = max(snow, max(0.0, (elev - 0.86) * 3.5))

                overlay = min(1.0, cloud * 0.78 + snow * 0.65)
                r = int(r * (1.0 - overlay) + 245 * overlay)
                g = int(g * (1.0 - overlay) + 247 * overlay)
                b = int(b * (1.0 - overlay) + 250 * overlay)

                # Sensor-like subtle grain.
                grain = rng.randint(-5, 5)
                r = max(0, min(255, r + grain))
                g = max(0, min(255, g + grain))
                b = max(0, min(255, b + grain))
                data_rgb.append((r, g, b))

        _write_tiff_rgb_u8(path, width, height, data_rgb)
        return

    data_gray = []
    for y in range(height):
        for x in range(width):
            xn = x / max(1, width - 1)
            yn = y / max(1, height - 1)
            texture = (
                0.55 * math.sin(xn * 28.0)
                + 0.35 * math.sin((xn + yn) * 17.0)
                + 0.25 * math.sin((xn * 49.0) - (yn * 31.0))
            )
            speckle = int(rng.random() * 3500)
            v = int(24000 + 16000 * texture + speckle)
            data_gray.append(max(0, min(65535, v)))
    _write_tiff_gray_u16(path, width, height, data_gray)


def _make_dummy_bin(path: Path, size_bytes: int, seed: int = 42) -> None:
    rng = random.Random(seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        chunk = bytearray(4096)
        remaining = size_bytes
        while remaining > 0:
            n = min(remaining, len(chunk))
            for i in range(n):
                chunk[i] = rng.randrange(0, 256)
            f.write(chunk[:n])
            remaining -= n


def _make_l3_tiles(sensor: str, image_slug: str, seed: int = 42) -> list[Path]:
    """
    Generate simple 2x2 tile set for L3 preview/use-case demonstration.
    """
    tiles_dir = RANDOM_STORE_DIR / sensor / "L3" / "tiles" / image_slug
    tiles_dir.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for ty in range(2):
        for tx in range(2):
            tile_path = tiles_dir / f"tile_{ty:03d}_{tx:03d}.tif"
            _make_dummy_image(
                tile_path,
                width=256,
                height=256,
                seed=(seed + ty * 101 + tx * 211),
                sensor=sensor,
            )
            out.append(tile_path)
    return out


def _u16_to_u8(v: int) -> int:
    if v <= 0:
        return 0
    if v >= 65535:
        return 255
    return v >> 8


def _write_bmp_bytes_rgb8(width: int, height: int, rgb: list[tuple[int, int, int]]) -> bytes:
    if len(rgb) != width * height:
        raise ValueError("BMP RGB length mismatch.")
    buf = io.BytesIO()
    row_bytes = width * 3
    pad = (4 - (row_bytes % 4)) % 4
    pixel_array_size = (row_bytes + pad) * height
    file_size = 14 + 40 + pixel_array_size
    buf.write(b"BM")
    buf.write(struct.pack("<I", file_size))
    buf.write(struct.pack("<HH", 0, 0))
    buf.write(struct.pack("<I", 14 + 40))
    buf.write(struct.pack("<I", 40))
    buf.write(struct.pack("<i", width))
    buf.write(struct.pack("<i", height))
    buf.write(struct.pack("<H", 1))
    buf.write(struct.pack("<H", 24))
    buf.write(struct.pack("<I", 0))
    buf.write(struct.pack("<I", pixel_array_size))
    buf.write(struct.pack("<i", 2835))
    buf.write(struct.pack("<i", 2835))
    buf.write(struct.pack("<I", 0))
    buf.write(struct.pack("<I", 0))
    for y in range(height - 1, -1, -1):
        row = y * width
        for x in range(width):
            r, g, b = rgb[row + x]
            buf.write(struct.pack("BBB", b, g, r))
        if pad:
            buf.write(b"\x00" * pad)
    return buf.getvalue()


def _read_u16_le(raw: bytes, off: int) -> int:
    return int.from_bytes(raw[off : off + 2], "little", signed=False)


def _read_u32_le(raw: bytes, off: int) -> int:
    return int.from_bytes(raw[off : off + 4], "little", signed=False)


def _tiff_to_bmp_bytes(path: Path) -> bytes:
    """
    Converts simple uncompressed TIFF (single strip, generated by this service)
    to 24-bit BMP bytes for browser preview.
    """
    raw = path.read_bytes()
    if len(raw) < 8 or raw[0:2] != b"II" or _read_u16_le(raw, 2) != 42:
        raise ValueError("Unsupported TIFF header")
    ifd_off = _read_u32_le(raw, 4)
    n = _read_u16_le(raw, ifd_off)
    tags: dict[int, tuple[int, int, int]] = {}
    base = ifd_off + 2
    for i in range(n):
        eoff = base + i * 12
        tag = _read_u16_le(raw, eoff)
        typ = _read_u16_le(raw, eoff + 2)
        cnt = _read_u32_le(raw, eoff + 4)
        val = _read_u32_le(raw, eoff + 8)
        tags[tag] = (typ, cnt, val)

    width = tags.get(256, (0, 0, 0))[2]
    height = tags.get(257, (0, 0, 0))[2]
    photometric = tags.get(262, (0, 0, 1))[2]
    strip_off = tags.get(273, (0, 0, 0))[2]
    strip_len = tags.get(279, (0, 0, 0))[2]
    spp = tags.get(277, (0, 0, 1))[2]
    bits = tags.get(258, (0, 1, 8))
    if width <= 0 or height <= 0 or strip_off <= 0 or strip_len <= 0:
        raise ValueError("Unsupported TIFF tags")

    pixel = raw[strip_off : strip_off + strip_len]
    rgb: list[tuple[int, int, int]] = []

    # RGB uint8
    if photometric == 2 and spp == 3:
        if bits[1] == 3:
            bits_off = bits[2]
            b0 = _read_u16_le(raw, bits_off)
            b1 = _read_u16_le(raw, bits_off + 2)
            b2 = _read_u16_le(raw, bits_off + 4)
            if b0 != 8 or b1 != 8 or b2 != 8:
                raise ValueError("Unsupported RGB bit depth")
        idx = 0
        px_count = width * height
        for _ in range(px_count):
            r = pixel[idx]
            g = pixel[idx + 1]
            b = pixel[idx + 2]
            rgb.append((r, g, b))
            idx += 3
        return _write_bmp_bytes_rgb8(width, height, rgb)

    # Grayscale uint16
    if photometric == 1 and spp == 1:
        if bits[2] != 16:
            raise ValueError("Unsupported grayscale bit depth")
        arr = array("H")
        arr.frombytes(pixel)
        for v in arr:
            g = _u16_to_u8(v)
            rgb.append((g, g, g))
        return _write_bmp_bytes_rgb8(width, height, rgb)

    raise ValueError("Unsupported TIFF format")


def _build_mock_store(force_rebuild: bool = False) -> list[ImageItem]:
    RANDOM_STORE_DIR.mkdir(parents=True, exist_ok=True)
    seed_rng = random.SystemRandom()
    scene_seed = {
        "eo": seed_rng.randrange(1, 2**31),
        "sar": seed_rng.randrange(1, 2**31),
    }

    # Create mock files (idempotent).
    files = {
        "eo_l0": RANDOM_STORE_DIR / "eo" / "L0" / "K3_L0_raw_001.bin",
        "eo_l1": RANDOM_STORE_DIR / "eo" / "L1" / "K3_L1_scene_001.tif",
        "eo_l2": RANDOM_STORE_DIR / "eo" / "L2" / "K3_L2_scene_001.tif",
        "eo_l3": RANDOM_STORE_DIR / "eo" / "L3" / "K3_L3_mosaic_001.tif",
        "eo_l4": RANDOM_STORE_DIR / "eo" / "L4" / "K3_L4_index_001.tif",
        "sar_l0": RANDOM_STORE_DIR / "sar" / "L0" / "K5_L0_raw_001.bin",
        "sar_l1": RANDOM_STORE_DIR / "sar" / "L1" / "K5_L1_intensity_001.tif",
        "sar_l2": RANDOM_STORE_DIR / "sar" / "L2" / "K5_L2_geocoded_001.tif",
        "sar_l3": RANDOM_STORE_DIR / "sar" / "L3" / "K5_L3_mosaic_001.tif",
        "sar_l4": RANDOM_STORE_DIR / "sar" / "L4" / "K5_L4_change_001.tif",
    }

    for key, fp in files.items():
        if fp.exists() and not force_rebuild:
            continue
        sensor = "eo" if key.startswith("eo_") else "sar"
        file_seed = scene_seed[sensor]
        if fp.suffix == ".tif":
            _make_dummy_image(fp, width=512, height=512, seed=file_seed, sensor=sensor)
        else:
            _make_dummy_bin(fp, size_bytes=1024 * 1024, seed=file_seed)

    # L3 service tiles (mosaic derivatives)
    _make_l3_tiles(
        sensor="eo",
        image_slug="eo-kompsat3-l3-mosaic001",
        seed=scene_seed["eo"],
    )
    _make_l3_tiles(
        sensor="sar",
        image_slug="sar-kompsat5-l3-mosaic001",
        seed=scene_seed["sar"],
    )

    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    catalog = [
        ImageItem(
            image_id="eo-kompsat3-l0-raw001",
            sensor="eo",
            level="L0",
            fmt="ceos",
            satellite="KOMPSAT-3",
            acquired_at_utc=ts,
            file_name=files["eo_l0"].name,
            file_size_bytes=files["eo_l0"].stat().st_size,
            path=str(files["eo_l0"]),
            summary="원시 EO 원격측정 기반 L0 샘플",
        ),
        ImageItem(
            image_id="eo-kompsat3-l1-scene001",
            sensor="eo",
            level="L1",
            fmt="geotiff",
            satellite="KOMPSAT-3",
            acquired_at_utc=ts,
            file_name=files["eo_l1"].name,
            file_size_bytes=files["eo_l1"].stat().st_size,
            path=str(files["eo_l1"]),
            summary="Radiometric/geometric 기본 보정 단계 EO L1 샘플",
        ),
        ImageItem(
            image_id="eo-kompsat3-l2-scene001",
            sensor="eo",
            level="L2",
            fmt="geotiff",
            satellite="KOMPSAT-3",
            acquired_at_utc=ts,
            file_name=files["eo_l2"].name,
            file_size_bytes=files["eo_l2"].stat().st_size,
            path=str(files["eo_l2"]),
            summary="정사보정 기반 EO L2 샘플",
        ),
        ImageItem(
            image_id="eo-kompsat3-l3-mosaic001",
            sensor="eo",
            level="L3",
            fmt="tiled-geotiff",
            satellite="KOMPSAT-3",
            acquired_at_utc=ts,
            file_name=files["eo_l3"].name,
            file_size_bytes=files["eo_l3"].stat().st_size,
            path=str(files["eo_l3"]),
            summary="모자이크/서비스용 EO L3 샘플",
        ),
        ImageItem(
            image_id="eo-kompsat3-l4-index001",
            sensor="eo",
            level="L4",
            fmt="index-map",
            satellite="KOMPSAT-3",
            acquired_at_utc=ts,
            file_name=files["eo_l4"].name,
            file_size_bytes=files["eo_l4"].stat().st_size,
            path=str(files["eo_l4"]),
            summary="분석 산출물 EO L4 샘플",
        ),
        ImageItem(
            image_id="sar-kompsat5-l0-raw001",
            sensor="sar",
            level="L0",
            fmt="ceos",
            satellite="KOMPSAT-5",
            acquired_at_utc=ts,
            file_name=files["sar_l0"].name,
            file_size_bytes=files["sar_l0"].stat().st_size,
            path=str(files["sar_l0"]),
            summary="원시 SAR IQ 기반 L0 샘플",
        ),
        ImageItem(
            image_id="sar-kompsat5-l1-intensity001",
            sensor="sar",
            level="L1",
            fmt="geotiff",
            satellite="KOMPSAT-5",
            acquired_at_utc=ts,
            file_name=files["sar_l1"].name,
            file_size_bytes=files["sar_l1"].stat().st_size,
            path=str(files["sar_l1"]),
            summary="강도 영상 SAR L1 샘플",
        ),
        ImageItem(
            image_id="sar-kompsat5-l2-geocoded001",
            sensor="sar",
            level="L2",
            fmt="geotiff",
            satellite="KOMPSAT-5",
            acquired_at_utc=ts,
            file_name=files["sar_l2"].name,
            file_size_bytes=files["sar_l2"].stat().st_size,
            path=str(files["sar_l2"]),
            summary="지오코딩 기반 SAR L2 샘플",
        ),
        ImageItem(
            image_id="sar-kompsat5-l3-mosaic001",
            sensor="sar",
            level="L3",
            fmt="tiled-geotiff",
            satellite="KOMPSAT-5",
            acquired_at_utc=ts,
            file_name=files["sar_l3"].name,
            file_size_bytes=files["sar_l3"].stat().st_size,
            path=str(files["sar_l3"]),
            summary="모자이크/서비스용 SAR L3 샘플",
        ),
        ImageItem(
            image_id="sar-kompsat5-l4-change001",
            sensor="sar",
            level="L4",
            fmt="classified-raster",
            satellite="KOMPSAT-5",
            acquired_at_utc=ts,
            file_name=files["sar_l4"].name,
            file_size_bytes=files["sar_l4"].stat().st_size,
            path=str(files["sar_l4"]),
            summary="변화탐지형 SAR L4 샘플",
        ),
    ]

    write_obj = {
        "mock_store_version": MOCK_STORE_VERSION,
        "generated_at_utc": ts,
        "count": len(catalog),
        "images": [asdict(x) for x in catalog],
    }
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_text(json.dumps(write_obj, indent=2, ensure_ascii=False))
    return catalog


def _load_catalog() -> list[ImageItem]:
    # If disabled flag exists, never auto-rebuild; rebuild only via explicit admin action.
    if MOCK_STORE_DISABLED_FLAG.exists():
        return []
    if not CATALOG_PATH.exists():
        return _build_mock_store()
    obj = read_json(CATALOG_PATH)
    raw_images = obj.get("images")
    if raw_images is None:
        # Backward compatibility with older catalog schema.
        raw_images = obj.get("products")
    if not isinstance(raw_images, list):
        return _build_mock_store(force_rebuild=True)

    images: list[ImageItem] = []
    for raw in raw_images:
        if not isinstance(raw, dict):
            return _build_mock_store(force_rebuild=True)
        item = dict(raw)
        if "image_id" not in item and "product_id" in item:
            item["image_id"] = item["product_id"]
        item.pop("product_id", None)
        try:
            images.append(ImageItem(**item))
        except TypeError:
            return _build_mock_store(force_rebuild=True)

    # Keep catalog aligned with current mock model (EO L0 included).
    if obj.get("mock_store_version") != MOCK_STORE_VERSION:
        return _build_mock_store(force_rebuild=True)
    if not any(p.sensor == "eo" and p.level == "L0" for p in images):
        return _build_mock_store(force_rebuild=True)
    if not any(p.sensor == "sar" and p.level == "L3" for p in images):
        return _build_mock_store(force_rebuild=True)
    return images


def _collect_image_folders(images: list[ImageItem]) -> list[str]:
    folders: set[str] = set()
    for it in images:
        fp = Path(it.path)
        if not fp.exists() or not fp.is_file():
            continue
        try:
            folders.add(str(fp.parent.relative_to(STORE_DIR)))
        except ValueError:
            folders.add(str(fp.parent))
    return sorted(folders)


def _collect_image_files(images: list[ImageItem]) -> list[str]:
    files: list[str] = []
    for it in images:
        fp = Path(it.path)
        if not fp.exists() or not fp.is_file():
            continue
        try:
            files.append(str(fp.relative_to(STORE_DIR)))
        except ValueError:
            files.append(str(fp))
    return sorted(files)


def _collect_store_folders() -> list[str]:
    if not STORE_DIR.exists():
        return []
    folders: set[str] = set()
    for fp in STORE_DIR.rglob("*"):
        if not fp.is_file():
            continue
        try:
            folders.add(str(fp.parent.relative_to(STORE_DIR)))
        except ValueError:
            folders.add(str(fp.parent))
    return sorted(folders)


def _collect_store_files() -> list[str]:
    if not STORE_DIR.exists():
        return []
    files: list[str] = []
    for fp in STORE_DIR.rglob("*"):
        if not fp.is_file():
            continue
        try:
            files.append(str(fp.relative_to(STORE_DIR)))
        except ValueError:
            files.append(str(fp))
    return sorted(files)


def _generated_suffix_for_format(fmt: str) -> str:
    normalized = fmt.strip().lower()
    if normalized in {"geotiff", "tiled-geotiff", "index-map", "classified-raster"}:
        return ".tif"
    if normalized == "ceos":
        return ".bin"
    raise HTTPException(
        status_code=400,
        detail=(
            "Unsupported fmt. allowed: ceos, geotiff, tiled-geotiff, "
            "index-map, classified-raster"
        ),
    )


def _validate_generate_combo(sensor: str, level: str, fmt: str) -> str:
    sensor_norm = sensor.strip().lower()
    level_norm = level.strip().upper()
    fmt_norm = fmt.strip().lower()
    allowed_map = {
        ("eo", "L0"): {"ceos"},
        ("eo", "L1"): {"geotiff"},
        ("eo", "L2"): {"geotiff"},
        ("eo", "L3"): {"tiled-geotiff"},
        ("eo", "L4"): {"index-map"},
        ("sar", "L0"): {"ceos"},
        ("sar", "L1"): {"geotiff"},
        ("sar", "L2"): {"geotiff"},
        ("sar", "L3"): {"tiled-geotiff"},
        ("sar", "L4"): {"classified-raster"},
    }
    allowed = allowed_map.get((sensor_norm, level_norm))
    if not allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported sensor/level: {sensor_norm}/{level_norm}")
    if fmt_norm not in allowed:
        allowed_list = ", ".join(sorted(allowed))
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid fmt for {sensor_norm}/{level_norm}. "
                f"allowed: {allowed_list}; requested: {fmt_norm}"
            ),
        )
    return fmt_norm


def _restore_osm_request_from_disk(request_id: str) -> list[ImageItem]:
    req_dir = OSM_STORE_DIR / request_id
    if not req_dir.exists() or not req_dir.is_dir():
        return []

    sensor = "eo"
    parts = request_id.split("-")
    if len(parts) >= 2 and parts[1] in {"eo", "sar"}:
        sensor = parts[1]

    items: list[ImageItem] = []
    level_order = {"L0": 0, "L1": 1, "L2": 2, "L3": 3, "L4": 4}
    for fp in sorted(req_dir.glob("*")):
        if not fp.is_file():
            continue
        if "_L0_" in fp.name:
            level = "L0"
            fmt = "ceos"
        elif "_L1_" in fp.name:
            level = "L1"
            fmt = "geotiff"
        elif "_L2_" in fp.name:
            level = "L2"
            fmt = "geotiff"
        elif "_L3_" in fp.name:
            level = "L3"
            fmt = "tiled-geotiff"
        elif "_L4_" in fp.name:
            level = "L4"
            fmt = "index-map" if sensor == "eo" else "classified-raster"
        else:
            continue

        st = fp.stat()
        acquired = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        items.append(
            ImageItem(
                image_id=f"{request_id}-{level.lower()}",
                sensor=sensor,
                level=level,
                fmt=fmt,
                satellite="OSM-simulated",
                acquired_at_utc=acquired,
                file_name=fp.name,
                file_size_bytes=st.st_size,
                path=str(fp),
                summary="OSM 기반 모사(서버 재시작 후 디스크 복원 항목)",
            )
        )

    items.sort(key=lambda x: level_order.get(x.level, 99))
    if items:
        OSM_SIM_CATALOG[request_id] = items
    return items


def _ensure_osm_catalog_loaded() -> None:
    base = OSM_STORE_DIR
    if not base.exists() or not base.is_dir():
        return
    for d in sorted(base.iterdir(), key=lambda p: p.name, reverse=True):
        if not d.is_dir():
            continue
        rid = d.name
        if rid not in OSM_SIM_CATALOG:
            _restore_osm_request_from_disk(rid)


def _tile_xy_from_lonlat(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    lat_clamped = max(min(lat, 85.05112878), -85.05112878)
    n = 2**zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat_clamped)
    y = int((1.0 - math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad))) / math.pi) / 2.0 * n)
    x = max(0, min(n - 1, x))
    y = max(0, min(n - 1, y))
    return x, y


def _fetch_osm_tile(lon: float, lat: float, zoom: int) -> dict:
    x, y = _tile_xy_from_lonlat(lon=lon, lat=lat, zoom=zoom)
    url = OSM_TILE_URL_TEMPLATE.format(z=zoom, x=x, y=y)
    req = urllib.request.Request(
        url=url,
        headers={
            "User-Agent": "sattie-virtual/0.1 (+https://github.com/jaysys/sattie-virtual)",
            "Accept": "image/png,*/*;q=0.8",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = resp.read()
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"OSM tile fetch failed: {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=f"OSM tile fetch failed: {exc.reason}") from exc

    if not data:
        raise HTTPException(status_code=502, detail="OSM tile fetch returned empty body")
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=502, detail="OSM tile payload is unexpectedly large")
    return {
        "url": url,
        "x": x,
        "y": y,
        "bytes": data,
    }


def _fetch_osm_tile_by_xyz(zoom: int, x: int, y: int) -> bytes:
    n = 2**zoom
    xx = x % n
    yy = max(0, min(n - 1, y))
    url = OSM_TILE_URL_TEMPLATE.format(z=zoom, x=xx, y=yy)
    req = urllib.request.Request(
        url=url,
        headers={
            "User-Agent": "sattie-virtual/0.1 (+https://github.com/jaysys/sattie-virtual)",
            "Accept": "image/png,*/*;q=0.8",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = resp.read()
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"OSM tile fetch failed: {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=f"OSM tile fetch failed: {exc.reason}") from exc
    if not data:
        raise HTTPException(status_code=502, detail="OSM tile fetch returned empty body")
    return data


def _png_bytes_to_rgb8(tile_bytes: bytes, out_w: int = 512, out_h: int = 512) -> list[tuple[int, int, int]]:
    if PILImage is None:
        raise HTTPException(
            status_code=500,
            detail="Pillow is required for OSM TIFF generation. install with: pip install pillow",
        )
    try:
        with PILImage.open(io.BytesIO(tile_bytes)) as img:
            img = img.convert("RGB").resize((out_w, out_h))
            px = list(img.getdata())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OSM tile decode failed: {exc}") from exc
    return [(int(r), int(g), int(b)) for (r, g, b) in px]


def _rgb_adjust_linear(
    rgb: list[tuple[int, int, int]],
    gain: float = 1.0,
    bias: int = 0,
    gamma: float = 1.0,
) -> list[tuple[int, int, int]]:
    out: list[tuple[int, int, int]] = []
    inv = 1.0 / max(gamma, 1e-6)
    for r, g, b in rgb:
        rr = max(0.0, min(255.0, ((r / 255.0) ** inv) * 255.0 * gain + bias))
        gg = max(0.0, min(255.0, ((g / 255.0) ** inv) * 255.0 * gain + bias))
        bb = max(0.0, min(255.0, ((b / 255.0) ** inv) * 255.0 * gain + bias))
        out.append((int(rr), int(gg), int(bb)))
    return out


def _rgb_to_gray_u16(rgb: list[tuple[int, int, int]]) -> list[int]:
    out: list[int] = []
    for r, g, b in rgb:
        y8 = int(0.299 * r + 0.587 * g + 0.114 * b)
        out.append(max(0, min(65535, y8 * 257)))
    return out


def _rgb_to_classified_gray_u16(rgb: list[tuple[int, int, int]], sensor: str) -> list[int]:
    if sensor != "sar":
        return _rgb_to_gray_u16(_rgb_to_classified(rgb, sensor=sensor))
    out: list[int] = []
    for r, g, b in rgb:
        y = int(0.299 * r + 0.587 * g + 0.114 * b)
        if y < 60:
            out.append(9000)
        elif y < 120:
            out.append(22000)
        elif y < 180:
            out.append(39000)
        else:
            out.append(56000)
    return out


def _rgb_to_classified(rgb: list[tuple[int, int, int]], sensor: str) -> list[tuple[int, int, int]]:
    out: list[tuple[int, int, int]] = []
    if sensor == "sar":
        for r, g, b in rgb:
            y = int(0.299 * r + 0.587 * g + 0.114 * b)
            if y < 60:
                out.append((18, 32, 68))
            elif y < 120:
                out.append((60, 88, 132))
            elif y < 180:
                out.append((124, 146, 172))
            else:
                out.append((214, 224, 236))
        return out

    for r, g, b in rgb:
        if g > r + 18 and g > b:
            out.append((34, 139, 34))    # vegetation
        elif b > r + 16 and b > g:
            out.append((49, 116, 219))   # water
        elif r > 145 and g > 145 and b > 145:
            out.append((230, 230, 224))  # bright urban/cloud
        else:
            out.append((173, 153, 117))  # bare land
    return out


def _stitch_2x2_rgb(tiles: list[list[tuple[int, int, int]]], tile_w: int, tile_h: int) -> list[tuple[int, int, int]]:
    out_w = tile_w * 2
    out_h = tile_h * 2
    out = [(0, 0, 0)] * (out_w * out_h)
    for idx, tile in enumerate(tiles):
        ox = (idx % 2) * tile_w
        oy = (idx // 2) * tile_h
        for y in range(tile_h):
            src_off = y * tile_w
            dst_off = (oy + y) * out_w + ox
            out[dst_off:dst_off + tile_w] = tile[src_off:src_off + tile_w]
    return out


def _write_osm_l0_bin(path: Path, tile_bytes: bytes, meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    head = json.dumps(meta, ensure_ascii=False).encode("utf-8")
    path.write_bytes(b"SATTIE_OSM_L0\n" + len(head).to_bytes(4, "little") + head + tile_bytes)


def _make_l3_tiles_under(base_dir: Path, sensor: str, seed: int) -> list[Path]:
    base_dir.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for ty in range(2):
        for tx in range(2):
            fp = base_dir / f"tile_{ty:03d}_{tx:03d}.tif"
            _make_dummy_image(
                fp,
                width=256,
                height=256,
                seed=(seed + ty * 101 + tx * 211),
                sensor=sensor,
            )
            out.append(fp)
    return out


def _make_l3_tiles_from_osm_under(base_dir: Path, tile_rgbs: list[list[tuple[int, int, int]]], tile_w: int, tile_h: int) -> list[Path]:
    base_dir.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for idx, rgb in enumerate(tile_rgbs):
        ty = idx // 2
        tx = idx % 2
        fp = base_dir / f"tile_{ty:03d}_{tx:03d}.tif"
        _write_tiff_rgb_u8(fp, tile_w, tile_h, rgb)
        out.append(fp)
    return out


__all__ = [name for name in globals().keys() if not name.startswith("__")]
