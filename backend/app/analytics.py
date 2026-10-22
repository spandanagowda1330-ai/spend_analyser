from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from .db import get_db
from .models import Transaction

router = APIRouter(prefix="/analytics")

MONTH = func.to_char(Transaction.date, "YYYY-MM")


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    total = float(db.query(func.sum(Transaction.amount)).scalar() or 0)
    first, last = db.query(
        func.min(Transaction.date), func.max(Transaction.date)
    ).one()
    months = db.query(func.count(func.distinct(MONTH))).scalar() or 0
    count = db.query(func.count(Transaction.id)).scalar() or 0

    return {
        "total_spent": round(total, 2),
        "transactions": count,
        "months": months,
        "average_per_month": round(total / months, 2) if months else 0,
        "first_date": first,
        "last_date": last,
    }


@router.get("/monthly")
def monthly(db: Session = Depends(get_db)):
    subscription_amount = case(
        (Transaction.subscription_id.isnot(None), Transaction.amount), else_=0
    )
    rows = (
        db.query(
            MONTH.label("month"),
            func.sum(Transaction.amount),
            func.sum(subscription_amount),
            func.count(Transaction.id),
        )
        .group_by(MONTH)
        .order_by(MONTH)
        .all()
    )

    result = []
    previous = None
    for month, total, subs, count in rows:
        total, subs = float(total), float(subs)
        change = None
        if previous:
            change = round((total - previous) / previous * 100, 1)
        result.append(
            {
                "month": month,
                "total": round(total, 2),
                "subscriptions": round(subs, 2),
                "other": round(total - subs, 2),
                "transactions": count,
                "change_pct": change,
            }
        )
        previous = total
    return result


@router.get("/top-merchants")
def top_merchants(limit: int = 5, db: Session = Depends(get_db)):
    grand_total = float(db.query(func.sum(Transaction.amount)).scalar() or 0) or 1
    rows = (
        db.query(
            Transaction.merchant,
            func.sum(Transaction.amount),
            func.count(Transaction.id),
            func.max(Transaction.category),
            func.count(Transaction.subscription_id),
        )
        .filter(Transaction.merchant.isnot(None))
        .group_by(Transaction.merchant)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "merchant": merchant,
            "total": round(float(total), 2),
            "transactions": count,
            "category": category,
            "percent": round(float(total) / grand_total * 100, 1),
            "is_subscription": sub_count > 0,
        }
        for merchant, total, count, category, sub_count in rows
    ]


@router.get("/spikes")
def spikes(db: Session = Depends(get_db)):
    """Months where a category cost at least 1.5x its usual monthly amount."""
    rows = (
        db.query(
            Transaction.category,
            MONTH.label("month"),
            func.sum(Transaction.amount),
        )
        .filter(Transaction.category.isnot(None))
        .group_by(Transaction.category, MONTH)
        .all()
    )

    by_category = defaultdict(dict)
    for category, month, total in rows:
        by_category[category][month] = float(total)

    found = []
    for category, months in by_category.items():
        if len(months) < 4:
            continue
        for month, amount in months.items():
            others = [v for m, v in months.items() if m != month]
            usual = sum(others) / len(others)
            if amount >= usual * 1.5 and amount - usual >= 20:
                found.append(
                    {
                        "category": category,
                        "month": month,
                        "amount": round(amount, 2),
                        "usual": round(usual, 2),
                        "extra": round(amount - usual, 2),
                    }
                )

    found.sort(key=lambda s: s["extra"], reverse=True)
    return found