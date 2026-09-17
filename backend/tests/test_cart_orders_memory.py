from datetime import date, timedelta

import pytest

from app.services import cart, memory, orders
from tests.conftest import NOW

S, C = "sess-1", "cust-1"


def test_cart_math_with_gift_options():
    cart.add_item(S, "cu-soy-candle-trio", 2)        # 68
    view = cart.add_item(S, "cu-gratitude-journal")   # 22 -> 90, free standard shipping
    assert view["subtotal"] == 90 and view["shipping_fee"] == 0
    view = cart.set_gift_options(S, wrap="premium", message="Happy birthday!")
    view = cart.view_cart(S)
    assert view["gift_fee"] == 9 and view["total"] == 99
    cart.set_gift_options(S, express=True)
    assert cart.view_cart(S)["total"] == 90 + 9 + 12
    view = cart.remove_item(S, "cu-soy-candle-trio", 1)
    assert view["item_count"] == 2


def test_cart_rejects_bad_input():
    with pytest.raises(cart.CartError):
        cart.add_item(S, "does-not-exist")
    with pytest.raises(cart.CartError):
        cart.add_item(S, "cu-limited-advent-calendar")
    with pytest.raises(cart.CartError):
        cart.set_gift_options(S, wrap="glitter")
    with pytest.raises(cart.CartError):
        cart.add_item(S, "cu-bonsai-starter", 9)  # stock 8


def test_checkout_requires_address_then_creates_order():
    cart.add_item(S, "cu-gardening-tool-set")
    with pytest.raises(orders.OrderError):
        orders.checkout(S, C, now=NOW)
    cart.set_gift_options(S, recipient_name="Mom", ship_address="12 Rose Lane", ship_city="Lahore")
    profile = memory.save_profile(C, "Mom", "mother", interests=["gardening", "coffee"])
    order = orders.checkout(S, C, recipient_id=profile["id"], occasion="birthday", now=NOW)
    assert order["status"] == "pending_payment"
    assert order["total"] == 64 + 5
    assert order["payment_url"].endswith(order["id"])
    assert cart.view_cart(S)["items"] == []
    # Gift history is remembered for this recipient.
    assert memory.past_gift_ids(profile["id"]) == {"cu-gardening-tool-set"}


def test_tracking_progress_and_returns():
    cart.add_item(S, "cu-bbq-tool-set")
    cart.set_gift_options(S, ship_address="1 Main St", ship_city="Karachi")
    order = orders.checkout(S, C, now=NOW)
    with pytest.raises(orders.OrderError):
        orders.start_return(order["id"], C, "changed mind", today=NOW.date())
    orders.mark_paid(order["id"])
    assert orders.track_order(order["id"], C, today=NOW.date())["status"] == "paid"
    assert orders.track_order(None, C, today=NOW.date() + timedelta(days=1))["status"] == "shipped"
    eta = date.fromisoformat(order["eta"])
    assert orders.track_order(order["id"], C, today=eta)["status"] == "delivered"
    ret = orders.start_return(order["id"], C, "wrong size", "exchange", today=eta)
    assert ret["resolution"] == "exchange"
    with pytest.raises(orders.OrderError):
        orders.track_order(order["id"], "someone-else")


def test_profile_merge_and_upcoming_occasions():
    memory.save_profile(C, "Sara", "sister", interests=["yoga"], occasions=[{"type": "birthday", "date": "10-02"}])
    merged = memory.save_profile(C, "sara", interests=["Tea"], notes="allergic to lavender")
    assert merged["interests"] == ["yoga", "tea"]
    assert merged["relationship"] == "sibling"
    assert memory.find_profile(C, "sister")["name"] == "Sara"
    upcoming = memory.upcoming_occasions(C, today=date(2026, 9, 16))
    assert upcoming == [{"recipient": "Sara", "occasion": "birthday", "date": "2026-10-02", "days_left": 16}]


def test_profile_recorded_at_checkout_merges_with_the_named_person():
    placeholder = memory.save_profile(C, "Mom", "mom")
    named = memory.save_profile(C, "Ammi", "mother", interests=["gardening"])
    assert named["id"] == placeholder["id"] and named["name"] == "Ammi"
    # Asking for "mom" again finds Ammi rather than creating a third profile.
    assert memory.save_profile(C, "Mom", "mother")["name"] == "Ammi"
    # Two named people with the same relationship stay separate.
    memory.save_profile(C, "Sara", "sister")
    memory.save_profile(C, "Hina", "sister")
    assert [p["name"] for p in memory.list_profiles(C)].count("Ammi") == 1
    assert len(memory.list_profiles(C)) == 3

