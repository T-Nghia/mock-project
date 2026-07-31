import uuid
from pydantic import BaseModel, EmailStr, Field, ConfigDict

class UserRegister(BaseModel):
    full_name: str
    email: EmailStr
    password: str = Field(min_length=6)

class TeacherCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str = Field(min_length=6)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshRequest(BaseModel):
    refresh_token: str

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    full_name: str
    email: EmailStr
    role: str