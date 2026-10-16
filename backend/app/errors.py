"""Consistent API responses.

Success: {"data": ...}            (optionally "meta": {...})
Error:   {"error": {"code": str, "message": str, "details": [...]}}
"""
from __future__ import annotations

from typing import Any


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, details: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details or []


def not_found(what: str, ident: Any) -> AppError:
    return AppError(404, "not_found", f"{what} {ident} was not found")


def conflict(message: str) -> AppError:
    return AppError(409, "conflict", message)


def invalid(message: str, field: str | None = None) -> AppError:
    details = [{"field": field, "message": message}] if field else []
    return AppError(422, "validation_error", message, details)


def ok(data: Any, **meta: Any) -> dict[str, Any]:
    return {"data": data, "meta": meta} if meta else {"data": data}
