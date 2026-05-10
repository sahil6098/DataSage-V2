from typing import Generic, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class ApiEnvelope(BaseModel, Generic[T]):
    success: bool = True
    message: str | None = None
    data: T | None = None


class ErrorEnvelope(BaseModel):
    success: bool = False
    message: str
    error_code: str | None = None
    errors: list[str] = Field(default_factory=list)
