"""Turn almost any bank or credit-card statement (CSV or Excel) into three columns:
date, description, amount   (amount > 0 means money spent).

The reader works out the layout by itself:
  * junk lines above the header row are skipped
  * the delimiter (comma, semicolon, tab, pipe) is detected
  * the date, description and amount columns are found by name, then by content
  * separate Debit / Credit columns, a signed Amount column, or Amount + Dr/Cr
    marker columns are all understood
  * dates are read as day-first or month-first by looking at the values
"""
import csv
import io
import re

import pandas as pd


class StatementError(ValueError):
    """An error whose message is safe and useful to show to the user."""


DATE_WORDS = {"date", "dt"}
DEBIT_WORDS = {"debit", "debits", "withdrawal", "withdrawals", "withdrawl", "dr", "paid", "spent"}
AMOUNT_WORDS = {"amount", "amt"}
DESC_PRIORITY = [
    "narration", "description", "details", "particulars", "remarks",
    "merchant", "payee", "memo", "transaction", "name", "reference",
]
TYPE_VALUES = {"DR", "CR", "DR.", "CR.", "D", "C", "DEBIT", "CREDIT", "WITHDRAWAL", "DEPOSIT"}
DEBIT_VALUES = {"DR", "DR.", "D", "DEBIT", "WITHDRAWAL"}


# ---------------------------------------------------------------- reading ----

def _tokens(name):
    return set(re.findall(r"[a-z]+", str(name).lower()))


def _decode(content: bytes) -> str:
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        return content.decode("utf-16")
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    raise StatementError("Could not read the file. Is it a CSV or Excel file?")


def _read_rows(content: bytes, filename: str) -> list[list[str]]:
    name = (filename or "").lower()
    if name.endswith(".xls"):
        raise StatementError(
            "Old .xls files are not supported. Open it in Excel and save it as .xlsx or .csv."
        )
    if name.endswith((".xlsx", ".xlsm")):
        try:
            frame = pd.read_excel(io.BytesIO(content), header=None, dtype=str, sheet_name=0)
        except Exception:
            raise StatementError(
                "Could not read the Excel file. Save it as .csv and try again."
            )
        rows = frame.fillna("").values.tolist()
    else:
        text = _decode(content)
        sample = [line for line in text.splitlines() if line.strip()][:40]
        delimiter = max([",", ";", "\t", "|"], key=lambda d: sum(line.count(d) for line in sample))
        rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))

    rows = [[str(c).strip() for c in r] for r in rows]
    rows = [r for r in rows if any(r)]
    if not rows:
        raise StatementError("The file is empty.")
    width = max(len(r) for r in rows)
    return [r + [""] * (width - len(r)) for r in rows]


def _find_header(rows):
    for i, row in enumerate(rows[:50]):
        toks = [_tokens(c) for c in row]
        has_date = any(t & DATE_WORDS for t in toks)
        has_money = any(t & (AMOUNT_WORDS | DEBIT_WORDS) for t in toks)
        if has_date and has_money:
            return i
    return None


def _unique(names):
    seen, out = {}, []
    for i, n in enumerate(names):
        n = n or f"column {i + 1}"
        seen[n] = seen.get(n, 0) + 1
        out.append(n if seen[n] == 1 else f"{n} ({seen[n]})")
    return out


# --------------------------------------------------------------- numbers -----

def _lenient_number(series):
    """'1,250.50', '$12', '(5.00)', '1250.50 Dr' -> numbers."""
    s = series.astype(str).str.strip()
    negative = s.str.startswith("(") & s.str.endswith(")")
    s = s.str.replace(r"[^0-9.\-]", "", regex=True)
    n = pd.to_numeric(s, errors="coerce")
    n[negative] = -n[negative].abs()
    return n


