from fastapi import APIRouter, Depends, HTTPException
from greenvolt_api.schemas import BulkPricingCreate
from users import get_current_user
from sqlalchemy.orm import Session
from greenvolt_api.database import SessionLocal
from greenvolt_api.models import Pricing, User
from typing import List

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/bulk/")
def bulk_pricing_upload(prices: List[BulkPricingCreate],
                        db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    if not prices:
        raise HTTPException(status_code=400, detail="Empty pricing list")

    results = []
    for p in prices:
        existing = db.query(Pricing).filter(Pricing.date == p.date).first()
        if existing:
            existing.price_per_kwh = p.price_per_kwh
            db.commit()
            db.refresh(existing)
            results.append({"id": existing.id, "date": existing.date, "price_per_kwh": existing.price_per_kwh, "status": "updated"})
        else:
            new_rate = Pricing(date=p.date, price_per_kwh=p.price_per_kwh)
            db.add(new_rate)
            db.commit()
            db.refresh(new_rate)
            results.append({"id": new_rate.id, "date": new_rate.date, "price_per_kwh": new_rate.price_per_kwh, "status": "added"})

    return {"uploaded_count": len(results), "details": results}
