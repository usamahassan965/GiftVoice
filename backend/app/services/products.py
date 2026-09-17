"""Product catalog access."""

from app.db.database import connect, row_to_dict


def get_product(product_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    return row_to_dict(row)


def get_products(product_ids: list[str]) -> list[dict]:
    if not product_ids:
        return []
    marks = ",".join("?" * len(product_ids))
    with connect() as conn:
        rows = conn.execute(f"SELECT * FROM products WHERE id IN ({marks})", product_ids).fetchall()
    by_id = {r["id"]: row_to_dict(r) for r in rows}
    return [by_id[i] for i in product_ids if i in by_id]


def all_products() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM products").fetchall()
    return [row_to_dict(r) for r in rows]


def categories() -> list[str]:
    with connect() as conn:
        rows = conn.execute("SELECT DISTINCT category FROM products ORDER BY category").fetchall()
    return [r["category"] for r in rows]


def card(p: dict) -> dict:
    """Compact product view sent to the UI and to the LLM (keeps token use low)."""
    return {
        "id": p["id"],
        "name": p["name"],
        "price": p["price"],
        "category": p["category"],
        "rating": p["rating"],
        "review_count": p["review_count"],
        "in_stock": p["stock"] > 0,
        "ship_days": p["ship_days"],
        "image_url": f"/images/{p['image_path']}" if p.get("image_path") else None,
        "image_credit": p.get("image_credit"),
        "image_credit_url": p.get("image_credit_url"),
        "description": p["description"],
    }


def llm_view(p: dict) -> dict:
    """What the model needs to recommend and justify a product, nothing more."""
    return {
        "id": p["id"],
        "name": p["name"],
        "price": p["price"],
        "category": p["category"],
        "rating": p["rating"],
        "reviews": p["review_count"],
        "in_stock": p["stock"] > 0,
        "ship_days": p["ship_days"],
        "description": p["description"],
        "good_for": p["interests"][:4],
    }
