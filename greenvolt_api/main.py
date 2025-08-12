from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, func
from sqlalchemy.orm import Session, declarative_base, sessionmaker, relationship
from sqlalchemy import create_engine
from datetime import datetime, date
from typing import Optional


# Database setup
DATABASE_URL = "sqlite:///./greenvolt.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ---------------------------
# Database Models
# ---------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    password = Column(String)
    smart_meters = relationship("SmartMeter", back_populates="owner")


class SmartMeter(Base):
    __tablename__ = "smart_meters"

    id = Column(Integer, primary_key=True, index=True)
    serial_number = Column(String, unique=True, index=True)
    location = Column(String)
    installation_date = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="smart_meters")
    readings = relationship("SmartMeterReading", back_populates="meter")


class SmartMeterReading(Base):
    __tablename__ = "smart_meter_readings"

    id = Column(Integer, primary_key=True, index=True)
    meter_id = Column(Integer, ForeignKey("smart_meters.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    energy_kwh = Column(Float)  # Energy consumed/generated in kWh

    meter = relationship("SmartMeter", back_populates="readings")


Base.metadata.create_all(bind=engine)

app = FastAPI()

print("MAIN.PY is being loaded")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------------------------
# Pydantic Models
# ---------------------------
class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str

class SmartMeterCreate(BaseModel):
    serial_number: str
    location: str
    user_id: int

# class SmartMeterReadingCreate(BaseModel):
#     meter_id: int
#     energy_kwh: float

class ReadingCreate(BaseModel):
    meter_id: int
    energy_kwh: float
    timestamp: Optional[datetime] = None  # Optional custom timestamp


# ---------------------------
# Routes
# ---------------------------
@app.get("/")
def read_root():
    return {"message": "Hello from GreenVolt API"}

@app.post("/users/")
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(name=user.name, email=user.email, password=user.password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"id": new_user.id, "name": new_user.name, "email": new_user.email}

@app.post("/smartmeters/")
def create_smart_meter(smart_meter: SmartMeterCreate, db: Session = Depends(get_db)):
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

@app.get("/smartmeters/{user_id}")
def get_user_smart_meters(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    meters = db.query(SmartMeter).filter(SmartMeter.user_id == user_id).all()
    return meters

@app.post("/readings/")
# def create_reading(reading: SmartMeterReadingCreate, db: Session = Depends(get_db)):
#     meter = db.query(SmartMeter).filter(SmartMeter.id == reading.meter_id).first()
#     if not meter:
#         raise HTTPException(status_code=404, detail="Smart meter not found")
#
#     new_reading = SmartMeterReading(
#         meter_id=reading.meter_id,
#         energy_kwh=reading.energy_kwh
#     )
#     db.add(new_reading)
#     db.commit()
#     db.refresh(new_reading)
#
#     return {
#         "id": new_reading.id,
#         "meter_id": new_reading.meter_id,
#         "timestamp": new_reading.timestamp,
#         "energy_kwh": new_reading.energy_kwh
#     }
@app.post("/readings/")
def create_reading(reading: ReadingCreate, db: Session = Depends(get_db)):
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


@app.get("/readings/{meter_id}")
def get_meter_readings(meter_id: int, db: Session = Depends(get_db)):
    meter = db.query(SmartMeter).filter(SmartMeter.id == meter_id).first()
    if not meter:
        raise HTTPException(status_code=404, detail="Smart meter not found")

    readings = db.query(SmartMeterReading).filter(SmartMeterReading.meter_id == meter_id).all()
    return readings


@app.get("/readings/{meter_id}/daily")
def get_daily_energy(meter_id: int, db: Session = Depends(get_db)):
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

@app.get("/readings/{meter_id}/monthly")
def get_monthly_energy(meter_id: int, db: Session = Depends(get_db)):
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

