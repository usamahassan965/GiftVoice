"""Budget bundle builder: best 2-4 item gift set that fits a total budget."""

from datetime import date, datetime
from itertools import combinations

from app.services.search import search_products

POOL_SIZE = 16


def build_bundle(
    budget: float,
    *,
    theme: str = "",
    recipient: str | None = None,
    occasion: str | None = None,
    interests: list[str] | None = None,
    deadline: date | None = None,
    exclude_ids: set[str] | None = None,
    min_items: int = 2,
    max_items: int = 4,
    use_vectors: bool = True,
    now: datetime | None = None,
) -> dict:
    if budget <= 0:
        raise ValueError("Budget must be positive.")
    pool = search_products(
        theme, max_price=budget, recipient=recipient, occasion=occasion, interests=interests,
        deadline=deadline, exclude_ids=exclude_ids, limit=POOL_SIZE, use_vectors=use_vectors, now=now,
    )
    # Relevance decays with search rank; the first hits matter most.
    weighted = [(1 / (1 + 0.15 * rank), hit) for rank, hit in enumerate(pool)]

    best, best_score = None, -1.0
    for size in range(min_items, max_items + 1):
        for combo in combinations(weighted, size):
            products = [hit["product"] for _, hit in combo]
            total = sum(p["price"] for p in products)
            if total > budget:
                continue
            if len({p["category"] for p in products}) < size:
                continue  # a bundle should feel varied, not three candles
            relevance = sum(w for w, _ in combo) / size
            utilisation = total / budget
            score = relevance + 0.6 * utilisation + 0.05 * size
            if score > best_score:
                best, best_score = combo, score

    if not best:
        return {"found": False, "budget": budget,
                "message": f"No set of {min_items}+ different items fits within {budget:.2f}."}
    items = [hit for _, hit in best]
    total = round(sum(h["product"]["price"] for h in items), 2)
    return {
        "found": True,
        "budget": budget,
        "total": total,
        "remaining": round(budget - total, 2),
        "items": items,
    }
