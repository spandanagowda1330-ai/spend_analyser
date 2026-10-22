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
        dates = [t.date for t in items]
        amounts = [float(t.amount) for t in items]

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

    for s in subs:
        txns = sorted(s.transactions, key=lambda t: t.date)
        first_amount = float(txns[0].amount)
        latest = float(s.amount)
        per_year = CHARGES_PER_YEAR[s.frequency]
        annual = round(latest * per_year, 2)
        total_monthly += annual / 12

        change = round(latest - first_amount, 2)
        result.append(
            {
                "id": s.id,
                "merchant": s.merchant,
                "frequency": s.frequency,
                "amount": latest,
                "annual_cost": annual,
                "charges": len(txns),
                "first_seen": s.first_seen,
                "last_charged": s.last_charged,
                "status": s.status,
                "price_change": change if abs(change) > 0.005 else None,
            }
        )

    result.sort(key=lambda r: r["annual_cost"], reverse=True)
    return {
        "total_monthly_cost": round(total_monthly, 2),
        "total_annual_cost": round(total_monthly * 12, 2),
        "subscriptions": result,
    }