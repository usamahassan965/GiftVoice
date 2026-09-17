"""Checkout, order tracking and returns."""

import secrets
from datetime import date, datetime, timedelta

from app.db.database import connect, dumps, row_to_dict
from app.services import cart as cart_svc
from app.services import delivery, payments
from app.services.products import get_products

RETURN_WINDOW_DAYS = 30


class OrderError(ValueError):
    pass


def _new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.randbelow(900000) + 100000}"


def _checkable_cart(session_id: str, now: datetime) -> tuple[dict, date]:
    """The cart and its arrival date, or OrderError if it can't be ordered yet."""
    cart = cart_svc.view_cart(session_id)
    if not cart["items"]:
        raise OrderError("The cart is empty.")
    gift = cart["gift_options"]
    products = {p["id"]: p for p in get_products([i["product_id"] for i in cart["items"]])}
    for item in cart["items"]:
        if products[item["product_id"]]["stock"] < item["qty"]:
            raise OrderError(f"'{item['name']}' no longer has enough stock.")
    physical = [i for i in cart["items"] if i["ship_days"] > 0]
    if physical and not (gift["ship_address"] and gift["ship_city"]):
        raise OrderError("A shipping address and city are needed before checkout. If the shopper already gave them, "
                         "call create_checkout again with ship_address and ship_city; otherwise ask for what is "
                         "missing.")
    return cart, max(delivery.estimate_arrival(i["ship_days"], now, gift["express"]) for i in cart["items"])


def quote(session_id: str, now: datetime | None = None) -> dict:
    """What would be ordered right now: the summary the shopper confirms before checkout."""
    cart, eta = _checkable_cart(session_id, now or datetime.now())
    gift = cart["gift_options"]
    return {
        "items": [{k: i[k] for k in ("name", "price", "qty")} for i in cart["items"]],
        "wrap": gift["wrap"], "message": gift["message"], "hide_price": bool(gift["hide_price"]),
        "ship_to": {k: gift[k] for k in ("recipient_name", "ship_address", "ship_city")},
        "express": bool(gift["express"]), "total": cart["total"], "arrives_by": eta.isoformat(),
    }


def checkout(session_id: str, customer_id: str, recipient_id: str | None = None,
             occasion: str | None = None, now: datetime | None = None) -> dict:
    """Turn the cart into an order awaiting payment. Caller must have spoken confirmation."""
    now = now or datetime.now()
    cart, eta = _checkable_cart(session_id, now)
    gift = cart["gift_options"]
    order_id = _new_id("GV")
    items = [{k: i[k] for k in ("product_id", "name", "price", "qty")} for i in cart["items"]]
    order = {
        "id": order_id, "session_id": session_id, "customer_id": customer_id, "items": items,
        "subtotal": cart["subtotal"], "gift_fee": cart["gift_fee"], "shipping_fee": cart["shipping_fee"],
        "total": cart["total"], "gift": gift, "recipient_id": recipient_id, "status": "pending_payment",
        "created_at": now.isoformat(timespec="seconds"), "eta": eta.isoformat(),
    }
    order["payment_url"] = payments.create_payment_link(order)

    with connect() as conn:
        conn.execute(
            "INSERT INTO orders (id, session_id, customer_id, items, subtotal, gift_fee, shipping_fee, total, gift, "
            "recipient_id, status, created_at, eta, payment_url) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (order_id, session_id, customer_id, dumps(items), order["subtotal"], order["gift_fee"],
             order["shipping_fee"], order["total"], dumps(gift), recipient_id, order["status"],
             order["created_at"], order["eta"], order["payment_url"]),
        )
        for item in items:
            conn.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (item["qty"], item["product_id"]))
            if recipient_id:
                conn.execute(
                    "INSERT INTO gift_history (customer_id, recipient_id, product_id, order_id, occasion, created_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (customer_id, recipient_id, item["product_id"], order_id, occasion, order["created_at"]),
                )
    cart_svc.clear_cart(session_id)
    return order


def mark_paid(order_id: str) -> dict:
    with connect() as conn:
        conn.execute("UPDATE orders SET status = 'paid' WHERE id = ? AND status = 'pending_payment'", (order_id,))
    return get_order(order_id)


def get_order(order_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id.strip().upper(),)).fetchone()
    return row_to_dict(row)


def _live_status(order: dict, today: date) -> str:
    """Simulate fulfilment progress from dates so tracking feels real in a demo."""
    if order["status"] in ("pending_payment", "return_requested"):
        return order["status"]
    created = datetime.fromisoformat(order["created_at"])
    eta = date.fromisoformat(order["eta"])
    if today >= eta:
        return "delivered"
    if today >= delivery.dispatch_date(created) and created.date() < today:
        return "shipped"
    return "paid"


def track_order(order_id: str | None, customer_id: str, today: date | None = None) -> dict:
    today = today or date.today()
    if order_id:
        order = get_order(order_id)
        if not order or order["customer_id"] != customer_id:
            raise OrderError(f"No order {order_id} found for this account.")
    else:
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE customer_id = ? ORDER BY created_at DESC LIMIT 1", (customer_id,)
            ).fetchone()
        order = row_to_dict(row)
        if not order:
            raise OrderError("This account has no orders yet.")
    return {
        "order_id": order["id"],
        "status": _live_status(order, today),
        "eta": order["eta"],
        "items": [f"{i['qty']} x {i['name']}" for i in order["items"]],
        "total": order["total"],
        "ship_to": order["gift"].get("recipient_name") or order["gift"].get("ship_city"),
        "payment_url": order["payment_url"] if order["status"] == "pending_payment" else None,
    }


def start_return(order_id: str, customer_id: str, reason: str, resolution: str = "refund",
                 today: date | None = None) -> dict:
    today = today or date.today()
    if resolution not in ("refund", "exchange"):
        raise OrderError("Resolution must be 'refund' or 'exchange'.")
    tracked = track_order(order_id, customer_id, today)
    order = get_order(order_id)
    if tracked["status"] == "pending_payment":
        raise OrderError("This order was never paid, so there is nothing to return.")
    if tracked["status"] == "return_requested":
        raise OrderError("A return is already open for this order.")
    products = get_products([i["product_id"] for i in order["items"]])
    if all(p["ship_days"] == 0 for p in products):
        raise OrderError("Digital gifts and experiences can't be returned.")
    if today > date.fromisoformat(order["eta"]) + timedelta(days=RETURN_WINDOW_DAYS):
        raise OrderError(f"The {RETURN_WINDOW_DAYS}-day return window has closed for this order.")
    return_id = _new_id("RT")
    with connect() as conn:
        conn.execute(
            "INSERT INTO returns (id, order_id, reason, resolution, status, created_at) VALUES (?,?,?,?,?,?)",
            (return_id, order["id"], reason, resolution, "label_sent", today.isoformat()),
        )
        conn.execute("UPDATE orders SET status = 'return_requested' WHERE id = ?", (order["id"],))
    return {
        "return_id": return_id,
        "order_id": order["id"],
        "resolution": resolution,
        "next_step": "A prepaid return label has been emailed. Drop the parcel off within 14 days.",
    }


def create_ticket(session_id: str, reason: str, summary: str | None = None) -> dict:
    ticket_id = _new_id("TK")
    with connect() as conn:
        conn.execute(
            "INSERT INTO tickets (id, session_id, reason, summary, created_at) VALUES (?,?,?,?,?)",
            (ticket_id, session_id, reason, summary, datetime.now().isoformat(timespec="seconds")),
        )
    return {"ticket_id": ticket_id, "message": "A human teammate will reach out within one business day."}
