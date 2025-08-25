from datetime import datetime, timedelta, date
from greenvolt_api.schemas import EVChargingCreate
from sqlalchemy.orm import Session
from greenvolt_api.models import User, Pricing, EVChargingSession
from greenvolt_api.database import get_db
from routers.users import get_current_user
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()


def hour_floor(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)

def get_rate_for_hour(db: Session, dt: datetime) -> float:
    """Return price for the hour starting at dt (floored to the hour). Missing rate -> 0."""
    hour = hour_floor(dt)
    rate = db.query(Pricing).filter(Pricing.date == hour).first()
    return rate.price_per_kwh if rate else 0.0



@router.post("/")
def create_ev_charging_session(session: EVChargingCreate,
                               db: Session = Depends(get_db),
                               current_user: User = Depends(get_current_user)):
    user = db.query(User).filter(User.id == session.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    start_time = session.start_time or datetime.utcnow()
    # If no end_time, assume 1-hour session for pricing; you can change this rule if you prefer.
    end_time = session.end_time or (start_time + timedelta(hours=1))
    if end_time <= start_time:
        raise HTTPException(status_code=400, detail="end_time must be after start_time")

    # Distribute energy evenly over the session duration across hour buckets
    duration_sec = (end_time - start_time).total_seconds()
    energy_total = session.energy_kwh
    cost_total = 0.0

    # Iterate hour by hour over the interval
    cursor = hour_floor(start_time)
    # Ensure cursor starts at the beginning of the hour that includes start_time
    if cursor < start_time:
        cursor = cursor
    else:
        cursor = hour_floor(start_time)

    while cursor < end_time:
        next_hour = cursor + timedelta(hours=1)
        # Portion of the session overlapping this hour
        seg_start = max(cursor, start_time)
        seg_end = min(next_hour, end_time)
        seg_sec = max(0.0, (seg_end - seg_start).total_seconds())
        if seg_sec > 0 and duration_sec > 0:
            seg_energy = energy_total * (seg_sec / duration_sec)
            price = get_rate_for_hour(db, cursor)  # price for this hour
            cost_total += seg_energy * price
        cursor = next_hour

    new_session = EVChargingSession(
        user_id=session.user_id,
        start_time=start_time,
        end_time=session.end_time,  # keep None if not provided
        energy_kwh=energy_total,
        cost=round(cost_total, 6)
    )

    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    return {
        "id": new_session.id,
        "user_id": new_session.user_id,
        "start_time": new_session.start_time,
        "end_time": new_session.end_time,
        "energy_kwh": new_session.energy_kwh,
        "cost": new_session.cost
    }


@router.get("/{user_id}")
def get_ev_charging_sessions(user_id: int,
                             db: Session = Depends(get_db),
                             current_user: User = Depends(get_current_user)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    sessions = db.query(EVChargingSession).filter(EVChargingSession.user_id == user_id).all()
    return [
        {
            "id": s.id,
            "start_time": s.start_time,
            "end_time": s.end_time,
            "energy_kwh": s.energy_kwh,
            "cost": s.cost
        }
        for s in sessions
    ]


@router.get("/{user_id}/monthly-summary")
def get_monthly_ev_summary(user_id: int,
                           db: Session = Depends(get_db),
                           current_user: User = Depends(get_current_user)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    today = date.today()
    # Start of month
    first_of_month = datetime(today.year, today.month, 1)
    # Start of next month
    if today.month == 12:
        first_of_next_month = datetime(today.year + 1, 1, 1)
    else:
        first_of_next_month = datetime(today.year, today.month + 1, 1)

    sessions = db.query(EVChargingSession).filter(
        EVChargingSession.user_id == user_id,
        EVChargingSession.start_time >= first_of_month,
        EVChargingSession.start_time < first_of_next_month
    ).all()

    total_energy = 0
    total_cost = 0

    now = datetime.utcnow()
    for s in sessions:
        # Use end_time or now if session is ongoing
        end_time = s.end_time or now
        total_energy += s.energy_kwh
        total_cost += s.cost

    return {
        "user_id": user_id,
        "month": today.strftime("%Y-%m"),
        "total_energy_kwh": round(total_energy, 2),
        "total_cost": round(total_cost, 2)
    }

