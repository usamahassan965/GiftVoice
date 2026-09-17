"""Hybrid gift search: BM25 + dense vectors (bge-small) fused with RRF, then gift-aware re-ranking.

Image search embeds a photo with CLIP and matches it against CLIP embeddings of product photos.
The catalog is small (hundreds of items) so every query scores the whole catalog; filters and
boosts run in Python where they are easy to read and test.
"""

import logging
import re
from datetime import date, datetime
from functools import lru_cache

from rank_bm25 import BM25Okapi

from app import config
from app.services import delivery
from app.services.products import all_products
from app.services.taxonomy import RECIPIENT_EXPANSION, normalize_recipient

log = logging.getLogger(__name__)

RRF_K = 60
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
STOPWORDS = {"a", "an", "the", "for", "of", "and", "or", "to", "with", "in", "on", "my", "who", "is", "that",
             "gift", "gifts", "something", "some", "i", "want", "looking", "loves", "likes", "love", "her", "his"}


def product_document(p: dict) -> str:
    return " . ".join([
        p["name"], p["description"], p["category"].replace("-", " "),
        "good for " + ", ".join(p["interests"]),
        "occasions " + ", ".join(o.replace("_", " ") for o in p["occasions"]),
        "for " + ", ".join(p["recipients"]),
    ])


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


# ---- Index ------------------------------------------------------------------------------------

class _Index:
    def __init__(self) -> None:
        self.products = all_products()
        self.by_id = {p["id"]: p for p in self.products}
        self.ids = [p["id"] for p in self.products]
        self.bm25 = BM25Okapi([tokenize(product_document(p)) for p in self.products]) if self.products else None


_index: _Index | None = None


def index() -> _Index:
    global _index
    if _index is None:
        _index = _Index()
    return _index


def reset_index() -> None:
    """Call after catalog changes (seed, stock updates in tests)."""
    global _index
    _index = None


def _load_sentence_transformer(name: str):
    from sentence_transformers import SentenceTransformer
    try:
        # Cached copy first: checking the Hub for updates costs ~20 s on a slow link.
        return SentenceTransformer(name, device="cpu", local_files_only=True)
    except Exception:
        return SentenceTransformer(name, device="cpu")


@lru_cache(maxsize=1)
def _text_model():
    return _load_sentence_transformer(config.TEXT_EMBED_MODEL)


@lru_cache(maxsize=1)
def _clip_model():
    return _load_sentence_transformer(config.CLIP_MODEL)


@lru_cache(maxsize=1)
def _chroma():
    import chromadb
    return chromadb.PersistentClient(path=str(config.CHROMA_DIR))


def warm_up() -> None:
    """Load the catalog index and embedding models so the first search doesn't stall a conversation."""
    index()
    _chroma()
    _text_model()
    _clip_model()


def embed_texts(texts: list[str], is_query: bool = False) -> list[list[float]]:
    if is_query:
        texts = [BGE_QUERY_PREFIX + t for t in texts]
    return _text_model().encode(texts, normalize_embeddings=True).tolist()


def embed_images(images) -> list[list[float]]:
    """`images` are PIL images."""
    return _clip_model().encode(images, normalize_embeddings=True).tolist()


def build_vector_index(products: list[dict], images_by_id: dict) -> None:
    """(Re)build Chroma collections. `images_by_id` maps product id -> PIL image."""
    client = _chroma()
    for name in ("products_text", "products_image"):
        try:
            client.delete_collection(name)
        except Exception:
            pass
    text_col = client.create_collection("products_text", metadata={"hnsw:space": "cosine"})
    text_col.add(ids=[p["id"] for p in products], embeddings=embed_texts([product_document(p) for p in products]))
    if images_by_id:
        img_col = client.create_collection("products_image", metadata={"hnsw:space": "cosine"})
        ids = list(images_by_id)
        img_col.add(ids=ids, embeddings=embed_images([images_by_id[i] for i in ids]))


def _vector_ranking(query: str, n: int) -> list[str]:
    try:
        col = _chroma().get_collection("products_text")
        res = col.query(query_embeddings=embed_texts([query], is_query=True), n_results=n)
        return res["ids"][0]
    except Exception:
        log.warning("Vector search unavailable; falling back to BM25 only", exc_info=True)
        return []


