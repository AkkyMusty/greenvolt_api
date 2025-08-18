from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, func
from sqlalchemy.orm import Session, declarative_base, sessionmaker, relationship
from sqlalchemy import create_engine
from datetime import datetime, date, timedelta
from typing import Optional
from typing import List
from collections import defaultdict
from jose import JWTError, jwt
from passlib.context import CryptContext



CO2_FACTOR = 0.475  # kg CO₂ per kWh avoided (example value, adjust if needed)




# Database setup
DATABASE_URL = "sqlite:///./greenvolt.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ---------------------------
# JWT Settings (DEV only)
# ---------------------------
# Secret key for signing JWT
SECRET_KEY = "supersecretkey123"  # ⚠️ change in production
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# Helper functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

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

class Pricing(Base):
    __tablename__ = "pricing"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, index=True)  # Date + Hour
    price_per_kwh = Column(Float)        # Price in currency per kWh

class EVChargingSession(Base):
    __tablename__ = "ev_charging_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    energy_kwh = Column(Float, nullable=False)
    cost = Column(Float, nullable=True)  # Optional: store calculated cost

    owner = relationship("User")


class SmartMeterData(Base):
    __tablename__ = "smart_meter_data"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    consumption_kwh = Column(Float)

    user = relationship("User")

class Consumption(Base):
    __tablename__ = "consumptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    smart_meter_id = Column(Integer, ForeignKey("smartmeters.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    energy_kwh = Column(Float)

    # Relationships
    user = relationship("User", backref="consumptions")
    smart_meter = relationship("SmartMeter", backref="consumptions")



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

class PricingCreate(BaseModel):
    date: datetime
    price_per_kwh: float

class EVChargingCreate(BaseModel):
    user_id: int
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    energy_kwh: float

class BillingLineItem(BaseModel):
    meter_id: int
    timestamp: datetime
    energy_kwh: float
    price_per_kwh: float
    cost: float

class BillingBreakdown(BaseModel):
    user_id: int
    start: datetime
    end: datetime
    total_kwh: float
    total_cost: float
    missing_rate_hours: int
    items: list[BillingLineItem]

class SmartMeterDataCreate(BaseModel):
    user_id: int
    timestamp: datetime
    consumption_kwh: float

class BulkPricingCreate(BaseModel):
    date: datetime  # The exact hour
    price_per_kwh: float


class ConsumptionCreate(BaseModel):
    user_id: int
    smart_meter_id: int
    timestamp: datetime
    energy_kwh: float


class ConsumptionOut(BaseModel):
    id: int
    user_id: int
    smart_meter_id: int
    timestamp: datetime
    energy_kwh: float

    class Config:
        orm_mode = True




# ---------------------------
# Routes
# ---------------------------
@app.get("/")
def read_root():
    return {"message": "Hello from GreenVolt API"}


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=401, detail="Could not validate credentials"
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    return user

# def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> User:
#     credentials_exception = HTTPException(
#         status_code=401,
#         detail="Could not validate credentials",
#         headers={"WWW-Authenticate": "Bearer"},
#     )
#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         sub = payload.get("sub")
#         if sub is None:
#             raise credentials_exception
#         user_id = int(sub)
#     except (JWTError, ValueError):
#         raise credentials_exception
#
#     user = db.query(User).filter(User.id == user_id).first()
#     if not user:
#         raise credentials_exception
#     return user


# ---------------------------
# User Management - Read/Update/Delete
# ---------------------------

# @app.post("/users/")
# def create_user(user: UserCreate, db: Session = Depends(get_db)):
#     existing_user = db.query(User).filter(User.email == user.email).first()
#     if existing_user:
#         raise HTTPException(status_code=400, detail="Email already registered")
#
#     new_user = User(name=user.name, email=user.email, password=user.password)
#     db.add(new_user)
#     db.commit()
#     db.refresh(new_user)
#
#     return {"id": new_user.id, "name": new_user.name, "email": new_user.email}

@app.post("/users/")
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_pw = get_password_hash(user.password)
    new_user = User(name=user.name, email=user.email, password=hashed_pw)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"id": new_user.id, "name": new_user.name, "email": new_user.email}


