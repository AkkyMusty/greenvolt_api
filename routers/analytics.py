from datetime import datetime, date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func

from greenvolt_api.database import get_db
from greenvolt_api.models import User, Pricing, SmartMeterReading, EVChargingSession
from routers.users import get_current_user
from sqlalchemy.orm import Session

router = APIRouter()

CO2_FACTOR = 0.475


def load_pricing_map(db: Session, start: date, end: date) -> dict[datetime, float]:
    """Return {hour_start_datetime -> price_per_kwh} for the date range."""
    # widen to cover the whole last day
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt   = datetime.combine(end,   datetime.max.time())
    rates = db.query(Pricing).filter(
        Pricing.date >= start_dt,
        Pricing.date <= end_dt
    ).all()
    return {r.date.replace(minute=0, second=0, microsecond=0): r.price_per_kwh for r in rates}



@router.get("/{user_id}")
def analytics_summary(
    user_id: int,
    start: date,
    end: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    meter_ids = [m.id for m in user.smart_meters]
    # No meters? Return zeros but still show the period.
    if not meter_ids:
        return {
            "user_id": user_id,
            "start_date": start,
            "end_date": end,
            "household_kwh": 0.0,
            "ev_kwh": 0.0,
            "total_kwh": 0.0,
            "total_cost": 0.0,
            "average_daily_kwh": 0.0,
            "peak_usage_hour": None,
            "co2_offset_kg": 0.0
        }

    # Readings in range
    readings = db.query(SmartMeterReading).filter(
        SmartMeterReading.meter_id.in_(meter_ids),
        SmartMeterReading.timestamp >= datetime.combine(start, datetime.min.time()),
        SmartMeterReading.timestamp <= datetime.combine(end,   datetime.max.time())
    ).all()

    # EV kWh in range (simple inclusion by start_time)
    ev_kwh = db.query(func.sum(EVChargingSession.energy_kwh)).filter(
        EVChargingSession.user_id == user_id,
        EVChargingSession.start_time >= datetime.combine(start, datetime.min.time()),
        EVChargingSession.start_time <= datetime.combine(end,   datetime.max.time())
    ).scalar() or 0.0

    # Pricing map for cost calc
    pricing_map = load_pricing_map(db, start, end)

    total_kwh = 0.0
    total_cost = 0.0
    hourly_bins = [0.0] * 24  # accumulate household kWh by hour-of-day

    for r in readings:
        hour_ts = r.timestamp.replace(minute=0, second=0, microsecond=0)
        price = pricing_map.get(hour_ts, 0.0)
        total_kwh += r.energy_kwh
        total_cost += r.energy_kwh * price
        hourly_bins[r.timestamp.hour] += r.energy_kwh

    total_kwh_combined = total_kwh + ev_kwh

    # Averages & peak
    num_days = (end - start).days + 1
    avg_daily = round(total_kwh_combined / num_days, 2) if num_days > 0 else 0.0
    peak_hour = int(max(range(24), key=lambda h: hourly_bins[h])) if any(hourly_bins) else None

    return {
        "user_id": user_id,
        "start_date": start,
        "end_date": end,
        "household_kwh": round(total_kwh, 2),
        "ev_kwh": round(ev_kwh, 2),
        "total_kwh": round(total_kwh_combined, 2),
        "total_cost": round(total_cost, 2),
        "average_daily_kwh": avg_daily,
        "peak_usage_hour": peak_hour,
        "co2_offset_kg": round(total_kwh_combined * CO2_FACTOR, 2),
        # Optional: include the hourly profile if you want to chart it on the frontend
        "hourly_profile": [{"hour": h, "kwh": round(k, 3)} for h, k in enumerate(hourly_bins)]
    }