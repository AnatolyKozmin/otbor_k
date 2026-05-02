from datetime import datetime
from typing import List
from pydantic import BaseModel, EmailStr, field_validator
from app.models import Role

FACULTIES = ["НАБ", "ФЭБ", "ВШУ", "ИТиАБД", "СНиМК", "МЭО", "Финфак", "Юрфак"]


class UserBase(BaseModel):
    email: EmailStr
    name: str
    role: Role


class UserCreate(UserBase):
    password: str


class UserOut(UserBase):
    id: int
    faculties: List[str] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class FacultiesUpdate(BaseModel):
    faculties: List[str]

    @field_validator("faculties")
    @classmethod
    def validate_faculties(cls, v: List[str]) -> List[str]:
        invalid = [f for f in v if f not in FACULTIES]
        if invalid:
            raise ValueError(f"Недопустимые факультеты: {invalid}")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
