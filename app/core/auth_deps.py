from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from jose import JWTError

from app.database import get_db
from app.models.driver import Driver
from app.models.rider import Rider
from app.core.security import decode_access_token

# HTTPBearer gives Swagger a simple "paste your token" box (just the
# raw token string, no "Bearer " prefix needed in the box itself —
# Swagger adds that automatically), instead of a full OAuth2
# username/password login form we don't actually implement that way.
security_scheme = HTTPBearer()


def _decode_or_401(credentials: HTTPAuthorizationCredentials) -> dict:
    token = credentials.credentials
    try:
        return decode_access_token(token)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


def get_current_driver(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> Driver:
    payload = _decode_or_401(credentials)
    if payload.get("role") != "driver":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Driver token required")
    driver = db.query(Driver).filter(Driver.id == payload["sub"]).first()
    if not driver:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Driver not found")
    return driver


def get_current_rider(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> Rider:
    payload = _decode_or_401(credentials)
    if payload.get("role") != "rider":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rider token required")
    rider = db.query(Rider).filter(Rider.id == payload["sub"]).first()
    if not rider:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Rider not found")
    return rider


def get_current_principal(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: Session = Depends(get_db),
):
    """
    For endpoints usable by EITHER role. Returns (role, user_object) —
    the endpoint itself decides what's authorized to do what, using
    _require_trip_participant.
    """
    payload = _decode_or_401(credentials)
    role = payload.get("role")
    if role == "driver":
        driver = db.query(Driver).filter(Driver.id == payload["sub"]).first()
        if not driver:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Driver not found")
        return "driver", driver
    elif role == "rider":
        rider = db.query(Rider).filter(Rider.id == payload["sub"]).first()
        if not rider:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Rider not found")
        return "rider", rider
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token role")
