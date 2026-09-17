"""Session cart and gift options."""

from app.db.database import connect, row_to_dict
from app.services import delivery
from app.services.products import get_product, get_products
from app.services.taxonomy import WRAP_OPTIONS

MAX_QTY = 10


class CartError(ValueError):
    pass


def add_item(session_id: str, product_id: str, qty: int = 1) -> dict:
    product = get_product(product_id)
    if not product:
        raise CartError(f"Unknown product id '{product_id}'.")
    if product["stock"] <= 0:
        raise CartError(f"'{product['name']}' is out of stock.")
    with connect() as conn:
        row = conn.execute(
            "SELECT qty FROM cart_items WHERE session_id = ? AND product_id = ?", (session_id, product_id)
        ).fetchone()
        new_qty = (row["qty"] if row else 0) + qty
        if new_qty > min(MAX_QTY, product["stock"]):
            raise CartError(f"Only {min(MAX_QTY, product['stock'])} of '{product['name']}' can be ordered.")
        conn.execute(
            "INSERT INTO cart_items (session_id, product_id, qty) VALUES (?, ?, ?) "
            "ON CONFLICT(session_id, product_id) DO UPDATE SET qty = excluded.qty",
            (session_id, product_id, new_qty),
        )
    return view_cart(session_id)


def remove_item(session_id: str, product_id: str, qty: int | None = None) -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT qty FROM cart_items WHERE session_id = ? AND product_id = ?", (session_id, product_id)
        ).fetchone()
        if not row:
            raise CartError("That item is not in the cart.")
        if qty is None or qty >= row["qty"]:
            conn.execute("DELETE FROM cart_items WHERE session_id = ? AND product_id = ?", (session_id, product_id))
        else:
            conn.execute(
                "UPDATE cart_items SET qty = ? WHERE session_id = ? AND product_id = ?",
                (row["qty"] - qty, session_id, product_id),
            )
    return view_cart(session_id)


def clear_cart(session_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM cart_items WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM gift_options WHERE session_id = ?", (session_id,))


def get_gift_options(session_id: str) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT * FROM gift_options WHERE session_id = ?", (session_id,)).fetchone()
    opts = row_to_dict(row) or {"session_id": session_id, "wrap": None, "message": None, "hide_price": 0,
                                "recipient_name": None, "ship_address": None, "ship_city": None, "express": 0}
    opts["hide_price"] = bool(opts["hide_price"])
    opts["express"] = bool(opts["express"])
    return opts


def set_gift_options(session_id: str, **changes) -> dict:
    if "wrap" in changes and changes["wrap"] not in (None, "none", *WRAP_OPTIONS):
        raise CartError(f"Wrap must be one of: {', '.join(WRAP_OPTIONS)} or none.")
    if changes.get("wrap") == "none":
        changes["wrap"] = None
    if changes.get("message") and len(changes["message"]) > 250:
        raise CartError("Gift messages are limited to 250 characters.")
    opts = get_gift_options(session_id)
    opts.update({k: v for k, v in changes.items() if k in opts and k != "session_id"})
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO gift_options "
            "(session_id, wrap, message, hide_price, recipient_name, ship_address, ship_city, express) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, opts["wrap"], opts["message"], int(bool(opts["hide_price"])), opts["recipient_name"],
             opts["ship_address"], opts["ship_city"], int(bool(opts["express"]))),
        )
    return get_gift_options(session_id)


def view_cart(session_id: str) -> dict:
    with connect() as conn:
        rows = conn.execute("SELECT product_id, qty FROM cart_items WHERE session_id = ?", (session_id,)).fetchall()
    qty_by_id = {r["product_id"]: r["qty"] for r in rows}
    products = get_products(list(qty_by_id))
    items = [
        {
            "product_id": p["id"],
            "name": p["name"],
            "price": p["price"],
            "qty": qty_by_id[p["id"]],
            "line_total": round(p["price"] * qty_by_id[p["id"]], 2),
            "image_url": f"/images/{p['image_path']}" if p.get("image_path") else None,
            "ship_days": p["ship_days"],
        }
        for p in products
    ]
    gift = get_gift_options(session_id)
    subtotal = round(sum(i["line_total"] for i in items), 2)
    gift_fee = WRAP_OPTIONS[gift["wrap"]]["fee"] if gift["wrap"] else 0.0
    has_physical = any(i["ship_days"] > 0 for i in items)
    ship_fee = delivery.shipping_fee(subtotal, gift["express"], has_physical) if items else 0.0
    return {
        "items": items,
        "item_count": sum(i["qty"] for i in items),
        "subtotal": subtotal,
        "gift_fee": gift_fee,
        "shipping_fee": ship_fee,
        "total": round(subtotal + gift_fee + ship_fee, 2),
        "gift_options": gift,
    }
