from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

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
