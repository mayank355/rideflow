import os
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import jwt, JWTError

# bcrypt: industry-standard, deliberately slow hashing to resist brute
# force. Never store or compare plain-text passwords, ever.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-only-fallback-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str, role: str) -> str:
    """
    subject = the user's id (driver or rider). role = "driver" or "rider"
    — needed because a driver's id and a rider's id could theoretically
    collide in principle (different tables, different UUID spaces in
    practice, but the role claim removes any ambiguity about which type
    of user this token represents).
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Raises JWTError if the token is invalid, tampered with, or expired.
    The caller (auth dependency) is responsible for converting that into
    a 401 HTTP response.
    """
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
