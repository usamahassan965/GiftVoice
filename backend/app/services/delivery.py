"""Deadline-aware delivery estimates.

Rules (demo store):
- `ship_days` on a product = business days from dispatch to doorstep (standard).
- Orders placed after the 14:00 cutoff, or on a weekend, dispatch the next business day.
- Express shaves 2 business days (minimum 1) for a flat fee.
- ship_days == 0 means a digital item delivered instantly.
"""

import re
from datetime import date, datetime, time, timedelta

CUTOFF = time(14, 0)
EXPRESS_FEE = 12.0
STANDARD_FEE = 5.0
FREE_SHIPPING_OVER = 75.0

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def add_business_days(start: date, days: int) -> date:
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


def dispatch_date(now: datetime) -> date:
    d = now.date()
    if d.weekday() >= 5 or now.time() >= CUTOFF:
        d = add_business_days(d, 1)
    return d


def estimate_arrival(ship_days: int, now: datetime, express: bool = False) -> date:
    if ship_days <= 0:
        return now.date()
    days = max(1, ship_days - 2) if express else ship_days
    return add_business_days(dispatch_date(now), days)


def parse_deadline(text: str, today: date) -> date | None:
    """Parse ISO dates and common spoken phrases ("next Thursday", "in 3 days")."""
    if not text:
        return None
    t = text.strip().lower()
    try:
        return date.fromisoformat(t)
    except ValueError:
        pass
    if t in ("today", "tonight"):
        return today
    if t == "tomorrow":
        return today + timedelta(days=1)
    if t in ("day after tomorrow", "the day after tomorrow"):
        return today + timedelta(days=2)
    m = re.fullmatch(r"in (\d+) days?", t)
    if m:
        return today + timedelta(days=int(m.group(1)))
    m = re.fullmatch(r"in (\d+|a|one|two) weeks?", t)
    if m:
        n = {"a": 1, "one": 1, "two": 2}.get(m.group(1)) or int(m.group(1))
        return today + timedelta(weeks=n)
    m = re.fullmatch(r"(this |next |on )?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", t)
    if m:
        target = WEEKDAYS.index(m.group(2))
        if m.group(1) == "next ":
            # The given weekday in the following Monday-started week.
            next_monday = today + timedelta(days=7 - today.weekday())
            return next_monday + timedelta(days=target)
        ahead = (target - today.weekday()) % 7 or 7
        return today + timedelta(days=ahead)
    return None


def shipping_fee(subtotal: float, express: bool, has_physical: bool) -> float:
    if not has_physical:
        return 0.0
    if express:
        return EXPRESS_FEE
    return 0.0 if subtotal >= FREE_SHIPPING_OVER else STANDARD_FEE


def check_products(products: list[dict], deadline: date | None, now: datetime) -> dict:
    """Per-product standard/express arrival and whether each meets the deadline."""
    rows = []
    for p in products:
        std = estimate_arrival(p["ship_days"], now)
        exp = estimate_arrival(p["ship_days"], now, express=True)
        row = {
            "product_id": p["id"],
            "name": p["name"],
            "standard_arrival": std.isoformat(),
            "express_arrival": exp.isoformat(),
            "in_stock": p["stock"] > 0,
        }
        if deadline:
            row["standard_on_time"] = std <= deadline
            row["express_on_time"] = exp <= deadline
        rows.append(row)
    result = {"today": now.date().isoformat(), "items": rows}
    if deadline:
        result["deadline"] = deadline.isoformat()
        result["all_on_time_standard"] = all(r["standard_on_time"] for r in rows)
        result["all_on_time_express"] = all(r["express_on_time"] for r in rows)
    return result
