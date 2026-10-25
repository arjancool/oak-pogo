"""Shared API schema helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, PlainSerializer

# Timestamps leave the API as ISO 8601 UTC with an explicit offset.
UtcDatetime = Annotated[datetime, PlainSerializer(lambda v: v.isoformat(), return_type=str)]


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(ApiModel):
    total: int
    page: int
    page_size: int
    items: list[Any]


class Message(ApiModel):
    message: str
