"""Convert a real bank or credit-card CSV into the format the app expects.

Output columns: date, description, amount   (amount > 0 means money spent)

Usage (from the backend folder, venv active):
    python scripts\\prepare_statement.py "C:\\path\\to\\statement.csv"

Options:
    --skip-rows N        skip N junk lines above the header row (some banks add them)
    --monthfirst         dates are MM/DD/YYYY (default is DD/MM/YYYY)
    --spend-sign S       negative | positive, for single-amount-column files
                         (default: auto-detect)
    --out FILE           output file (default: <input>_clean.csv)
"""
import argparse
import re
import sys
from pathlib import Path

import pandas as pd

DATE_HINTS = ["date", "dt"]
DESC_HINTS = ["narration", "description", "details", "particulars", "remarks",
              "merchant", "payee", "memo", "transaction"]
DEBIT_HINTS = ["debit", "withdrawal", "withdrawl", "dr", "paid", "out"]
AMOUNT_HINTS = ["amount", "amt", "value"]


def tokens(col):
    return re.findall(r"[a-z]+", str(col).lower())


def find_col(columns, hints, exclude=()):
    for hint in hints:
        for col in columns:
            if col not in exclude and hint in tokens(col):
                return col
    return None


def to_number(series):
    s = series.astype(str).str.strip()
    negative = s.str.startswith("(") & s.str.endswith(")")
    s = s.str.replace(r"[^0-9.\-]", "", regex=True)
    n = pd.to_numeric(s, errors="coerce")
    n[negative] = -n[negative].abs()
    return n


def parse_dates(series, dayfirst):
    """ISO dates (YYYY-MM-DD) are read as-is; everything else honours dayfirst."""
    s = series.astype(str).str.strip()
    iso = s.str.match(r"^\d{4}-\d{2}-\d{2}")
    iso_part = pd.to_datetime(s.str[:10].where(iso), format="%Y-%m-%d", errors="coerce")
    other_part = pd.to_datetime(s.where(~iso), errors="coerce",
                                dayfirst=dayfirst, format="mixed")
    return iso_part.fillna(other_part)


def read_csv(path, skip):
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(path, skiprows=skip, sep=None, engine="python",
                               dtype=str, encoding=enc, skipinitialspace=True)
        except UnicodeDecodeError:
            continue
    sys.exit("Could not read the file. Is it a CSV?")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--skip-rows", type=int, default=0)
    ap.add_argument("--monthfirst", action="store_true")
    ap.add_argument("--spend-sign", choices=["negative", "positive"])
    ap.add_argument("--out")
    args = ap.parse_args()

    df = read_csv(args.input, args.skip_rows)
    df.columns = [str(c).strip() for c in df.columns]
    cols = list(df.columns)
    print("Columns found:", cols)

    # Prefer a plain "Date" over "Value Dt"
    date_candidates = [c for c in cols if any(h in tokens(c) for h in DATE_HINTS)]
    date_col = next((c for c in date_candidates if "value" not in tokens(c)),
                    date_candidates[0] if date_candidates else None)
    desc_col = find_col(cols, DESC_HINTS, exclude=[date_col])
    if not date_col or not desc_col:
        sys.exit(f"Could not find the date or description column in {cols}.\n"
                 "Rename them to 'date' and 'description' in Excel and try again.")

    debit_col = find_col(cols, DEBIT_HINTS, exclude=[date_col, desc_col])
    amount_col = find_col(cols, AMOUNT_HINTS, exclude=[date_col, desc_col])

    if debit_col:
        spend = to_number(df[debit_col]).abs()
        print(f"Using '{debit_col}' as spending (credits/deposits are ignored).")
    elif amount_col:
        amt = to_number(df[amount_col])
        sign = args.spend_sign
        if not sign:
            sign = "negative" if (amt < 0).sum() >= (amt > 0).sum() else "positive"
        print(f"Using '{amount_col}'; treating {sign} values as spending "
              "(override with --spend-sign).")
        spend = -amt if sign == "negative" else amt
    else:
        sys.exit(f"Could not find an amount column in {cols}.")

    out = pd.DataFrame({
        "date": parse_dates(df[date_col], dayfirst=not args.monthfirst),
        "description": df[desc_col].astype(str).str.replace(r"\s+", " ", regex=True).str.strip(),
        "amount": spend,
    })
    total_rows = len(df)
    out = out[(out["amount"] > 0) & out["date"].notna() & (out["description"] != "")]
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out["amount"] = out["amount"].round(2)
    out = out.sort_values("date")

    path = Path(args.out) if args.out else Path(args.input).with_name(
        Path(args.input).stem + "_clean.csv")
    out.to_csv(path, index=False)

    print(f"\nRead {total_rows} rows, kept {len(out)} spending rows "
          f"({total_rows - len(out)} skipped: income, payments, blanks or bad dates).")
    if len(out):
        print(f"Date range: {out['date'].min()} to {out['date'].max()}")
        print(f"Total spent: {out['amount'].sum():,.2f}")
    print(f"\nFirst rows:\n{out.head(5).to_string(index=False)}")
    print(f"\nSaved: {path}")


if __name__ == "__main__":
    main()