# @app.post("/login")
# def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
#     """
#     OAuth2PasswordRequestForm expects form fields:
#       - username (we'll use this as email)
#       - password
#     """
#     user = db.query(User).filter(User.email == form_data.username).first()
#     if not user or user.password != form_data.password:  # DEV: plaintext check
#         raise HTTPException(status_code=401, detail="Invalid email or password")
#
#     access_token = create_access_token(data={"sub": str(user.id)})
#     return {"access_token": access_token, "token_type": "bearer"}

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": str(user.id)}, expires_delta=access_token_expires)

    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/users/{user_id}")
def get_user(user_id: int,
             db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email
    }

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None

@app.put("/users/{user_id}")
def update_user(user_id: int, user_update: UserUpdate,
                db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user_update.name:
        user.name = user_update.name
    if user_update.email:
        existing_email = db.query(User).filter(User.email == user_update.email, User.id != user_id).first()
        if existing_email:
            raise HTTPException(status_code=400, detail="Email already in use")
        user.email = user_update.email
    if user_update.password:
        user.password = user_update.password

    db.commit()
    db.refresh(user)
    return {"message": "User updated", "user": {"id": user.id, "name": user.name, "email": user.email}}

@app.delete("/users/{user_id}")
def delete_user(user_id: int,
                db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user)
    db.commit()
    return {"message": f"User {user_id} deleted successfully"}


@app.post("/smartmeters/")
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

@app.get("/smartmeters/{user_id}")
def get_user_smart_meters(user_id: int,
                          db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    meters = db.query(SmartMeter).filter(SmartMeter.user_id == user_id).all()
    return meters


@app.post("/readings/")
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


@app.get("/readings/{meter_id}")
def get_meter_readings(meter_id: int,
                       db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    meter = db.query(SmartMeter).filter(SmartMeter.id == meter_id).first()
    if not meter:
        raise HTTPException(status_code=404, detail="Smart meter not found")

    readings = db.query(SmartMeterReading).filter(SmartMeterReading.meter_id == meter_id).all()
    return readings


@app.get("/readings/{meter_id}/daily")
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

@app.get("/readings/{meter_id}/monthly")
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



@app.post("/pricing/")
def set_pricing(pricing: PricingCreate,
                db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    existing_rate = db.query(Pricing).filter(Pricing.date == pricing.date).first()

    if existing_rate:
        existing_rate.price_per_kwh = pricing.price_per_kwh
        db.commit()
        db.refresh(existing_rate)
        return {"message": "Rate updated", "id": existing_rate.id, "price_per_kwh": existing_rate.price_per_kwh}

    new_rate = Pricing(date=pricing.date, price_per_kwh=pricing.price_per_kwh)
    db.add(new_rate)
    db.commit()
    db.refresh(new_rate)
    return {"message": "Rate added", "id": new_rate.id, "price_per_kwh": new_rate.price_per_kwh}


@app.get("/billing/{user_id}")
def calculate_bill(user_id: int,
                   start: date, end: date,
                   db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    # Get all user's meters
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
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
        return {"user_id": user_id, "total_kwh": 0, "total_cost": 0}

    total_kwh = 0
    total_cost = 0

    for reading in readings:
        # Find the pricing for the exact hour of this reading
        rate = db.query(Pricing).filter(Pricing.date == reading.timestamp.replace(minute=0, second=0, microsecond=0)).first()
        price = rate.price_per_kwh if rate else 0
        total_kwh += reading.energy_kwh
        total_cost += reading.energy_kwh * price

    return {
        "user_id": user_id,
        "start_date": start,
        "end_date": end,
        "total_kwh": total_kwh,
        "total_cost": total_cost
    }

def hour_floor(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)

def get_rate_for_hour(db: Session, dt: datetime) -> float:
    """Return price for the hour starting at dt (floored to the hour). Missing rate -> 0."""
    hour = hour_floor(dt)
    rate = db.query(Pricing).filter(Pricing.date == hour).first()
    return rate.price_per_kwh if rate else 0.0


# ---------------------------
# EV Charging Endpoints
# ---------------------------
# @app.post("/ev-charging/")
# def create_ev_charging_session(session: EVChargingCreate, db: Session = Depends(get_db)):
#     user = db.query(User).filter(User.id == session.user_id).first()
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")
#
#     # Assume price per kWh is 0.25 (can be changed later)
#     price_per_kwh = 0.25
#     cost = round(session.energy_kwh * price_per_kwh, 2)
#
#     new_session = EVChargingSession(
#         user_id=session.user_id,
#         start_time=session.start_time or datetime.utcnow(),
#         end_time=session.end_time,
#         energy_kwh=session.energy_kwh,
#         cost=cost
#     )
#
#     db.add(new_session)
#     db.commit()
#     db.refresh(new_session)
#
#     return {
#         "id": new_session.id,
#         "user_id": new_session.user_id,
#         "start_time": new_session.start_time,
#         "end_time": new_session.end_time,
#         "energy_kwh": new_session.energy_kwh,
#         "cost": new_session.cost
#     }

@app.post("/ev-charging/")
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


@app.get("/ev-charging/{user_id}")
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


@app.get("/ev-charging/{user_id}/monthly-summary")
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



# @app.get("/billing/{user_id}/breakdown", response_model=BillingBreakdown)
# def billing_breakdown(
#     user_id: int,
#     start: datetime = Query(..., description="ISO timestamp, e.g. 2025-08-13T00:00:00"),
#     end: datetime = Query(..., description="ISO timestamp, e.g. 2025-08-14T00:00:00"),
#     db: Session = Depends(get_db),
# ):
#     meters = db.query(SmartMeter).filter(SmartMeter.user_id == user_id).all()
#     if not meters:
#         raise HTTPException(status_code=404, detail="No smart meters found for this user")
#
#     meter_ids = [m.id for m in meters]
#
#     readings = db.query(SmartMeterReading).filter(
#         SmartMeterReading.meter_id.in_(meter_ids),
#         SmartMeterReading.timestamp >= start,
#         SmartMeterReading.timestamp < end
#     ).order_by(SmartMeterReading.timestamp.asc()).all()
#
#     items: list[BillingLineItem] = []
#     total_kwh = 0.0
#     total_cost = 0.0
#     missing_rate_hours = 0
#
#     for r in readings:
#         hour_ts = hour_floor(r.timestamp)
#         price = get_rate_for_hour(db, hour_ts)
#         if price == 0.0:
#             missing_rate_hours += 1
#         cost = round(r.energy_kwh * price, 6)
#         total_kwh += r.energy_kwh
#         total_cost += cost
#         items.append(BillingLineItem(
#             meter_id=r.meter_id,
#             timestamp=hour_ts,
#             energy_kwh=r.energy_kwh,
#             price_per_kwh=price,
#             cost=cost
#         ))
#
#     return BillingBreakdown(
#         user_id=user_id,
#         start=start,
#         end=end,
#         total_kwh=round(total_kwh, 6),
#         total_cost=round(total_cost, 6),
#         missing_rate_hours=missing_rate_hours,
#         items=items
#     )

@app.post("/smartmeters/data")
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


@app.get("/smartmeters/{user_id}/consumption")
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

@app.post("/pricing/bulk/")
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

# @app.get("/billing/{user_id}")
# def calculate_bill(user_id: int, start: datetime, end: datetime, db: Session = Depends(get_db)):
#     # Get all user's meters
#     meters = db.query(SmartMeter).filter(SmartMeter.user_id == user_id).all()
#     if not meters:
#         raise HTTPException(status_code=404, detail="No smart meters found for this user")
#
#     meter_ids = [m.id for m in meters]
#
#     # Get all readings in the date range
#     readings = db.query(SmartMeterReading).filter(
#         SmartMeterReading.meter_id.in_(meter_ids),
#         SmartMeterReading.timestamp >= start,
#         SmartMeterReading.timestamp <= end
#     ).all()
#
#     if not readings:
#         return {"user_id": user_id, "total_kwh": 0, "total_cost": 0}
#
#     total_kwh = 0
#     total_cost = 0
#
#     for reading in readings:
#         # Round timestamp to the hour to match pricing
#         hour_timestamp = reading.timestamp.replace(minute=0, second=0, microsecond=0)
#         rate = db.query(Pricing).filter(Pricing.date == hour_timestamp).first()
#         price = rate.price_per_kwh if rate else 0  # fallback to 0 if no pricing set
#
#         total_kwh += reading.energy_kwh
#         total_cost += reading.energy_kwh * price
#
#     return {
#         "user_id": user_id,
#         "start_date": start,
#         "end_date": end,
#         "total_kwh": round(total_kwh, 2),
#         "total_cost": round(total_cost, 2)
#     }


# @app.get("/billing/{user_id}")
# def calculate_bill(
#     user_id: int,
#     start: date,
#     end: date,
#     db: Session = Depends(get_db)
# ):
#     # Get all user's meters
#     meters = db.query(SmartMeter).filter(SmartMeter.user_id == user_id).all()
#     if not meters:
#         raise HTTPException(status_code=404, detail="No smart meters found for this user")
#
#     meter_ids = [m.id for m in meters]
#
#     # Get all readings in the date range
#     readings = db.query(SmartMeterReading).filter(
#         SmartMeterReading.meter_id.in_(meter_ids),
#         SmartMeterReading.timestamp >= start,
#         SmartMeterReading.timestamp <= end
#     ).all()
#
#     if not readings:
#         return {
#             "user_id": user_id,
#             "total_kwh": 0,
#             "total_cost": 0,
#             "co2_avoided_kg": 0
#         }
#
#     total_kwh = 0
#     total_cost = 0
#
#     for reading in readings:
#         # Find the pricing for the exact hour of this reading
#         rate = db.query(Pricing).filter(
#             Pricing.date == reading.timestamp.replace(minute=0, second=0, microsecond=0)
#         ).first()
#         price = rate.price_per_kwh if rate else 0
#         total_kwh += reading.energy_kwh
#         total_cost += reading.energy_kwh * price
#
#     # --- CO₂ Offset Analytics ---
#     # Example: Assume grid emissions factor = 0.4 kg CO₂/kWh
#     # This can be replaced with your local factor or stored in a config/db table.
#     EMISSIONS_FACTOR_KG_PER_KWH = 0.4
#     co2_avoided_kg = round(total_kwh * EMISSIONS_FACTOR_KG_PER_KWH, 2)
#
#     return {
#         "user_id": user_id,
#         "start_date": start,
#         "end_date": end,
#         "total_kwh": round(total_kwh, 2),
#         "total_cost": round(total_cost, 2),
#         "co2_avoided_kg": co2_avoided_kg
#     }



@app.get("/billing/{user_id}")
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



@app.get("/billing/{user_id}/detailed_hourly")
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

# @app.get("/analytics/{user_id}")
# def get_user_analytics(user_id: int, start: date, end: date, db: Session = Depends(get_db)):
#     user = db.query(User).filter(User.id == user_id).first()
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")
#
#     # Household consumption (smart meter readings)
#     meter_ids = [m.id for m in user.smart_meters]
#     household_kwh = db.query(func.sum(SmartMeterReading.energy_kwh)).filter(
#         SmartMeterReading.meter_id.in_(meter_ids),
#         SmartMeterReading.timestamp >= start,
#         SmartMeterReading.timestamp <= end
#     ).scalar() or 0
#
#     # EV consumption
#     ev_kwh = db.query(func.sum(EVChargingSession.energy_kwh)).filter(
#         EVChargingSession.user_id == user_id,
#         EVChargingSession.start_time >= start,
#         EVChargingSession.start_time <= end
#     ).scalar() or 0
#
#     # Totals
#     total_kwh = household_kwh + ev_kwh
#     co2_offset = round(total_kwh * CO2_FACTOR, 2)
#
#     return {
#         "user_id": user_id,
#         "start_date": start,
#         "end_date": end,
#         "household_kwh": round(household_kwh, 2),
#         "ev_kwh": round(ev_kwh, 2),
#         "total_kwh": round(total_kwh, 2),
#         "co2_offset_kg": co2_offset
#     }

@app.get("/analytics/{user_id}")
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


@app.post("/consumptions/", response_model=ConsumptionOut)
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


@app.get("/consumptions/{user_id}", response_model=List[ConsumptionOut])
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


@app.post("/consumptions/bulk/")
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
