from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20)


class LogoutRequest(BaseModel):
    refresh_token: str | None = None  # optional: revoke a specific token only


class UserOut(BaseModel):
    id: str
    email: EmailStr
    name: str


class AuthTokensOut(BaseModel):
    access_token: str
    refresh_token: str
    user: UserOut
