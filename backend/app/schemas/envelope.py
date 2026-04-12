"""
Standard API response envelope used by every endpoint.

All responses have the shape:
    { "data": <payload | null>, "error": <null | {message, code}>, "meta": {} }

Success:  ApiResponse(data=payload, meta={"total": n})
Error:    ApiResponse(error=ErrorDetail(message="...", code="not_found"))

Helpers
-------
ok(data, meta={})   — build a success envelope
err(message, code)  — build an error envelope (used by the exception handler)
"""

from __future__ import annotations

from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    message: str
    code: str = "error"


class ApiResponse(BaseModel, Generic[T]):
    data: Optional[T] = None
    error: Optional[ErrorDetail] = None
    meta: dict[str, Any] = Field(default_factory=dict)


def ok(data: T, meta: dict[str, Any] | None = None) -> ApiResponse[T]:
    return ApiResponse(data=data, meta=meta or {})


def err(message: str, code: str = "error") -> ApiResponse[None]:
    return ApiResponse(error=ErrorDetail(message=message, code=code))
