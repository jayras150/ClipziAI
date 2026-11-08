"""
Auth schemas - Login, register, 2FA, social auth
"""
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(min_length=2, max_length=255)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class TwoFactorSetup(BaseModel):
    secret: str
    qr_code_url: str
    backup_codes: list[str]


class TwoFactorVerify(BaseModel):
    secret: str
    otp: str


class SocialLoginRequest(BaseModel):
    provider: str  # google, x, facebook
    access_token: str