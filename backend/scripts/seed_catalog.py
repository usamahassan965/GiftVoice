"""Build the GiftVoice catalog.

1. DummyJSON gift-friendly products (real product photos, no key needed)
2. Curated gift items (seed_data/curated_gifts.py) with photos from the Pexels API
   (falls back to generated placeholder images when PEXELS_API_KEY is missing)
3. Text (bge-small) and image (CLIP) embeddings into ChromaDB

Usage (from backend/):  python -m scripts.seed_catalog [--no-vectors] [--no-pexels]
"""

import argparse
import hashlib
import json
import random
import re
import sys
import time
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402
from app.db.database import connect, db_path, dumps, init_db  # noqa: E402
from app.services.taxonomy import DUMMYJSON_CATEGORY_MAP  # noqa: E402
from seed_data.curated_gifts import CURATED  # noqa: E402

CREDITS_FILE = config.IMAGES_DIR / "credits.json"
HTTP = httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": "GiftVoice-seed/1.0"})

REVIEW_TEMPLATES = [
    "Bought this for my {who} for {occ} and they absolutely loved it.",
    "Beautiful quality, arrived {speed} and the gift wrap was lovely.",
    "Exactly as pictured. {who_cap} uses it every day now.",
    "Great value for the price. Would gift again.",
    "Thoughtful present for anyone into {interest}.",
    "Packaging felt premium, perfect for {occ}.",
]
REVIEWERS = ["Ayesha K.", "Daniel R.", "Maria S.", "Omar F.", "Priya N.", "James T.", "Sara L.", "Hamza A.",
             "Chen W.", "Fatima Z.", "Lucas M.", "Nadia H."]


def rng_for(key: str) -> random.Random:
    return random.Random(int(hashlib.md5(key.encode()).hexdigest()[:8], 16))


def fake_reviews(key: str, interests: list[str], occasions: list[str], recipients: list[str]) -> list[dict]:
    r = rng_for(key + "reviews")
    who = next((x for x in recipients if x not in ("anyone", "her", "him")), "friend")
    reviews = []
    for template in r.sample(REVIEW_TEMPLATES, 3):
        reviews.append({
            "rating": r.choice([4, 5, 5, 5]),
            "reviewer": r.choice(REVIEWERS),
            "comment": template.format(
                who=who, who_cap=who.capitalize(), occ=(r.choice(occasions) if occasions else "a birthday").replace("_", " "),
                interest=r.choice(interests) if interests else "gifts", speed=r.choice(["early", "on time", "quickly"]),
            ),
        })
    return reviews


def download(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    try:
        resp = HTTP.get(url)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        print(f"  ! download failed {url}: {e}")
        return False
    dest.write_bytes(resp.content)
    return True


def ship_days_from_text(text: str) -> int:
    t = (text or "").lower()
    if "overnight" in t:
        return 1
    nums = [int(n) for n in re.findall(r"\d+", t)] or [3]
    days = max(nums)
    if "week" in t:
        days *= 5
    return max(1, min(days, 10))


# ---- DummyJSON -----------------------------------------------------------------------------------

def dummyjson_products() -> list[dict]:
    print("Fetching DummyJSON products...")
    data = HTTP.get("https://dummyjson.com/products", params={"limit": 0}).json()["products"]
    out = []
    for d in data:
        meta = DUMMYJSON_CATEGORY_MAP.get(d["category"])
        if not meta:
            continue
        pid = f"dj-{d['id']}"
        url = (d.get("images") or [d["thumbnail"]])[0]
        ext = Path(url.split("?")[0]).suffix or ".png"
        filename = f"{pid}{ext}"
        if not download(url, config.IMAGES_DIR / filename):
            continue
        r = rng_for(pid)
        reviews = [{"rating": rv["rating"], "reviewer": rv["reviewerName"], "comment": rv["comment"]}
                   for rv in d.get("reviews", [])]
        out.append({
            "id": pid, "name": d["title"], "description": d["description"], "category": meta["category"],
            "price": round(float(d["price"]), 2), "image_path": filename, "image_credit": "DummyJSON",
            "image_credit_url": "https://dummyjson.com", "tags": d.get("tags", []),
            "interests": meta["interests"], "occasions": meta["occasions"], "recipients": meta["recipients"],
            "stock": int(d.get("stock", 20)), "ship_days": ship_days_from_text(d.get("shippingInformation", "")),
            "rating": round(float(d.get("rating", 4.2)), 1), "review_count": r.randint(8, 420),
            "reviews": reviews, "source": "dummyjson",
        })
    print(f"  kept {len(out)} gift-friendly DummyJSON products")
    return out


# ---- Curated + Pexels ----------------------------------------------------------------------------

def placeholder_image(dest: Path, title: str, category: str) -> None:
    r = rng_for(category)
    bg = tuple(r.randint(170, 235) for _ in range(3))
    img = Image.new("RGB", (600, 600), bg)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 34)
    except OSError:
        font = ImageFont.load_default()
    words, lines, line = title.split(), [], ""
    for w in words:
        if len(line + " " + w) > 18:
            lines.append(line)
            line = w
        else:
            line = (line + " " + w).strip()
    lines.append(line)
    y = 300 - len(lines) * 22
    for ln in lines:
        width = draw.textlength(ln, font=font)
        draw.text(((600 - width) / 2, y), ln, fill=(40, 40, 40), font=font)
        y += 44
    img.save(dest, "JPEG", quality=88)


