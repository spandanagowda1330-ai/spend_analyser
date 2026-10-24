from statistics import median

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .db import get_db
from .merchants import clean_merchant
from .models import Subscription, Transaction

router = APIRouter()

# expected gap between charges, allowed wiggle room, minimum charges needed
FREQUENCIES = {
    "weekly": {"days": 7, "tolerance": 2, "min_count": 4},
    "monthly": {"days": 30, "tolerance": 4, "min_count": 3},
    "yearly": {"days": 365, "tolerance": 10, "min_count": 2},
}
CHARGES_PER_YEAR = {"weekly": 52, "monthly": 12, "yearly": 1}

# Recurring payments in these categories are bills (rent, electricity), not subscriptions
BILL_CATEGORIES = {"Utilities", "Housing"}


def kind_of(sub) -> str:
    """'bill' for rent/utilities, otherwise 'subscription'."""
    for t in sub.transactions:
        return "bill" if t.category in BILL_CATEGORIES else "subscription"
    return "subscription"


def detect_frequency(dates):
    """Return 'weekly' / 'monthly' / 'yearly' if the gaps are regular, else None."""
    gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
    if not gaps:
        return None
    for name, cfg in FREQUENCIES.items():
        if len(dates) < cfg["min_count"]:
            continue
        regular = sum(1 for g in gaps if abs(g - cfg["days"]) <= cfg["tolerance"])
        if regular / len(gaps) >= 0.8:
            return name
    return None


def amounts_stable(amounts):
    """True if most charges are within 5% of the previous one (allows a price hike)."""
    pairs = list(zip(amounts, amounts[1:]))
    if not pairs:
        return False
    close = sum(1 for a, b in pairs if abs(b - a) <= 0.05 * a)
    return close / len(pairs) >= 0.8


def split_extras(items):
    """Separate a merchant's normal billing cycle charges from extra ones.

    For a roughly monthly merchant, a charge within 10 days of the previous one for a
    similar amount is an EXTRA charge (a double charge, or one after cancelling), not a
    new billing cycle. Returns (kept, extras); items must be sorted by date.
    """
    if len(items) < 3:
        return list(items), []
    gaps = [(b.date - a.date).days for a, b in zip(items, items[1:])]
    if median(gaps) < 20:          # not a monthly-style merchant (e.g. daily shopping)
        return list(items), []
    kept, extras = [items[0]], []
    for t in items[1:]:
        last = kept[-1]
        close = (t.date - last.date).days <= 10
        similar = abs(float(t.amount) - float(last.amount)) <= 0.05 * float(last.amount)
        if close and similar:
            extras.append(t)
        else:
            kept.append(t)
    return kept, extras


def run_detection(db: Session) -> dict:
    # Start fresh so this can be re-run safely
    db.query(Transaction).update({Transaction.subscription_id: None})
    db.query(Subscription).delete()
    db.flush()

    txns = db.query(Transaction).order_by(Transaction.date).all()
    if not txns:
        return {"transactions_processed": 0, "subscriptions_found": 0}

    for t in txns:
        t.merchant = clean_merchant(t.raw_description)

    latest_date = max(t.date for t in txns)

    groups = {}
    for t in txns:
        groups.setdefault(t.merchant, []).append(t)

    found = 0
    for merchant, items in groups.items():
        kept, _extras = split_extras(items)
        dates = [t.date for t in kept]
        amounts = [float(t.amount) for t in kept]

        frequency = detect_frequency(dates)
        if not frequency or not amounts_stable(amounts):
            continue

        cycle_days = FREQUENCIES[frequency]["days"]
        days_since_last = (latest_date - dates[-1]).days
        status = "active" if days_since_last <= cycle_days * 1.5 else "possibly_cancelled"

        sub = Subscription(
            merchant=merchant,
            amount=amounts[-1],
            frequency=frequency,
            first_seen=dates[0],
            last_charged=dates[-1],
            status=status,
        )
        db.add(sub)
        db.flush()  # gives sub an id
        for t in items:
            t.subscription_id = sub.id
        found += 1

    db.commit()
    return {"transactions_processed": len(txns), "subscriptions_found": found}


@router.post("/process")
def process(db: Session = Depends(get_db)):
    return run_detection(db)


@router.get("/subscriptions")
def list_subscriptions(db: Session = Depends(get_db)):
    subs = db.query(Subscription).all()
    result = []
    total_monthly = 0.0
    bills_monthly = 0.0

    for s in subs:
        all_txns = sorted(s.transactions, key=lambda t: t.date)
        txns, extras = split_extras(all_txns)
        first_amount = float(txns[0].amount)
        latest = float(s.amount)
        per_year = CHARGES_PER_YEAR[s.frequency]
        annual = round(latest * per_year, 2)
        kind = kind_of(s)
        if kind == "bill":
            bills_monthly += annual / 12
        else:
            total_monthly += annual / 12

        change = round(latest - first_amount, 2)
        result.append(
            {
                "id": s.id,
                "merchant": s.merchant,
                "kind": kind,
                "frequency": s.frequency,
                "amount": latest,
                "annual_cost": annual,
                "charges": len(txns),
                "extra_charges": len(extras),
                "extra_amount": round(sum(float(t.amount) for t in extras), 2),
                "first_seen": s.first_seen,
                "last_charged": s.last_charged,
                "status": s.status,
                "price_change": change if abs(change) > 0.005 else None,
            }
        )

    # subscriptions first, then bills; most expensive first within each
    result.sort(key=lambda r: (r["kind"] == "bill", -r["annual_cost"]))
    return {
        "total_monthly_cost": round(total_monthly, 2),
        "total_annual_cost": round(total_monthly * 12, 2),
        "bills_monthly_cost": round(bills_monthly, 2),
        "bills_annual_cost": round(bills_monthly * 12, 2),
        "subscriptions": result,
    }