# ---- Search -----------------------------------------------------------------------------------

def search_products(
    query: str = "",
    *,
    min_price: float | None = None,
    max_price: float | None = None,
    category: str | None = None,
    recipient: str | None = None,
    occasion: str | None = None,
    interests: list[str] | None = None,
    deadline: date | None = None,
    exclude_ids: set[str] | None = None,
    in_stock_only: bool = True,
    limit: int = 6,
    use_vectors: bool = True,
    now: datetime | None = None,
) -> list[dict]:
    idx = index()
    if not idx.products:
        return []
    now = now or datetime.now()
    recipient = normalize_recipient(recipient)
    accepted_recipients = set(RECIPIENT_EXPANSION.get(recipient, [recipient] if recipient else []))
    wanted_interests = {i.lower() for i in (interests or [])}

    # 1. Retrieval: rank fusion of lexical and dense rankings.
    fused: dict[str, float] = {pid: 0.0 for pid in idx.ids}
    q = " ".join(filter(None, [query, " ".join(wanted_interests)]))
    if q.strip():
        tokens = tokenize(q)
        if tokens:
            scores = idx.bm25.get_scores(tokens)
            lexical = [idx.ids[i] for i in sorted(range(len(scores)), key=lambda i: -scores[i]) if scores[i] > 0]
            for rank, pid in enumerate(lexical):
                fused[pid] += 1 / (RRF_K + rank + 1)
        if use_vectors:
            for rank, pid in enumerate(_vector_ranking(q, len(idx.ids))):
                if pid in fused:
                    fused[pid] += 1 / (RRF_K + rank + 1)

    results = []
    for pid, score in fused.items():
        p = idx.by_id[pid]
        # 2. Hard filters.
        if in_stock_only and p["stock"] <= 0:
            continue
        if exclude_ids and pid in exclude_ids:
            continue
        if min_price is not None and p["price"] < min_price:
            continue
        if max_price is not None and p["price"] > max_price:
            continue
        if category and category.lower() not in (p["category"], p["category"].replace("-", " ")):
            continue
        arrival = delivery.estimate_arrival(p["ship_days"], now)
        express_arrival = delivery.estimate_arrival(p["ship_days"], now, express=True)
        if deadline and express_arrival > deadline:
            continue

        # 3. Gift-aware boosts, recorded as reasons the agent can cite.
        why = []
        if accepted_recipients & set(p["recipients"]):
            score += 0.02
            why.append(f"popular for {recipient}")
        elif "anyone" in p["recipients"] and recipient:
            score += 0.005
        if occasion and occasion in p["occasions"]:
            score += 0.015
            why.append(f"fits {occasion.replace('_', ' ')}")
        overlap = wanted_interests & set(p["interests"])
        if overlap:
            score += 0.01 * min(len(overlap), 3)
            why.append("matches " + ", ".join(sorted(overlap)))
        score += 0.002 * (p["rating"] - 4.0)
        if deadline and arrival <= deadline:
            score += 0.008  # beats a slightly better rating that needs paid express shipping
            why.append("arrives on time")
        elif deadline:
            why.insert(0, "needs express to arrive on time")  # first, so the product card shows it
        if p["rating"] >= 4.6 and p["review_count"] >= 50:
            why.append(f"rated {p['rating']} by {p['review_count']} buyers")

        if q.strip() and fused[pid] == 0 and not why:
            continue  # irrelevant to the query and no gift signal
        results.append((score, p, why, arrival, express_arrival))

    results.sort(key=lambda r: -r[0])
    return [
        {"product": p, "why": why, "arrival": a.isoformat(), "express_arrival": e.isoformat()}
        for _, p, why, a, e in results[:limit]
    ]


def image_search(pil_image, limit: int = 6, max_price: float | None = None) -> list[dict]:
    col = _chroma().get_collection("products_image")
    res = col.query(query_embeddings=embed_images([pil_image]), n_results=min(40, col.count()))
    idx = index()
    out = []
    for pid, dist in zip(res["ids"][0], res["distances"][0]):
        p = idx.by_id.get(pid)
        if not p or p["stock"] <= 0 or (max_price is not None and p["price"] > max_price):
            continue
        out.append({"product": p, "similarity": round(1 - dist, 3)})
        if len(out) >= limit:
            break
    return out
