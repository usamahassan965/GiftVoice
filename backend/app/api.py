"""REST endpoints for the web UI: catalog, cart, profiles, orders, payments and photo upload."""

import io
from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from app.agent import sessions
from app.services import cart, memory, orders, payments
from app.services.products import all_products, card, categories, get_product

router = APIRouter(prefix="/api")

MAX_UPLOAD_BYTES = 8 * 1024 * 1024


@router.get("/health")
def health() -> dict:
    return {"ok": True, "products": len(all_products())}


@router.get("/products")
def list_products(category: str | None = None, limit: int = 60) -> dict:
    products = [p for p in all_products() if not category or p["category"] == category]
    return {"categories": categories(), "products": [card(p) for p in products[:limit]]}


@router.get("/products/{product_id}")
def product_detail(product_id: str) -> dict:
    p = get_product(product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    return card(p) | {"reviews": p["reviews"], "interests": p["interests"], "occasions": p["occasions"]}


@router.get("/cart/{session_id}")
def get_cart(session_id: str) -> dict:
    return cart.view_cart(session_id)


@router.get("/profiles/{customer_id}")
def get_profiles(customer_id: str) -> dict:
    return {
        "profiles": memory.list_profiles(customer_id),
        "upcoming": memory.upcoming_occasions(customer_id, date.today()),
    }


@router.get("/orders/{order_id}")
def order_detail(order_id: str) -> dict:
    order = orders.get_order(order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    return order


@router.post("/orders/{order_id}/mock-pay")
def mock_pay(order_id: str) -> dict:
    """Test-mode payment used when Stripe isn't configured."""
    if payments.stripe_enabled():
        raise HTTPException(400, "Stripe is configured; pay through Stripe Checkout.")
    if not orders.get_order(order_id):
        raise HTTPException(404, "Order not found")
    return orders.mark_paid(order_id)


@router.post("/orders/{order_id}/verify-stripe")
def verify_stripe(order_id: str, session_id: str) -> dict:
    if not orders.get_order(order_id):
        raise HTTPException(404, "Order not found")
    if payments.verify_stripe_session(session_id, order_id):
        return orders.mark_paid(order_id)
    return orders.get_order(order_id)


@router.post("/image-upload")
async def image_upload(session_id: str = Form(...), file: UploadFile = File(...)) -> dict:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Photo is larger than 8 MB.")
    try:
        image = Image.open(io.BytesIO(data)).convert("RGB")
    except UnidentifiedImageError:
        raise HTTPException(400, "That file isn't an image.")
    image.thumbnail((512, 512))
    sessions.set_uploaded_image(session_id, image)
    return {"ok": True}
