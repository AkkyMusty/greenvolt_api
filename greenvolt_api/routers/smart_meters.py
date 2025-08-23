from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from greenvolt_api.main import SessionLocal
from greenvolt_api.models import SmartMeter, User, SmartMeterData
from greenvolt_api.schemas import SmartMeterCreate, SmartMeterDataCreate
from users import get_current_user
from sqlalchemy.orm import Session

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/")
def create_smart_meter(smart_meter: SmartMeterCreate,
                       db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    user = db.query(User).filter(User.id == smart_meter.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    new_meter = SmartMeter(
        serial_number=smart_meter.serial_number,
        location=smart_meter.location,
        user_id=smart_meter.user_id
    )
    db.add(new_meter)
    db.commit()
    db.refresh(new_meter)

    return {"id": new_meter.id, "serial_number": new_meter.serial_number, "location": new_meter.location}

@router.get("/smartmeters/{user_id}")
def get_user_smart_meters(user_id: int,
                          db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    meters = db.query(SmartMeter).filter(SmartMeter.user_id == user_id).all()
    return meters

@router.post("/data")
def upload_smart_meter_data(data: SmartMeterDataCreate,
                            db: Session = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    # Check user exists
    user = db.query(User).filter(User.id == data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Create new record
    new_record = SmartMeterData(
        user_id=data.user_id,
        timestamp=data.timestamp,
        consumption_kwh=data.consumption_kwh
    )
    db.add(new_record)
    db.commit()
    db.refresh(new_record)

    return {
        "id": new_record.id,
        "user_id": new_record.user_id,
        "timestamp": new_record.timestamp,
        "consumption_kwh": new_record.consumption_kwh
    }


@router.get("/{user_id}/consumption")
def get_smart_meter_consumption(user_id: int,
                                start_date: str,
                                end_date: str,
                                db: Session = Depends(get_db),
                                current_user: User = Depends(get_current_user)):
    """
    Retrieve smart meter consumption data for a user within a date range.
    start_date and end_date format: YYYY-MM-DD
    """
    # Validate dates
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    # Check user exists
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Fetch data
    records = db.query(SmartMeterData).filter(
        SmartMeterData.user_id == user_id,
        SmartMeterData.timestamp >= start_dt,
        SmartMeterData.timestamp <= end_dt
    ).all()

    return {
        "user_id": user_id,
        "start_date": start_date,
        "end_date": end_date,
        "records": [
            {"timestamp": r.timestamp, "consumption_kwh": r.consumption_kwh}
            for r in records
        ]
    }

