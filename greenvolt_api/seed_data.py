from datetime import datetime
from greenvolt_api.database import SessionLocal
from greenvolt_api.models import User, SmartMeter, Consumption, Pricing, EVChargingSession

def seed():
    db = SessionLocal()

    # # --- Clear existing data (optional, comment if you don’t want reset each time) ---
    # db.query(EVChargingSession).delete()
    # db.query(Consumption).delete()
    # db.query(Pricing).delete()
    # db.query(SmartMeter).delete()
    # db.query(User).delete()
    # db.commit()

    # --- Create a User ---
    user = User(name="Alice", email="alice@example.com", password="secure123")
    db.add(user)
    db.commit()
    db.refresh(user)

    # --- Create a Smart Meter ---
    meter = SmartMeter(serial_number="SM-001", location="Berlin", user_id=user.id)
    db.add(meter)
    db.commit()
    db.refresh(meter)

    # --- Add Consumption Data (2 hours) ---
    ts1 = datetime(2025, 8, 15, 10, 0, 0)
    ts2 = datetime(2025, 8, 15, 11, 0, 0)

    c1 = Consumption(user_id=user.id, smart_meter_id=meter.id, timestamp=ts1, energy_kwh=5.2)
    c2 = Consumption(user_id=user.id, smart_meter_id=meter.id, timestamp=ts2, energy_kwh=3.8)
    db.add_all([c1, c2])
    db.commit()

    # --- Add Pricing Data ---
    p1 = Pricing(date=ts1, price_per_kwh=0.25)
    p2 = Pricing(date=ts2, price_per_kwh=0.30)
    db.add_all([p1, p2])
    db.commit()

    # --- Add EV Charging Session ---
    ev = EVChargingSession(
        user_id=user.id,
        start_time=datetime(2025, 8, 15, 9, 0, 0),
        end_time=datetime(2025, 8, 15, 11, 0, 0),
        energy_kwh=12.5,
        cost=3.5
    )
    db.add(ev)
    db.commit()

    print("✅ Database seeded with test data!")

if __name__ == "__main__":
    seed()
