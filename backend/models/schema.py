from enum import Enum
from typing import Any

from pydantic import BaseModel


class ColumnType(str, Enum):
    DATE = "Date"
    FLOAT = "Float"
    STRING = "String"


class ColumnInfo(BaseModel):
    name: str
    type: ColumnType
    sample: list[Any]


class Schema(BaseModel):
    columns: list[ColumnInfo]
    row_count: int