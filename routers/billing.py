from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from greenvolt_api.database import get_db
from greenvolt_api.models import SmartMeter, User, Pricing, SmartMeterReading
from routers.users import get_current_user
from sqlalchemy.orm import Session

router = APIRouter()

@router.get("/{user_id}")
def calculate_bill_with_breakdown(
    user_id: int,
    start: date,
    end: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Get user's meters
    meters = db.query(SmartMeter).filter(SmartMeter.user_id == user_id).all()
    if not meters:
        raise HTTPException(status_code=404, detail="No smart meters found for this user")

    meter_ids = [m.id for m in meters]

    # Get readings in date range
    readings = db.query(SmartMeterReading).filter(
        SmartMeterReading.meter_id.in_(meter_ids),
        SmartMeterReading.timestamp >= start,
        SmartMeterReading.timestamp <= end
    ).all()

    if not readings:
        return {
            "user_id": user_id,
            "total_kwh": 0,
            "total_cost": 0,
            "co2_avoided_kg": 0,
            "daily_breakdown": []
        }

    total_kwh = 0
    total_cost = 0
    daily_data = defaultdict(lambda: {"kwh": 0, "cost": 0})

    EMISSIONS_FACTOR_KG_PER_KWH = 0.4

    for reading in readings:
        # Round timestamp to hour for matching pricing
        rate = db.query(Pricing).filter(
            Pricing.date == reading.timestamp.replace(minute=0, second=0, microsecond=0)
        ).first()
        price = rate.price_per_kwh if rate else 0

        day = reading.timestamp.date()
        daily_data[day]["kwh"] += reading.energy_kwh
        daily_data[day]["cost"] += reading.energy_kwh * price

        total_kwh += reading.energy_kwh
        total_cost += reading.energy_kwh * price

    daily_breakdown = [
        {
            "date": day.isoformat(),
            "kwh": round(data["kwh"], 2),
            "cost": round(data["cost"], 2),
            "co2_avoided_kg": round(data["kwh"] * EMISSIONS_FACTOR_KG_PER_KWH, 2)
        }
        for day, data in sorted(daily_data.items())
    ]

    return {
        "user_id": user_id,
        "start_date": start,
        "end_date": end,
        "total_kwh": round(total_kwh, 2),
        "total_cost": round(total_cost, 2),
        "co2_avoided_kg": round(total_kwh * EMISSIONS_FACTOR_KG_PER_KWH, 2),
        "daily_breakdown": daily_breakdown
    }



@router.get("/{user_id}/detailed_hourly")
def calculate_hourly_bill(user_id: int,
                          start: date, end: date,
                          db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    # Get all user's meters
    meters = db.query(SmartMeter).filter(SmartMeter.user_id == user_id).all()
    if not meters:
        raise HTTPException(status_code=404, detail="No smart meters found for this user")

    meter_ids = [m.id for m in meters]

    # Get all readings in the date range
    readings = db.query(SmartMeterReading).filter(
        SmartMeterReading.meter_id.in_(meter_ids),
        SmartMeterReading.timestamp >= start,
        SmartMeterReading.timestamp <= end
    ).all()

    if not readings:
        return {"user_id": user_id, "total_kwh": 0, "total_cost": 0, "daily_breakdown": [], "hourly_breakdown": []}

    daily_breakdown = {}
    hourly_breakdown = []
    total_kwh = 0
    total_cost = 0

    for reading in readings:
        # Hourly cost
        rate = db.query(Pricing).filter(
            Pricing.date == reading.timestamp.replace(minute=0, second=0, microsecond=0)
        ).first()
        price = rate.price_per_kwh if rate else 0
        cost = reading.energy_kwh * price

        total_kwh += reading.energy_kwh
        total_cost += cost

        # Daily aggregation
        day_str = reading.timestamp.date().isoformat()
        if day_str not in daily_breakdown:
            daily_breakdown[day_str] = {"kwh": 0, "cost": 0}
        daily_breakdown[day_str]["kwh"] += reading.energy_kwh
        daily_breakdown[day_str]["cost"] += cost

        # Hourly entry
        hourly_breakdown.append({
            "timestamp": reading.timestamp.isoformat(),
            "kwh": reading.energy_kwh,
            "cost": round(cost, 2)
        })

    # Convert daily breakdown to a sorted list
    daily_breakdown_list = [{"date": k, "kwh": v["kwh"], "cost": round(v["cost"], 2)}
                            for k, v in sorted(daily_breakdown.items())]

    return {
        "user_id": user_id,
        "start_date": start,
        "end_date": end,
        "total_kwh": total_kwh,
        "total_cost": round(total_cost, 2),
        "daily_breakdown": daily_breakdown_list,
        "hourly_breakdown": hourly_breakdown
    }