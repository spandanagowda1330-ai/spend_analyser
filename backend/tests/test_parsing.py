import pytest

from app.merchants import clean_merchant, guess_category
from app.parsing import StatementError, parse_statement


def parse(text, name="s.csv", **kw):
    return parse_statement(text.encode("utf-8"), name, **kw)


def test_simple_format_still_works():
    df, info = parse("date,description,amount\n2026-01-05,NETFLIX,15.49\n2026-02-05,NETFLIX,15.49\n")
    assert len(df) == 2
    assert info["total_spent"] == 30.98


def test_indian_bank_with_junk_lines_and_debit_credit_columns():
    text = (
        "HDFC BANK Account Statement\nCustomer: X\n\n"
        "Date,Narration,Chq./Ref.No.,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance\n"
        '05/01/26,UPI-SWIGGY-swiggy@icici-1,0001,05/01/26,"1,250.50",,9000\n'
        '06/01/26,SALARY ACME,0002,06/01/26,,"85,000.00",94000\n'
    )
    df, info = parse(text)
    assert len(df) == 1                      # salary is ignored
    assert df.iloc[0]["amount"] == 1250.50   # commas handled
    assert str(df.iloc[0]["date"]) == "2026-01-05"
    assert info["description_column"] == "Narration"
    assert info["date_column"] == "Date"     # not "Value Dt"


def test_negative_amounts_are_spending_and_income_is_dropped():
    df, _ = parse("Date,Description,Amount\n2026-01-05,STARBUCKS,-4.50\n2026-01-06,PAYROLL,2500\n")
    assert list(df["amount"]) == [4.5]


def test_credit_card_positive_amounts_are_spending_and_payment_is_dropped():
    text = "Date,Description,Amount\n2026-01-05,AMAZON,25.10\n2026-01-06,SHELL,40\n2026-01-07,PAYMENT THANK YOU,-200\n"
    df, info = parse(text)
    assert len(df) == 2
    assert "positive" in info["amount_mode"]


def test_amount_with_dr_cr_marker_column():
    text = "Date,Description,Amount,Type\n2026-01-05,SHOP,100,DR\n2026-01-06,SALARY,5000,CR\n"
    df, _ = parse(text)
    assert list(df["amount"]) == [100.0]


def test_semicolon_delimiter():
    df, _ = parse("Date;Payee;Amount\n2026-01-05;SHOP;-10\n2026-01-06;CAFE;-5\n")
    assert len(df) == 2


def test_iso_dates_are_never_swapped():
    df, _ = parse("date,description,amount\n2026-01-05,SHOP,10\n")
    assert str(df.iloc[0]["date"]) == "2026-01-05"


def test_day_first_detected_from_values():
    df, info = parse("date,description,amount\n25/12/2026,SHOP,10\n01/02/2026,SHOP,10\n")
    assert info["date_order"] == "day first"
    assert "2026-02-01" in [str(d) for d in df["date"]]


def test_month_first_detected_from_values():
    df, info = parse("date,description,amount\n12/25/2026,SHOP,10\n02/01/2026,SHOP,10\n")
    assert info["date_order"] == "month first"
    assert "2026-02-01" in [str(d) for d in df["date"]]


def test_user_can_override_date_order():
    df, _ = parse("date,description,amount\n03/04/2026,SHOP,10\n", date_order="monthfirst")
    assert str(df.iloc[0]["date"]) == "2026-03-04"


def test_file_without_header_is_understood():
    df, _ = parse("05-01-2026,NETFLIX,649\n05-02-2026,NETFLIX,649\n")
    assert len(df) == 2


def test_garbage_file_gives_a_clear_error():
    with pytest.raises(StatementError):
        parse("hello,world\nfoo,bar\n")


def test_old_xls_is_rejected_with_advice():
    with pytest.raises(StatementError, match="xlsx"):
        parse_statement(b"x", "old.xls")


def test_bad_option_is_rejected():
    with pytest.raises(StatementError):
        parse("date,description,amount\n2026-01-05,SHOP,10\n", spend_sign="sideways")


# merchants and categories -------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("UPI-SWIGGY-swiggy@icici-1234", "Swiggy"),
    ("POS 4412 BIG BAZAAR MUMBAI", "Big Bazaar"),
    ("PAYPAL *SPOTIFY", "Spotify"),
    ("COLA SHOP 22", "Cola Shop"),          # must not be mistaken for Ola
    ("UPI-RAHUL KUMAR-rahul@ybl-9988", "Rahul Kumar"),
])
def test_generic_merchant_cleaning(raw, expected):
    assert clean_merchant(raw) == expected


def test_variable_reference_numbers_do_not_split_a_merchant():
    a = clean_merchant("SPOTIFY P1A2B3")
    b = clean_merchant("SPOTIFY P9Z8Y7")
    assert a == b == "Spotify"


def test_category_guess_for_unknown_merchants():
    assert guess_category("Joes Pizza") == "Dining"
    assert guess_category("City Pharmacy") == "Health & Fitness"
    assert guess_category("Blue Bottle", "SQ *BLUE BOTTLE COFFEE") == "Dining"
    assert guess_category("Rahul Kumar") == "Other"
