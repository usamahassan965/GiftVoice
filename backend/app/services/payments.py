"""Stripe Checkout in TEST mode, with a mock fallback when no key is configured."""

import logging

from app import config

log = logging.getLogger(__name__)


def stripe_enabled() -> bool:
    return config.STRIPE_SECRET_KEY.startswith("sk_test_")


def create_payment_link(order: dict) -> str:
    """Return a URL where the shopper completes payment for `order`."""
    if not stripe_enabled():
        return f"{config.FRONTEND_URL}/checkout/mock/{order['id']}"

    import stripe

    stripe.api_key = config.STRIPE_SECRET_KEY
    line_items = [
        {
            "price_data": {
                "currency": config.CURRENCY.lower(),
                "product_data": {"name": item["name"]},
                "unit_amount": round(item["price"] * 100),
            },
            "quantity": item["qty"],
        }
        for item in order["items"]
    ]
    extras = [("Gift wrapping", order["gift_fee"]), ("Shipping", order["shipping_fee"])]
    for label, amount in extras:
        if amount:
            line_items.append({
                "price_data": {"currency": config.CURRENCY.lower(), "product_data": {"name": label},
                               "unit_amount": round(amount * 100)},
                "quantity": 1,
            })
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=line_items,
        client_reference_id=order["id"],
        success_url=f"{config.FRONTEND_URL}/order/{order['id']}?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{config.FRONTEND_URL}/?cancelled={order['id']}",
    )
    return session.url


def verify_stripe_session(session_id: str, order_id: str) -> bool:
    if not stripe_enabled():
        return False
    import stripe

    stripe.api_key = config.STRIPE_SECRET_KEY
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception:  # network / invalid id
        log.exception("Stripe session lookup failed")
        return False
    return session.client_reference_id == order_id and session.payment_status == "paid"