def pexels_photo(query: str) -> dict | None:
    resp = HTTP.get(
        "https://api.pexels.com/v1/search",
        params={"query": query, "per_page": 5, "orientation": "square"},
        headers={"Authorization": config.PEXELS_API_KEY},
    )
    if resp.status_code == 429:
        print("  ! Pexels rate limit hit; waiting 60s")
        time.sleep(60)
        return pexels_photo(query)
    resp.raise_for_status()
    photos = resp.json().get("photos", [])
    return photos[0] if photos else None


def curated_products(use_pexels: bool) -> list[dict]:
    credits = json.loads(CREDITS_FILE.read_text()) if CREDITS_FILE.exists() else {}
    use_pexels = use_pexels and bool(config.PEXELS_API_KEY)
    if not use_pexels:
        print("PEXELS_API_KEY not set (or --no-pexels): generating placeholder images for curated items")
    out = []
    for (slug, name, category, price, ship_days, stock, query, desc, interests, occasions, recipients) in CURATED:
        pid = f"cu-{slug}"
        filename = f"{pid}.jpg"
        dest = config.IMAGES_DIR / filename
        credit = credits.get(pid)
        if use_pexels and (credit is None or credit.get("photographer") == "placeholder"):
            photo = pexels_photo(query)
            if photo and download(photo["src"]["medium"], dest.with_suffix(".tmp")):
                dest.with_suffix(".tmp").replace(dest)
                credit = {"photographer": f"{photo['photographer']} / Pexels", "url": photo["url"]}
                print(f"  photo: {name} <- {photo['photographer']}")
            time.sleep(0.3)
        if not dest.exists() or credit is None:
            placeholder_image(dest, name, category)
            credit = {"photographer": "placeholder", "url": None}
        credits[pid] = credit
        r = rng_for(pid)
        out.append({
            "id": pid, "name": name, "description": desc, "category": category, "price": price,
            "image_path": filename,
            "image_credit": None if credit["photographer"] == "placeholder" else credit["photographer"],
            "image_credit_url": credit["url"], "tags": [], "interests": interests, "occasions": occasions,
            "recipients": recipients, "stock": stock, "ship_days": ship_days,
            "rating": round(r.uniform(4.1, 4.9), 1), "review_count": r.randint(12, 640),
            "reviews": fake_reviews(pid, interests, occasions, recipients), "source": "curated",
        })
    CREDITS_FILE.write_text(json.dumps(credits, indent=2))
    print(f"  prepared {len(out)} curated products")
    return out


# ---- Main ------------------------------------------------------------------------------------------

COLUMNS = ["id", "name", "description", "category", "price", "image_path", "image_credit", "image_credit_url",
           "tags", "interests", "occasions", "recipients", "stock", "ship_days", "rating", "review_count",
           "reviews", "source"]


def write_products(products: list[dict]) -> None:
    init_db()
    with connect() as conn:
        conn.execute("DELETE FROM products")
        conn.executemany(
            f"INSERT INTO products ({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))})",
            [tuple(dumps(p[c]) if isinstance(p[c], (list, dict)) else p[c] for c in COLUMNS) for p in products],
        )
    print(f"Wrote {len(products)} products to {db_path()}")


def build_vectors(products: list[dict]) -> None:
    from app.services.search import build_vector_index

    print("Embedding products (bge-small text + CLIP images) on CPU; first run downloads models...")
    images = {}
    for p in products:
        try:
            images[p["id"]] = Image.open(config.IMAGES_DIR / p["image_path"]).convert("RGB")
        except Exception as e:  # corrupt/unsupported file
            print(f"  ! skipping image for {p['id']}: {e}")
    build_vector_index(products, images)
    print(f"Vector index ready at {config.CHROMA_DIR}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-vectors", action="store_true", help="skip embeddings (BM25-only search)")
    parser.add_argument("--no-pexels", action="store_true", help="use placeholder images for curated items")
    args = parser.parse_args()

    config.IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    products = dummyjson_products() + curated_products(use_pexels=not args.no_pexels)
    write_products(products)
    if not args.no_vectors:
        build_vectors(products)


if __name__ == "__main__":
    main()
