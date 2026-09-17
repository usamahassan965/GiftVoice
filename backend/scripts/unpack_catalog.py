"""Restore the seeded catalog from data/catalog.zip.

Seeding needs Pexels and Gemini keys and a long download, so the finished catalog (SQLite rows,
Chroma vectors and the product photos) travels with the repository as one zip. This unpacks it,
and does nothing if the catalog is already there.

    python backend/scripts/unpack_catalog.py [--force]
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "data" / "catalog.zip"
DB = ROOT / "data" / "giftvoice.db"


def unpack(force: bool = False) -> int:
    if DB.exists() and not force:
        print(f"Catalog already unpacked ({DB.relative_to(ROOT)}); use --force to overwrite.")
        return 0
    if not ARCHIVE.exists():
        print(f"Missing {ARCHIVE.relative_to(ROOT)} - run backend/scripts/seed_catalog.py instead.")
        return 1
    with zipfile.ZipFile(ARCHIVE) as archive:
        archive.extractall(ROOT / "data")
        print(f"Unpacked {len(archive.namelist())} files into {(ROOT / 'data')}")
    return 0


if __name__ == "__main__":
    sys.exit(unpack(force="--force" in sys.argv[1:]))