def _numeric_rate(series):
    """Share of non-empty cells that are plain numbers (so IDs and text score ~0)."""
    s = series.astype(str).str.strip()
    s = s[s != ""]
    if s.empty:
        return 0.0
    plain = s.str.replace(r"[,\s₹$€£]", "", regex=True)
    plain = plain.str.replace(r"^\((.*)\)$", r"-\1", regex=True)
    plain = plain.str.replace(r"(?i)(dr|cr)\.?$", "", regex=True)
    return float(pd.to_numeric(plain, errors="coerce").notna().mean())


def _avg_len(series):
    s = series.astype(str).str.strip()
    s = s[s != ""]
    return float(s.str.len().mean()) if len(s) else 0.0


# ----------------------------------------------------------------- dates -----

def _parse_dates(series, order):
    """Returns (dates, label). ISO dates are always read as year-month-day."""
    s = series.astype(str).str.strip()
    iso = s.str.match(r"^\d{4}-\d{2}-\d{2}")
    iso_part = pd.to_datetime(s.str[:10].where(iso), format="%Y-%m-%d", errors="coerce")
    rest = s.where(~iso)

    if order == "auto":
        dayfirst = True
        try:
            parts = rest.dropna().str.extract(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})")
            first = pd.to_numeric(parts[0], errors="coerce")
            second = pd.to_numeric(parts[1], errors="coerce")
            if (second > 12).any() and not (first > 12).any():
                dayfirst = False
        except Exception:
            pass
    else:
        dayfirst = order == "dayfirst"

    other_part = pd.to_datetime(rest, errors="coerce", dayfirst=dayfirst, format="mixed")
    dates = iso_part.fillna(other_part)
    if iso.all():
        label = "year-month-day"
    else:
        label = "day first" if dayfirst else "month first"
    return dates, label


# -------------------------------------------------------- column picking -----

def _infer_without_header(df):
    """No header row: find the columns by what is inside them."""
    date_col = amount_col = desc_col = None
    best_date = 0.0
    for c in df.columns:
        sample = df[c].astype(str).str.strip().head(60)
        sample = sample[sample != ""]
        if sample.empty:
            continue
        parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
        rate = float(parsed.notna().mean())
        if rate > 0.7 and rate > best_date and _numeric_rate(sample) < 0.5:
            date_col, best_date = c, rate
    for c in df.columns:
        if c != date_col and _numeric_rate(df[c]) > 0.7:
            amount_col = c
            break
    texts = [c for c in df.columns
             if c not in (date_col, amount_col) and _numeric_rate(df[c]) < 0.5]
    if texts:
        desc_col = max(texts, key=lambda c: _avg_len(df[c]))
    if not (date_col and amount_col and desc_col):
        raise StatementError(
            "Could not find the date, description and amount in this file. "
            "It needs a date, a text description and an amount for each transaction."
        )
    return date_col, desc_col, amount_col


def _pick_columns(df, has_header):
    cols = list(df.columns)
    if not has_header:
        d, t, a = _infer_without_header(df)
        return {"date": d, "desc": t, "debit": None, "amount": a, "type": None}

    toks = {c: _tokens(c) for c in cols}
    date_cands = [c for c in cols if toks[c] & DATE_WORDS]
    date_col = next((c for c in date_cands if "value" not in toks[c]), None) or (
        date_cands[0] if date_cands else None
    )
    if not date_col:
        raise StatementError("Could not find a date column.")

    debit = next(
        (c for c in cols
         if toks[c] & DEBIT_WORDS and c not in date_cands and _numeric_rate(df[c]) > 0.5),
        None,
    )
    amount = None
    if not debit:
        amount = next(
            (c for c in cols
             if toks[c] & AMOUNT_WORDS and c not in date_cands and _numeric_rate(df[c]) > 0.5),
            None,
        )
        if not amount:
            raise StatementError(
                "Could not find an amount column (or Debit / Withdrawal column)."
            )

    money_cols = {c for c in cols if toks[c] & (AMOUNT_WORDS | DEBIT_WORDS | {"credit", "credits", "deposit", "deposits", "cr", "balance"})}
    taken = set(date_cands) | money_cols | {debit, amount}

    desc = None
    for hint in DESC_PRIORITY:
        for c in cols:
            if hint in toks[c] and c not in taken and _avg_len(df[c]) >= 5 and _numeric_rate(df[c]) < 0.5:
                desc = c
                break
        if desc:
            break
    if not desc:
        texts = [c for c in cols if c not in taken and _numeric_rate(df[c]) < 0.5]
        if not texts:
            raise StatementError("Could not find a description column.")
        desc = max(texts, key=lambda c: _avg_len(df[c]))

    type_col = None
    if amount:
        for c in cols:
            if c in (date_col, desc, amount):
                continue
            vals = df[c].astype(str).str.strip().str.upper()
            vals = vals[vals != ""]
            if len(vals) >= 0.5 * len(df) and set(vals.unique()) <= TYPE_VALUES:
                type_col = c
                break

    return {"date": date_col, "desc": desc, "debit": debit, "amount": amount, "type": type_col}


