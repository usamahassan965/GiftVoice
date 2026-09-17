"""LLM tools: JSON schemas + async handlers, independent of the voice framework.

The Pipecat pipeline wraps these as function calls; tests call them directly.
Handlers return small JSON-able dicts (the LLM reads them) and push richer
payloads to the UI through `ctx.emit` (product cards, cart, checkout link).
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Awaitable, Callable

from app.services import cart as cart_svc
from app.services import delivery, memory, orders
from app.services.bundles import build_bundle
from app.services.products import card, get_product, get_products, llm_view
from app.services.search import image_search, search_products
from app.services.taxonomy import OCCASIONS, RECIPIENTS, WRAP_OPTIONS, normalize_recipient

Emit = Callable[[str, dict], Awaitable[None]]


async def _no_emit(_event: str, _payload: dict) -> None:
    return None


@dataclass
class ToolContext:
    session_id: str
    customer_id: str
    emit: Emit = _no_emit
    now_fn: Callable[[], datetime] = datetime.now
    use_vectors: bool = True
    last_shown: list[str] = field(default_factory=list)
    uploaded_image: Any = None          # PIL image from the UI upload endpoint
    language: str = "en"
    mood: str = "calm"
    on_language_change: Callable[[str], Awaitable[None]] | None = None
    # How many messages the shopper has sent (spoken or typed); the pipeline counts them in the LLM context.
    user_turns_fn: Callable[[], int] | None = None
    user_turns: int = 0
    checkout_preview: tuple[str, int] | None = None   # (order summary, shopper turn it was given in)

    @property
    def now(self) -> datetime:
        return self.now_fn()

    @property
    def user_turn(self) -> int:
        return self.user_turns_fn() if self.user_turns_fn else self.user_turns


@dataclass
class Tool:
    name: str
    description: str
    properties: dict
    required: list[str]
    handler: Callable[[ToolContext, dict], Awaitable[dict]]


# ---- helpers ---------------------------------------------------------------------------------

def _deadline(ctx: ToolContext, value: str | None) -> date | None:
    if not value:
        return None
    parsed = delivery.parse_deadline(value, ctx.now.date())
    if parsed is None:
        raise ValueError(f"Could not understand the date '{value}'. Pass YYYY-MM-DD.")
    return parsed


def _exclusions(ctx: ToolContext, profile_name: str | None) -> tuple[set[str], dict | None]:
    if not profile_name:
        return set(), None
    profile = memory.find_profile(ctx.customer_id, profile_name)
    return (memory.past_gift_ids(profile["id"]) if profile else set()), profile


async def _show(ctx: ToolContext, hits: list[dict], title: str) -> list[dict]:
    """Send cards to the UI with 1-based positions and return compact LLM results."""
    ctx.last_shown = [h["product"]["id"] for h in hits]
    cards = []
    results = []
    for pos, h in enumerate(hits, start=1):
        c = card(h["product"]) | {"position": pos, "why": h.get("why", []), "arrival": h.get("arrival")}
        cards.append(c)
        results.append(llm_view(h["product"]) | {"position": pos, "why": h.get("why", []),
                                                "standard_arrival": h.get("arrival"),
                                                "express_arrival": h.get("express_arrival")})
    await ctx.emit("show_products", {"title": title, "products": cards})
    return results


async def _emit_cart(ctx: ToolContext, view: dict) -> None:
    await ctx.emit("cart_updated", view)


def _cart_summary(view: dict) -> dict:
    return {
        "items": [f"{i['qty']} x {i['name']} ({i['product_id']}) @ {i['price']}" for i in view["items"]],
        "subtotal": view["subtotal"], "gift_fee": view["gift_fee"], "shipping_fee": view["shipping_fee"],
        "total": view["total"], "gift_options": {k: v for k, v in view["gift_options"].items() if k != "session_id"},
    }


# ---- handlers -----------------------------------------------------------------------------------

async def h_search_products(ctx: ToolContext, a: dict) -> dict:
    exclude, profile = _exclusions(ctx, a.get("recipient_profile_name"))
    interests = a.get("interests") or (profile["interests"] if profile else None)
    hits = await asyncio.to_thread(
        search_products, a.get("query", ""), min_price=a.get("min_price"), max_price=a.get("max_price"),
        category=a.get("category"), recipient=a.get("recipient") or (profile or {}).get("relationship"),
        occasion=a.get("occasion"), interests=interests, deadline=_deadline(ctx, a.get("deadline")),
        exclude_ids=exclude, limit=min(int(a.get("limit", 4)), 6), use_vectors=ctx.use_vectors, now=ctx.now,
    )
    if not hits:
        return {"results": [], "note": "Nothing matched. Relax a filter (budget, deadline) or ask a different question."}
    results = await _show(ctx, hits, a.get("query") or "Gift ideas")
    out = {"results": results, "shown_on_screen": True}
    if exclude:
        out["excluded_past_gifts"] = len(exclude)
    return out


async def h_get_product(ctx: ToolContext, a: dict) -> dict:
    p = get_product(a["product_id"])
    if not p:
        return {"error": f"No product with id {a['product_id']}."}
    return llm_view(p) | {"reviews": p["reviews"][:3], "stock_left": p["stock"]}


async def h_compare_products(ctx: ToolContext, a: dict) -> dict:
    products = get_products(a["product_ids"][:4])
    await _show(ctx, [{"product": p} for p in products], "Comparison")
    return {"products": [llm_view(p) | {"top_review": (p["reviews"] or [{}])[0].get("comment")} for p in products]}


async def h_show_products(ctx: ToolContext, a: dict) -> dict:
    products = get_products(a["product_ids"][:6])
    await _show(ctx, [{"product": p} for p in products], a.get("title") or "Selected gifts")
    return {"shown": [p["id"] for p in products]}


async def h_image_search(ctx: ToolContext, a: dict) -> dict:
    if ctx.uploaded_image is None:
        return {"error": "No photo uploaded yet. Ask the shopper to use the camera/upload button."}
    hits = await asyncio.to_thread(image_search, ctx.uploaded_image, 4, a.get("max_price"))
    results = await _show(ctx, hits, "Similar to your photo")
    return {"results": results}


async def h_build_bundle(ctx: ToolContext, a: dict) -> dict:
    exclude, profile = _exclusions(ctx, a.get("recipient_profile_name"))
    result = await asyncio.to_thread(
        build_bundle, float(a["budget"]), theme=a.get("theme", ""),
        recipient=a.get("recipient") or (profile or {}).get("relationship"), occasion=a.get("occasion"),
        interests=a.get("interests") or (profile["interests"] if profile else None),
        deadline=_deadline(ctx, a.get("deadline")), exclude_ids=exclude, use_vectors=ctx.use_vectors, now=ctx.now,
    )
    if not result["found"]:
        return result
    items = await _show(ctx, result["items"], f"Gift bundle under {result['budget']:.0f}")
    return {"total": result["total"], "remaining": result["remaining"], "items": items}


async def h_add_to_cart(ctx: ToolContext, a: dict) -> dict:
    view = cart_svc.add_item(ctx.session_id, a["product_id"], int(a.get("qty", 1)))
    await _emit_cart(ctx, view)
    return {"ok": True, "cart": _cart_summary(view)}


async def h_remove_from_cart(ctx: ToolContext, a: dict) -> dict:
    view = cart_svc.remove_item(ctx.session_id, a["product_id"], a.get("qty"))
    await _emit_cart(ctx, view)
    return {"ok": True, "cart": _cart_summary(view)}


async def h_view_cart(ctx: ToolContext, a: dict) -> dict:
    view = cart_svc.view_cart(ctx.session_id)
    await _emit_cart(ctx, view)
    return _cart_summary(view)


async def h_set_gift_options(ctx: ToolContext, a: dict) -> dict:
    changes = {k: a[k] for k in ("wrap", "message", "hide_price", "recipient_name", "ship_address", "ship_city",
                                 "express") if k in a}
    cart_svc.set_gift_options(ctx.session_id, **changes)
    view = cart_svc.view_cart(ctx.session_id)
    await _emit_cart(ctx, view)
    return {"ok": True, "cart": _cart_summary(view)}


async def h_check_delivery(ctx: ToolContext, a: dict) -> dict:
    ids = a.get("product_ids") or [i["product_id"] for i in cart_svc.view_cart(ctx.session_id)["items"]]
    if not ids:
        return {"error": "No products given and the cart is empty."}
    return delivery.check_products(get_products(ids), _deadline(ctx, a.get("deadline")), ctx.now)


async def h_create_checkout(ctx: ToolContext, a: dict) -> dict:
    # Shipping details spoken earlier often never reached set_gift_options; taking them here saves a
    # failed checkout and two extra LLM round trips.
    shipping = {k: a[k] for k in ("recipient_name", "ship_address", "ship_city") if a.get(k)}
    if shipping:
        cart_svc.set_gift_options(ctx.session_id, **shipping)
        await _emit_cart(ctx, cart_svc.view_cart(ctx.session_id))

    # The model can't be trusted to wait for a yes, so an order is only placed once this exact summary
    # was returned in an earlier shopper turn and the shopper has spoken since.
    summary = orders.quote(ctx.session_id, ctx.now)
    key = json.dumps(summary, sort_keys=True)
    preview = ctx.checkout_preview
    if not a.get("shopper_confirmed") or not preview or preview[0] != key or ctx.user_turn <= preview[1]:
        if not preview or preview[0] != key:
            ctx.checkout_preview = (key, ctx.user_turn)
        return {"order_placed": False, "order_summary": summary,
                "next_step": "Nothing is ordered yet. Read back the items, gift options, shipping address, total "
                             "and arrival date, and ask the shopper to confirm. Call create_checkout with "
                             "shopper_confirmed=true only after they say yes."}
    ctx.checkout_preview = None
    who = (a.get("recipient_profile_name") or "").strip().removeprefix("my ").removeprefix("My ")
    _, profile = _exclusions(ctx, who)
    if who and not profile:
        # Record who the gift is for even without a saved profile, so the next session knows what
        # they already received. Interests and dates are only kept via save_recipient_profile.
        profile = memory.save_profile(ctx.customer_id, who[:1].upper() + who[1:],
                                      relationship=who if normalize_recipient(who) else None)
    order = orders.checkout(ctx.session_id, ctx.customer_id, recipient_id=(profile or {}).get("id"),
                            occasion=a.get("occasion"), now=ctx.now)
    await _emit_cart(ctx, cart_svc.view_cart(ctx.session_id))
    if profile:
        await _emit_profiles(ctx)
    await ctx.emit("checkout_ready", {"order_id": order["id"], "total": order["total"], "eta": order["eta"],
                                      "payment_url": order["payment_url"]})
    return {"order_id": order["id"], "total": order["total"], "eta": order["eta"],
            "next_step": "Payment page opened on screen (Stripe test mode)."}


async def h_track_order(ctx: ToolContext, a: dict) -> dict:
    return orders.track_order(a.get("order_id"), ctx.customer_id, ctx.now.date())


async def h_start_return(ctx: ToolContext, a: dict) -> dict:
    return orders.start_return(a["order_id"], ctx.customer_id, a["reason"], a.get("resolution", "refund"),
                               ctx.now.date())


async def _emit_profiles(ctx: ToolContext) -> None:
    await ctx.emit("profiles_updated", {"profiles": memory.list_profiles(ctx.customer_id),
                                        "upcoming": memory.upcoming_occasions(ctx.customer_id, ctx.now.date())})


async def h_save_recipient_profile(ctx: ToolContext, a: dict) -> dict:
    profile = memory.save_profile(ctx.customer_id, a["name"], a.get("relationship"), a.get("interests"),
                                  a.get("notes"), a.get("occasions"))
    await _emit_profiles(ctx)
    return {"saved": profile["name"], "interests": profile["interests"], "occasions": profile["occasions"]}


async def h_get_recipient_profiles(ctx: ToolContext, a: dict) -> dict:
    profiles = memory.list_profiles(ctx.customer_id)
    return {
        "profiles": [{"name": p["name"], "relationship": p["relationship"], "interests": p["interests"],
                      "notes": p["notes"], "past_gifts": [g["name"] for g in p["past_gifts"]]} for p in profiles],
        "upcoming_occasions": memory.upcoming_occasions(ctx.customer_id, ctx.now.date()),
        # flash-lite sometimes "recommended" an invented product straight from this result.
        "next_step": "This has no products. Before suggesting any gift, call search_products (with "
                     "recipient_profile_name for a saved person) and describe only what it returns.",
    }


async def h_escalate_to_human(ctx: ToolContext, a: dict) -> dict:
    ticket = orders.create_ticket(ctx.session_id, a["reason"], a.get("summary"))
    await ctx.emit("ticket_created", ticket)
    return ticket


async def h_set_language(ctx: ToolContext, a: dict) -> dict:
    lang = a["language"]
    if lang not in ("en", "ur"):
        return {"error": "Supported languages: en, ur."}
    ctx.language = lang
    if ctx.on_language_change:
        await ctx.on_language_change(lang)
    await ctx.emit("language_changed", {"language": lang})
    return {"ok": True, "language": lang}


async def h_note_mood(ctx: ToolContext, a: dict) -> dict:
    ctx.mood = a["mood"]
    await ctx.emit("mood", {"mood": ctx.mood})
    return {"ok": True}


# ---- registry ------------------------------------------------------------------------------------

S = {"type": "string"}
N = {"type": "number"}
PROFILE = {"type": "string", "description": "Saved recipient name (e.g. 'Mom'); excludes past gifts and uses their interests."}
DEADLINE = {"type": "string", "description": "Date the gift must arrive by, YYYY-MM-DD (resolve 'next Friday' using today's date)."}

TOOLS: dict[str, Tool] = {t.name: t for t in [
    Tool("search_products",
         "Search the gift catalog. Results are shown on the shopper's screen as numbered cards. "
         "Only recommend products returned by this or other catalog tools.",
         {"query": {**S, "description": "What to look for, e.g. 'gardening gift' or 'cozy'"},
          "recipient": {"type": "string", "enum": RECIPIENTS},
          "occasion": {"type": "string", "enum": OCCASIONS},
          "interests": {"type": "array", "items": S},
          "min_price": N, "max_price": N,
          "deadline": DEADLINE, "recipient_profile_name": PROFILE,
          "limit": {"type": "integer", "description": "2-6, default 4"}},
         [], h_search_products),
    Tool("get_product", "Full details and reviews for one product.", {"product_id": S}, ["product_id"], h_get_product),
    Tool("compare_products", "Compare 2-4 products side by side (also shows them).",
         {"product_ids": {"type": "array", "items": S}}, ["product_ids"], h_compare_products),
    Tool("show_products", "Put specific products back on screen.",
         {"product_ids": {"type": "array", "items": S}, "title": S}, ["product_ids"], h_show_products),
    Tool("image_search", "Find products visually similar to the photo the shopper uploaded.",
         {"max_price": N}, [], h_image_search),
    Tool("build_bundle", "Assemble a varied 2-4 item gift set within a total budget.",
         {"budget": N, "theme": S, "recipient": {"type": "string", "enum": RECIPIENTS},
          "occasion": {"type": "string", "enum": OCCASIONS}, "interests": {"type": "array", "items": S},
          "deadline": DEADLINE, "recipient_profile_name": PROFILE},
         ["budget"], h_build_bundle),
    Tool("add_to_cart", "Add a product to the cart.", {"product_id": S, "qty": {"type": "integer"}},
         ["product_id"], h_add_to_cart),
    Tool("remove_from_cart", "Remove a product (or some quantity) from the cart.",
         {"product_id": S, "qty": {"type": "integer"}}, ["product_id"], h_remove_from_cart),
    Tool("view_cart", "Show the cart with totals and gift options.", {}, [], h_view_cart),
    Tool("set_gift_options",
         "Set gift wrap, message card, hidden-price receipt, recipient shipping details or express shipping.",
         {"wrap": {"type": "string", "enum": [*WRAP_OPTIONS, "none"],
                   "description": "; ".join(f"{k}: {v['label']} (+{v['fee']})" for k, v in WRAP_OPTIONS.items())},
          "message": {**S, "description": "Gift card message, max 250 chars"},
          "hide_price": {"type": "boolean", "description": "true only if the shopper wants a gift receipt "
                         "(prices hidden); false if they decline one"},
          "recipient_name": S, "ship_address": S, "ship_city": S,
          "express": {"type": "boolean"}},
         [], h_set_gift_options),
    Tool("check_delivery", "Arrival dates (standard and express) for products or the cart, against a deadline.",
         {"product_ids": {"type": "array", "items": S}, "deadline": DEADLINE}, [], h_check_delivery),
    Tool("create_checkout",
         "Checkout. Without shopper_confirmed it returns the order summary to read back (nothing is ordered). "
         "With shopper_confirmed=true, after the shopper said yes to that summary, it creates the order and "
         "opens the payment page.",
         {"shopper_confirmed": {"type": "boolean"},
          "recipient_profile_name": {**S, "description": "Who the gift is for, e.g. 'Mom' or 'Sarah'. Always pass it "
                                                         "for gifts: it is recorded so future sessions avoid repeats."},
          "occasion": {"type": "string", "enum": OCCASIONS},
          "recipient_name": S,
          "ship_address": {**S, "description": "Street address, if the shopper gave it and it isn't saved yet"},
          "ship_city": S},
         ["shopper_confirmed"], h_create_checkout),
    Tool("track_order", "Status and ETA of an order (latest order if no id).", {"order_id": S}, [], h_track_order),
    Tool("start_return", "Open a return or exchange for a delivered order.",
         {"order_id": S, "reason": S, "resolution": {"type": "string", "enum": ["refund", "exchange"]}},
         ["order_id", "reason"], h_start_return),
    Tool("save_recipient_profile",
         "Remember someone the shopper buys for (merges with existing). Call ONLY after asking \"shall I remember "
         "them for next time?\" and hearing yes in a later reply. Placing an order already records who the gift "
         "was for, so don't save a profile just because of an order.",
         {"name": S, "relationship": S, "interests": {"type": "array", "items": S}, "notes": S,
          "occasions": {"type": "array", "items": {"type": "object", "properties": {
              "type": {"type": "string", "enum": OCCASIONS},
              "date": {**S, "description": "MM-DD, only as the shopper said it; never guess holiday dates"}}}}},
         ["name"], h_save_recipient_profile),
    Tool("get_recipient_profiles", "Saved recipients, their past gifts and upcoming occasions.", {}, [],
         h_get_recipient_profiles),
    Tool("escalate_to_human", "Hand off to a human teammate (complaints, payment problems, anything unsupported).",
         {"reason": S, "summary": S}, ["reason"], h_escalate_to_human),
    Tool("set_language", "Switch spoken language when the shopper prefers Urdu or English.",
         {"language": {"type": "string", "enum": ["en", "ur"]}}, ["language"], h_set_language),
    Tool("note_mood", "Record a clear change in the shopper's mood so the UI and your tone adapt.",
         {"mood": {"type": "string", "enum": ["calm", "excited", "hesitant", "frustrated", "rushed"]}},
         ["mood"], h_note_mood),
]}


async def run_tool(ctx: ToolContext, name: str, args: dict) -> dict:
    """Execute a tool, turning domain errors into messages the LLM can recover from."""
    tool = TOOLS.get(name)
    if not tool:
        return {"error": f"Unknown tool {name}."}
    try:
        return await tool.handler(ctx, args or {})
    except (cart_svc.CartError, orders.OrderError, ValueError, KeyError) as e:
        return {"error": str(e)}
