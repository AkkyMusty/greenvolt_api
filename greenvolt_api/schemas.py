from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None

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


