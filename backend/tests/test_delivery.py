from datetime import date, datetime

from app.services import delivery

WED = date(2026, 9, 16)


def test_parse_iso_and_relative():
    assert delivery.parse_deadline("2026-09-20", WED) == date(2026, 9, 20)
    assert delivery.parse_deadline("tomorrow", WED) == date(2026, 9, 17)
    assert delivery.parse_deadline("in 3 days", WED) == date(2026, 9, 19)
    assert delivery.parse_deadline("in two weeks", WED) == date(2026, 9, 30)


def test_parse_weekdays():
    assert delivery.parse_deadline("friday", WED) == date(2026, 9, 18)
    assert delivery.parse_deadline("this Friday", WED) == date(2026, 9, 18)
    assert delivery.parse_deadline("wednesday", WED) == date(2026, 9, 23)  # same weekday -> next week
    assert delivery.parse_deadline("next thursday", WED) == date(2026, 9, 24)
    assert delivery.parse_deadline("next monday", WED) == date(2026, 9, 21)
    assert delivery.parse_deadline("whenever", WED) is None


def test_business_days_skip_weekend():
    # Friday + 1 business day = Monday
    assert delivery.add_business_days(date(2026, 9, 18), 1) == date(2026, 9, 21)


def test_cutoff_and_weekend_dispatch():
    assert delivery.dispatch_date(datetime(2026, 9, 16, 10)) == WED
    assert delivery.dispatch_date(datetime(2026, 9, 16, 15)) == date(2026, 9, 17)
    assert delivery.dispatch_date(datetime(2026, 9, 19, 9)) == date(2026, 9, 21)  # Saturday


def test_estimate_arrival_standard_express_digital():
    now = datetime(2026, 9, 16, 10)
    assert delivery.estimate_arrival(3, now) == date(2026, 9, 21)
    assert delivery.estimate_arrival(3, now, express=True) == date(2026, 9, 17)
    assert delivery.estimate_arrival(0, now) == WED


def test_shipping_fee():
    assert delivery.shipping_fee(40, express=False, has_physical=True) == delivery.STANDARD_FEE
    assert delivery.shipping_fee(80, express=False, has_physical=True) == 0
    assert delivery.shipping_fee(80, express=True, has_physical=True) == delivery.EXPRESS_FEE
    assert delivery.shipping_fee(80, express=True, has_physical=False) == 0
