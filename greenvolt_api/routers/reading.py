from fastapi import APIRouter, Depends
from main import SessionLocal, EVChargingSession
from datetime import datetime

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/")
def create_reading(reading: ReadingCreate,
                   db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    meter = db.query(SmartMeter).filter(SmartMeter.id == reading.meter_id).first()
    if not meter:
        raise HTTPException(status_code=404, detail="Smart meter not found")

    new_reading = SmartMeterReading(
        meter_id=reading.meter_id,
        energy_kwh=reading.energy_kwh,
        timestamp=reading.timestamp or datetime.utcnow()
    )

    db.add(new_reading)
    db.commit()
    db.refresh(new_reading)

    return {
        "id": new_reading.id,
        "meter_id": new_reading.meter_id,
        "energy_kwh": new_reading.energy_kwh,
        "timestamp": new_reading.timestamp
    }


@router.get("/{meter_id}")
def get_meter_readings(meter_id: int,
                       db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    meter = db.query(SmartMeter).filter(SmartMeter.id == meter_id).first()
    if not meter:
        raise HTTPException(status_code=404, detail="Smart meter not found")

    readings = db.query(SmartMeterReading).filter(SmartMeterReading.meter_id == meter_id).all()
    return readings


@router.get("/{meter_id}/daily")
def get_daily_energy(meter_id: int,
                     db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    """Get total energy (kWh) for today."""
    meter = db.query(SmartMeter).filter(SmartMeter.id == meter_id).first()
    if not meter:
        raise HTTPException(status_code=404, detail="Smart meter not found")

    today = date.today()
    total_kwh = db.query(func.sum(SmartMeterReading.energy_kwh)).filter(
        SmartMeterReading.meter_id == meter_id,
        func.date(SmartMeterReading.timestamp) == today
    ).scalar()

    return {
        "meter_id": meter_id,
        "date": today,
        "total_kwh": total_kwh or 0
    }

@router.get("/{meter_id}/monthly")
def get_monthly_energy(meter_id: int,
                       db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    """Get total energy (kWh) for the current month."""
    meter = db.query(SmartMeter).filter(SmartMeter.id == meter_id).first()
    if not meter:
        raise HTTPException(status_code=404, detail="Smart meter not found")

    today = date.today()
    first_of_month = date(today.year, today.month, 1)

    total_kwh = db.query(func.sum(SmartMeterReading.energy_kwh)).filter(
        SmartMeterReading.meter_id == meter_id,
        SmartMeterReading.timestamp >= first_of_month,
        SmartMeterReading.timestamp <= today
    ).scalar()

    return {
        "meter_id": meter_id,
        "month": today.strftime("%Y-%m"),
        "total_kwh": total_kwh or 0
    }
