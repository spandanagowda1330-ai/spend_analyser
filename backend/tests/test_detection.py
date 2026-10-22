from datetime import date, timedelta

from app.merchants import clean_merchant
from app.subscriptions import amounts_stable, detect_frequency


def monthly_dates(n, start=date(2026, 1, 5)):
    return [start + timedelta(days=30 * i) for i in range(n)]


def test_known_merchants_are_cleaned():
    assert clean_merchant("NETFLIX.COM 866-579-7172") == "Netflix"
    assert clean_merchant("AMZN MKTP US*2K4LM9") == "Amazon"
    assert clean_merchant("SPOTIFY P2B3C4D5E6") == "Spotify"


def test_unknown_merchant_drops_digits_and_symbols():
    assert clean_merchant("JOES PIZZA #4421") == "Joes Pizza"


def test_monthly_charges_are_detected():
    assert detect_frequency(monthly_dates(6)) == "monthly"


def test_weekly_charges_are_detected():
    dates = [date(2026, 1, 1) + timedelta(days=7 * i) for i in range(6)]
    assert detect_frequency(dates) == "weekly"


def test_yearly_charges_are_detected():
    assert detect_frequency([date(2024, 3, 1), date(2025, 3, 1)]) == "yearly"


def test_irregular_dates_are_not_a_subscription():
    dates = [
        date(2026, 1, 3),
        date(2026, 1, 19),
        date(2026, 2, 2),
        date(2026, 3, 28),
        date(2026, 4, 1),
    ]
    assert detect_frequency(dates) is None


def test_too_few_charges_are_not_a_subscription():
    assert detect_frequency(monthly_dates(2)) is None


def test_price_hike_still_counts_as_stable():
    assert amounts_stable([15.49] * 6 + [17.99] * 6)


def test_random_amounts_are_not_stable():
    assert not amounts_stable([4.5, 8.2, 5.1, 9.0, 4.2, 7.7])