# ---------------------------------------------------------------- public -----

def parse_statement(content: bytes, filename: str, spend_sign: str = "auto",
                    date_order: str = "auto"):
    """Returns (DataFrame[date, description, amount], info dict)."""
    if spend_sign not in ("auto", "negative", "positive"):
        raise StatementError("spend_sign must be auto, negative or positive.")
    if date_order not in ("auto", "dayfirst", "monthfirst"):
        raise StatementError("date_order must be auto, dayfirst or monthfirst.")

    rows = _read_rows(content, filename)
    header_idx = _find_header(rows)
    has_header = header_idx is not None
    if has_header:
        df = pd.DataFrame(rows[header_idx + 1:], columns=_unique(rows[header_idx]), dtype=str)
    else:
        df = pd.DataFrame(rows, columns=[f"column {i + 1}" for i in range(len(rows[0]))], dtype=str)
    if df.empty:
        raise StatementError("No transactions found below the header row.")

    picked = _pick_columns(df, has_header)

    if picked["debit"]:
        spend = _lenient_number(df[picked["debit"]]).abs()
        mode = f"spending = column '{picked['debit']}' (credits and deposits ignored)"
    elif picked["type"]:
        amt = _lenient_number(df[picked["amount"]]).abs()
        marker = df[picked["type"]].astype(str).str.strip().str.upper()
        spend = amt.where(marker.isin(DEBIT_VALUES))
        mode = f"spending = '{picked['amount']}' where '{picked['type']}' says debit"
    else:
        amt = _lenient_number(df[picked["amount"]])
        sign = spend_sign
        if sign == "auto":
            sign = "negative" if (amt < 0).sum() >= (amt > 0).sum() else "positive"
        spend = -amt if sign == "negative" else amt
        how = "chosen by you" if spend_sign != "auto" else "auto-detected"
        mode = f"spending = {sign} values in '{picked['amount']}' ({how})"

    dates, date_label = _parse_dates(df[picked["date"]], date_order)
    out = pd.DataFrame({
        "date": dates,
        "description": df[picked["desc"]].astype(str).str.replace(r"\s+", " ", regex=True).str.strip(),
        "amount": spend,
    })
    rows_read = len(out)
    out = out[(out["amount"] > 0) & out["date"].notna() & (out["description"] != "")]
    if out.empty:
        raise StatementError(
            "No spending transactions were found. Check the Options (spending sign and date "
            "order) or tell me what the file looks like."
        )
    out = out.sort_values("date").reset_index(drop=True)
    out["amount"] = out["amount"].round(2)
    out["date"] = out["date"].dt.date

    info = {
        "date_column": picked["date"],
        "description_column": picked["desc"],
        "amount_mode": mode,
        "date_order": date_label,
        "rows_read": rows_read,
        "rows_kept": len(out),
        "rows_skipped": rows_read - len(out),
        "first_date": str(out["date"].min()),
        "last_date": str(out["date"].max()),
        "total_spent": round(float(out["amount"].sum()), 2),
    }
    return out, info
