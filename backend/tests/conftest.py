import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import database  # noqa: E402
from app.services import search  # noqa: E402
from scripts.seed_catalog import write_products  # noqa: E402
from seed_data.curated_gifts import CURATED  # noqa: E402

# Wednesday 10:00, before the 14:00 dispatch cutoff.
NOW = datetime(2026, 9, 16, 10, 0)


def curated_rows() -> list[dict]:
    rows = []
    for i, (slug, name, category, price, ship_days, stock, _q, desc, interests, occasions, recipients) in enumerate(CURATED):
        rows.append({
            "id": f"cu-{slug}", "name": name, "description": desc, "category": category, "price": price,
            "image_path": None, "image_credit": None, "image_credit_url": None, "tags": [],
            "interests": interests, "occasions": occasions, "recipients": recipients, "stock": stock,
            "ship_days": ship_days, "rating": 4.5, "review_count": 10 + i, "reviews": [], "source": "curated",
        })
    return rows


@pytest.fixture(autouse=True)
def catalog_db(tmp_path):
    database.set_db_path(tmp_path / "test.db")
    write_products(curated_rows())
    search.reset_index()
    yield
    search.reset_index()
