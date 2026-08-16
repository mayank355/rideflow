from pydantic import BaseModel


class DriverSignup(BaseModel):
    name: str
    phone_number: str
    password: str
    vehicle_number: str
    vehicle_type: str


class RiderSignup(BaseModel):
    name: str
    phone_number: str
    password: str


class LoginRequest(BaseModel):
    phone_number: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
