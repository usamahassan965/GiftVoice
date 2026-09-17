"""Recipient profiles and gift history (long-term memory across sessions)."""

import secrets
from datetime import date, datetime

from app.db.database import connect, dumps, row_to_dict
from app.services.taxonomy import RECIPIENTS, normalize_recipient


def _profile_with_history(conn, profile: dict) -> dict:
    rows = conn.execute(
        "SELECT h.product_id, p.name, h.occasion, h.created_at FROM gift_history h "
        "LEFT JOIN products p ON p.id = h.product_id WHERE h.recipient_id = ? ORDER BY h.created_at DESC",
        (profile["id"],),
    ).fetchall()
    profile["past_gifts"] = [
        {"product_id": r["product_id"], "name": r["name"], "occasion": r["occasion"], "date": r["created_at"][:10]}
        for r in rows
    ]
    return profile


def _same_person(conn, customer_id: str, name: str, relationship: str | None) -> dict | None:
    """The one profile for this relationship when either name is just the relationship word: checkout records
    "Mom", and the shopper later saves her as "Ammi" (or the reverse)."""
    rel = normalize_recipient(relationship) or normalize_recipient(name)
    if not rel:
        return None
    rows = conn.execute("SELECT * FROM recipients WHERE customer_id = ? AND relationship = ?",
                        (customer_id, rel)).fetchall()
    if len(rows) != 1:
        return None
    candidate = row_to_dict(rows[0])
    return candidate if normalize_recipient(candidate["name"]) or normalize_recipient(name) else None


def save_profile(customer_id: str, name: str, relationship: str | None = None,
                 interests: list[str] | None = None, notes: str | None = None,
                 occasions: list[dict] | None = None) -> dict:
    """Create or merge a recipient profile. Interests/occasions are merged, not replaced."""
    name = name.strip()
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM recipients WHERE customer_id = ? AND lower(name) = lower(?)", (customer_id, name)
        ).fetchone()
        existing = row_to_dict(row) or _same_person(conn, customer_id, name, relationship)
        if existing:
            if existing["name"].lower() in RECIPIENTS and name.lower() not in RECIPIENTS:
                # "Mom" (recorded at checkout) is now known by name, e.g. "Ammi".
                conn.execute("UPDATE recipients SET name = ? WHERE id = ?", (name, existing["id"]))
            merged_interests = list(dict.fromkeys(existing["interests"] + [i.lower() for i in (interests or [])]))
            occ_by_type = {o["type"]: o for o in existing["occasions"]}
            occ_by_type.update({o["type"]: o for o in (occasions or [])})
            conn.execute(
                "UPDATE recipients SET relationship = ?, interests = ?, notes = ?, occasions = ?, updated_at = ? "
                "WHERE id = ?",
                (normalize_recipient(relationship) or relationship or existing["relationship"],
                 dumps(merged_interests),
                 "; ".join(filter(None, [existing["notes"], notes])) or None,
                 dumps(list(occ_by_type.values())), now, existing["id"]),
            )
            profile_id = existing["id"]
        else:
            profile_id = f"r_{secrets.token_hex(4)}"
            conn.execute(
                "INSERT INTO recipients (id, customer_id, name, relationship, interests, notes, occasions, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (profile_id, customer_id, name, normalize_recipient(relationship) or relationship,
                 dumps([i.lower() for i in (interests or [])]), notes, dumps(occasions or []), now),
            )
        row = conn.execute("SELECT * FROM recipients WHERE id = ?", (profile_id,)).fetchone()
        return _profile_with_history(conn, row_to_dict(row))


def list_profiles(customer_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM recipients WHERE customer_id = ? ORDER BY updated_at DESC", (customer_id,)
        ).fetchall()
        return [_profile_with_history(conn, row_to_dict(r)) for r in rows]


def find_profile(customer_id: str, name_or_relationship: str) -> dict | None:
    key = name_or_relationship.strip().lower()
    rel = normalize_recipient(key)
    for p in list_profiles(customer_id):
        if p["name"].lower() == key or (rel and p["relationship"] == rel):
            return p
    return None


def past_gift_ids(recipient_id: str) -> set[str]:
    with connect() as conn:
        rows = conn.execute("SELECT product_id FROM gift_history WHERE recipient_id = ?", (recipient_id,)).fetchall()
    return {r["product_id"] for r in rows}


def upcoming_occasions(customer_id: str, today: date | None = None, within_days: int = 45) -> list[dict]:
    """Occasions stored as MM-DD that fall within the next `within_days`."""
    today = today or date.today()
    upcoming = []
    for p in list_profiles(customer_id):
        for occ in p["occasions"]:
            try:
                month, day = (int(x) for x in occ["date"].split("-")[-2:])
                when = date(today.year, month, day)
            except (KeyError, ValueError):
                continue
            if when < today:
                when = date(today.year + 1, month, day)
            days_left = (when - today).days
            if days_left <= within_days:
                upcoming.append({"recipient": p["name"], "occasion": occ["type"], "date": when.isoformat(),
                                 "days_left": days_left})
    return sorted(upcoming, key=lambda o: o["days_left"])
