# from sqlalchemy.orm import Session
# from models import User, SmartMeter, Consumption, Pricing, EVChargingSession
# from fastapi import Depends, HTTPException
# from schemas import UserCreate
# # USER
# def create_user(user: UserCreate, db: Session = Depends(get_db)):
#     existing_user = db.query(User).filter(User.email == user.email).first()
#     if existing_user:
#         raise HTTPException(status_code=400, detail="Email already registered")
#
#     hashed_pw = get_password_hash(user.password)
#     new_user = User(name=user.name, email=user.email, password=hashed_pw)
#     db.add(new_user)
#     db.commit()
#     db.refresh(new_user)
#
#     return {"id": new_user.id, "name": new_user.name, "email": new_user.email}
#
#
# def get_user(user_id: int,
#              db: Session = Depends(get_db),
#              current_user: User = Depends(get_current_user)):
#     user = db.query(User).filter(User.id == user_id).first()
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")
#     return {
#         "id": user.id,
#         "name": user.name,
#         "email": user.email
#     }
#
# def update_user(user_id: int, user_update: UserUpdate,
#                 db: Session = Depends(get_db),
#                 current_user: User = Depends(get_current_user)):
#     user = db.query(User).filter(User.id == user_id).first()
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")
#
#     if user_update.name:
#         user.name = user_update.name
#     if user_update.email:
#         existing_email = db.query(User).filter(User.email == user_update.email, User.id != user_id).first()
#         if existing_email:
#             raise HTTPException(status_code=400, detail="Email already in use")
#         user.email = user_update.email
#     if user_update.password:
#         user.password = user_update.password
#
#     db.commit()
#     db.refresh(user)
#     return {"message": "User updated", "user": {"id": user.id, "name": user.name, "email": user.email}}
#
#
# def delete_user(user_id: int,
#                 db: Session = Depends(get_db),
#                 current_user: User = Depends(get_current_user)):
#     user = db.query(User).filter(User.id == user_id).first()
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")
#
#     db.delete(user)
#     db.commit()
#     return {"message": f"User {user_id} deleted successfully"}
#
#
# # SMART METER
# def create_smart_meter(smart_meter: SmartMeterCreate,
#                        db: Session = Depends(get_db),
#                        current_user: User = Depends(get_current_user)):
#     user = db.query(User).filter(User.id == smart_meter.user_id).first()
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")
#
#     new_meter = SmartMeter(
#         serial_number=smart_meter.serial_number,
#         location=smart_meter.location,
#         user_id=smart_meter.user_id
#     )
#     db.add(new_meter)
#     db.commit()
#     db.refresh(new_meter)
#
#     return {"id": new_meter.id, "serial_number": new_meter.serial_number, "location": new_meter.location}