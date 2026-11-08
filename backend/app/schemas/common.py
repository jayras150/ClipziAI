"""
Common Pydantic schemas - shared responses
"""
from typing import Any, Generic, Optional, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str = "connected"
    redis: str = "connected"
    gpu_available: bool = False


class FormatsResponse(BaseModel):
    supported_formats: list[str]
    supported_resolutions: list[str]
    max_duration_minutes: int
    max_file_size_mb: int