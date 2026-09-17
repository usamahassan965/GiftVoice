from datetime import date

from app.services.bundles import build_bundle
from app.services.search import search_products
from tests.conftest import NOW


def ids(hits):
    return [h["product"]["id"] for h in hits]


def test_gardening_mom_query_ranks_gardening_first():
    hits = search_products("gardening", recipient="mother", occasion="mothers_day", max_price=70,
                           use_vectors=False, now=NOW)
    assert hits
    top = hits[0]["product"]
    assert "gardening" in top["interests"]
    assert top["price"] <= 70
    assert any("mom" in w or "mothers day" in w for w in hits[0]["why"])


def test_filters_price_stock_and_exclusions():
    hits = search_products("tea", max_price=30, use_vectors=False, now=NOW, limit=20)
    assert all(h["product"]["price"] <= 30 for h in hits)
    assert "cu-limited-advent-calendar" not in ids(search_products("advent calendar tea", use_vectors=False, now=NOW))
    excluded = search_products("tea", use_vectors=False, now=NOW, exclude_ids={"cu-matcha-starter-kit"}, limit=30)
    assert "cu-matcha-starter-kit" not in ids(excluded)


def test_deadline_excludes_slow_items():
    friday = date(2026, 9, 18)
    hits = search_products("personalized", deadline=friday, use_vectors=False, now=NOW, limit=30)
    assert hits
    for h in hits:
        assert date.fromisoformat(h["express_arrival"]) <= friday
    assert "cu-custom-star-map" not in ids(hits)  # 7 ship days


def test_deadline_prefers_standard_shipping_that_arrives_on_time():
    tuesday = date(2026, 9, 22)
    hits = search_products("gardening", recipient="mom", occasion="birthday", interests=["gardening"], max_price=50,
                           deadline=tuesday, use_vectors=False, now=NOW, limit=30)
    on_time = [date.fromisoformat(h["arrival"]) <= tuesday for h in hits]
    assert on_time[:2] == [True, True] and False in on_time
    for h, ok in zip(hits, on_time):
        # The product card shows the first reasons, so a paid-express requirement is never hidden.
        assert (h["why"][0] == "needs express to arrive on time") != ok


def test_irrelevant_query_returns_nothing():
    assert search_products("xylophone submarine", use_vectors=False, now=NOW) == []


def test_bundle_respects_budget_and_variety():
    result = build_bundle(100, theme="coffee", recipient="dad", use_vectors=False, now=NOW)
    assert result["found"]
    assert result["total"] <= 100
    cats = [h["product"]["category"] for h in result["items"]]
    assert len(cats) == len(set(cats))
    assert 2 <= len(cats) <= 4


def test_bundle_impossible_budget():
    assert build_bundle(15, theme="spa", use_vectors=False, now=NOW)["found"] is False
