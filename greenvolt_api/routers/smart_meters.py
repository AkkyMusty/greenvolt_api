from fastapi import APIRouter, Depends, HTTPException
from greenvolt_api.main import SessionLocal
from greenvolt_api.models import SmartMeter, User
from greenvolt_api.schemas import SmartMeterCreate
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

