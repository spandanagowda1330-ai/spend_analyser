from types import SimpleNamespace

from app.merchants import clean_merchant, guess_category
from app.subscriptions import kind_of


def sub(category):
    return SimpleNamespace(transactions=[SimpleNamespace(category=category)])


def test_rent_and_utilities_are_bills_not_subscriptions():
    assert kind_of(sub("Housing")) == "bill"
    assert kind_of(sub("Utilities")) == "bill"


def test_software_and_streaming_are_subscriptions():
    assert kind_of(sub("Software")) == "subscription"
    assert kind_of(sub("Entertainment")) == "subscription"
    assert kind_of(sub(None)) == "subscription"


def test_house_rent_months_become_one_merchant_in_housing():
    names = {clean_merchant(f"HOUSE RENT {m}") for m in ("JULY", "AUGUST", "SEPTEMBER")}
    assert names == {"House Rent"}
    assert guess_category("House Rent") == "Housing"


def test_cash_and_vegetables_have_their_own_categories():
    assert guess_category("Cash Withdrawal") == "Cash"
    assert guess_category("Vegetable Shop", "UPI/VEGETABLE SHOP") == "Groceries"
