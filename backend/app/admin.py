from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import Insight, Subscription, Transaction

router = APIRouter()


@router.get("/config")
def get_config():
    return {"currency": settings.currency.upper(), "currency_symbol": settings.currency_symbol}


@router.delete("/data")
def clear_data(db: Session = Depends(get_db)):
    """Delete all transactions, subscriptions and insights (AI category cache is kept)."""
    db.query(Transaction).update({Transaction.subscription_id: None})
    deleted = db.query(Transaction).delete()
    db.query(Subscription).delete()
    db.query(Insight).delete()
    db.commit()
    return {"deleted_transactions": deleted}
