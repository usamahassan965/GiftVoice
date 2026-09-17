"""Scripted, audio-free conversation: the tool calls an agent would make for a gift purchase."""

import asyncio
from datetime import timedelta

from app.agent.tools import TOOLS, ToolContext, run_tool
from app.services.products import all_products
from tests.conftest import NOW


def make_ctx():
    events = []

    async def emit(name, payload):
        events.append((name, payload))

    ctx = ToolContext(session_id="s1", customer_id="c1", emit=emit, now_fn=lambda: NOW, use_vectors=False)
    return ctx, events


def call(ctx, tool, **args):
    return asyncio.run(run_tool(ctx, tool, args))


def checkout(ctx, **args):
    """Preview the order, then confirm it in the shopper's next turn."""
    preview = call(ctx, "create_checkout", **args)
    assert preview["order_placed"] is False, preview
    ctx.user_turns += 1
    return call(ctx, "create_checkout", shopper_confirmed=True, **args)


def test_schemas_are_well_formed():
    for tool in TOOLS.values():
        assert tool.description
        assert set(tool.required) <= set(tool.properties)


def test_full_gift_journey_for_mom():
    ctx, events = make_ctx()
    catalog_ids = {p["id"] for p in all_products()}

    # "Gift for my mom who loves gardening, under $50, her birthday is Friday"
    res = call(ctx, "search_products", query="gardening", recipient="mom", occasion="birthday",
               max_price=50, deadline="friday")
    assert res["results"], res
    assert {r["id"] for r in res["results"]} <= catalog_ids          # grounded: only catalog products
    assert all(r["price"] <= 50 for r in res["results"])
    assert events[-1][0] == "show_products"
    assert [c["position"] for c in events[-1][1]["products"]] == list(range(1, len(res["results"]) + 1))

    # "Add the first one"
    first = ctx.last_shown[0]
    res = call(ctx, "add_to_cart", product_id=first)
    assert res["ok"] and events[-1][0] == "cart_updated"

    call(ctx, "set_gift_options", wrap="premium", message="Happy birthday Ammi, love you!", hide_price=True)
    delivery = call(ctx, "check_delivery", deadline="2026-09-18")
    assert delivery["deadline"] == "2026-09-18"

    call(ctx, "save_recipient_profile", name="Mom", relationship="mother", interests=["gardening"],
         occasions=[{"type": "birthday", "date": "09-18"}])
    name, payload = events[-1]
    assert name == "profiles_updated" and payload["upcoming"]   # the side panel shows the birthday right away
    assert "error" in call(ctx, "create_checkout", recipient_profile_name="Mom")     # no address yet
    # The address given in conversation can be passed straight to checkout.
    order = checkout(ctx, recipient_profile_name="Mom", occasion="birthday", recipient_name="Mom",
                     ship_address="12 Rose Lane", ship_city="Lahore")
    assert order["order_id"].startswith("GV-")
    assert events[-1][0] == "checkout_ready"

    # Next session: memory recalls Mom, the upcoming birthday and excludes the past gift.
    ctx2, _ = make_ctx()
    ctx2.now_fn = lambda: NOW + timedelta(days=300)
    profiles = call(ctx2, "get_recipient_profiles")
    assert profiles["profiles"][0]["past_gifts"]
    again = call(ctx2, "search_products", query="gardening", recipient_profile_name="Mom", limit=6)
    assert first not in {r["id"] for r in again["results"]}
    assert again["excluded_past_gifts"] == 1


def test_tool_errors_are_returned_not_raised():
    ctx, _ = make_ctx()
    assert "error" in call(ctx, "add_to_cart", product_id="nope")
    assert "error" in call(ctx, "track_order")
    assert "error" in call(ctx, "search_products", deadline="someday soon")
    assert "error" in call(ctx, "image_search")
    assert "error" in call(ctx, "missing_tool")


def test_bundle_and_language_tools():
    ctx, events = make_ctx()
    switched = []

    async def on_lang(lang):
        switched.append(lang)

    ctx.on_language_change = on_lang
    res = call(ctx, "build_bundle", budget=120, theme="relaxing spa", recipient="wife")
    assert res["total"] <= 120 and len(res["items"]) >= 2
    assert call(ctx, "set_language", language="ur")["language"] == "ur"
    assert switched == ["ur"] and ctx.language == "ur"


def test_checkout_remembers_recipient_without_saved_profile():
    ctx, events = make_ctx()
    call(ctx, "search_products", query="gardening", max_price=50)
    first = ctx.last_shown[0]
    call(ctx, "add_to_cart", product_id=first)
    call(ctx, "set_gift_options", ship_address="4 Oak St", ship_city="Austin")
    checkout(ctx, recipient_profile_name="my mom", occasion="birthday")
    assert "profiles_updated" in {name for name, _ in events}

    ctx2, _ = make_ctx()
    profiles = call(ctx2, "get_recipient_profiles")["profiles"]
    assert [(p["name"], p["relationship"], len(p["past_gifts"])) for p in profiles] == [("Mom", "mom", 1)]
    again = call(ctx2, "search_products", query="gardening", recipient_profile_name="Mom", limit=6)
    assert first not in {r["id"] for r in again["results"]}


def test_checkout_waits_for_the_shopper_to_confirm_the_summary():
    ctx, events = make_ctx()
    call(ctx, "search_products", query="gardening", max_price=50)
    call(ctx, "add_to_cart", product_id=ctx.last_shown[0])
    args = dict(shopper_confirmed=True, ship_address="4 Oak St", ship_city="Austin")

    # Confirming in the same turn the summary was first produced doesn't place the order, even if repeated.
    first = call(ctx, "create_checkout", **args)
    assert first["order_placed"] is False and first["order_summary"]["ship_to"]["ship_city"] == "Austin"
    assert call(ctx, "create_checkout", **args)["order_placed"] is False

    # A change after the read-back needs a fresh confirmation.
    ctx.user_turns += 1
    call(ctx, "set_gift_options", wrap="premium")
    assert call(ctx, "create_checkout", **args)["order_placed"] is False
    assert "checkout_ready" not in {name for name, _ in events}

    ctx.user_turns += 1
    assert call(ctx, "create_checkout", **args)["order_id"].startswith("GV-")
