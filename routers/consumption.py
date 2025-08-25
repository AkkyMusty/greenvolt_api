from typing import List

from fastapi import APIRouter, Depends, HTTPException,Query
from datetime import datetime

from sqlalchemy.orm import Session

from greenvolt_api.database import get_db
from greenvolt_api.models import SmartMeter, User, Consumption
from greenvolt_api.schemas import ConsumptionOut, ConsumptionCreate

router = APIRouter()



@router.post("/", response_model=ConsumptionOut)
def create_consumption(consumption: ConsumptionCreate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == consumption.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    meter = db.query(SmartMeter).filter(SmartMeter.id == consumption.smart_meter_id,
                                        SmartMeter.user_id == consumption.user_id).first()
    if not meter:
        raise HTTPException(status_code=404, detail="Smart meter not found for this user")

    new_consumption = Consumption(
        user_id=consumption.user_id,
        smart_meter_id=consumption.smart_meter_id,
        timestamp=consumption.timestamp,
        energy_kwh=consumption.energy_kwh
    )
    db.add(new_consumption)
    db.commit()
    db.refresh(new_consumption)
    return new_consumption


@router.get("/{user_id}", response_model=List[ConsumptionOut])
def get_consumption(
    user_id: int,
    start: datetime = Query(..., description="Start datetime (YYYY-MM-DDTHH:MM:SS)"),
    end: datetime = Query(..., description="End datetime (YYYY-MM-DDTHH:MM:SS)"),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    records = db.query(Consumption).filter(
        Consumption.user_id == user_id,
        Consumption.timestamp >= start,
        Consumption.timestamp <= end
    ).all()

    return records


@router.post("/bulk/")
def bulk_consumption_upload(consumptions: List[ConsumptionCreate], db: Session = Depends(get_db)):
    if not consumptions:
        raise HTTPException(status_code=400, detail="Empty consumption list")

    results = []
    for c in consumptions:
        new_record = Consumption(
            user_id=c.user_id,
            smart_meter_id=c.smart_meter_id,
            timestamp=c.timestamp,
            energy_kwh=c.energy_kwh
        )
        db.add(new_record)
        db.commit()
        db.refresh(new_record)
        results.append({
            "id": new_record.id,
            "timestamp": new_record.timestamp,
            "energy_kwh": new_record.energy_kwh
        })

    return {"uploaded_count": len(results), "details": results}

