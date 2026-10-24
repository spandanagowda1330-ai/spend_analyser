from collections import namedtuple
from datetime import date

from app.subscriptions import amounts_stable, detect_frequency, split_extras

Tx = namedtuple("Tx", "date amount")


def txs(*pairs):
    return [Tx(d, a) for d, a in pairs]


def test_normal_monthly_charges_have_no_extras():
    items = txs((date(2026, 7, 5), 649), (date(2026, 8, 5), 649), (date(2026, 9, 5), 649))
    kept, extras = split_extras(items)
    assert len(kept) == 3 and extras == []


def test_double_charge_in_same_cycle_is_an_extra():
    items = txs((date(2026, 7, 5), 649), (date(2026, 8, 5), 649), (date(2026, 8, 5), 649),
                (date(2026, 9, 5), 649), (date(2026, 10, 5), 649))
    kept, extras = split_extras(items)
    assert len(kept) == 4 and len(extras) == 1


def test_charge_a_few_days_after_the_normal_one_is_an_extra():
    items = txs((date(2026, 7, 5), 119), (date(2026, 8, 5), 119), (date(2026, 9, 5), 119),
                (date(2026, 10, 5), 119), (date(2026, 10, 10), 119))
    kept, extras = split_extras(items)
    assert len(extras) == 1 and extras[0].date == date(2026, 10, 10)


def test_subscription_with_extras_is_still_detected_after_removing_them():
    items = txs((date(2026, 7, 5), 649), (date(2026, 8, 5), 649), (date(2026, 8, 5), 649),
                (date(2026, 8, 5), 649), (date(2026, 9, 5), 649), (date(2026, 10, 5), 649))
    kept, _ = split_extras(items)
    assert detect_frequency([t.date for t in items]) is None          # noise hides it...
    assert detect_frequency([t.date for t in kept]) == "monthly"      # ...until extras are removed
    assert amounts_stable([float(t.amount) for t in kept])


def test_frequent_shopping_is_not_treated_as_extras():
    items = txs(*[(date(2026, 1, d), 100) for d in (1, 3, 4, 8, 9, 12, 15)])
    kept, extras = split_extras(items)
    assert extras == []
