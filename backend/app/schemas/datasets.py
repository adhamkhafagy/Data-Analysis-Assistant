from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, StringConstraints
from typing_extensions import Annotated


ColumnType = Literal["text", "integer", "decimal", "boolean", "date", "datetime"]


class ColumnSpec(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
    type: ColumnType = "text"
    nullable: bool = True


class DatasetCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    columns: list[ColumnSpec] = Field(min_length=1, max_length=500)
    rows: list[dict[str, Any]] = Field(default_factory=list, max_length=1000)


class DatasetResponse(BaseModel):
    id: int
    workspace_id: int
    name: str
    source_type: str
    status: str
    schema_json: list[dict[str, Any]]
    row_count: int
    source_ref: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UploadResponse(BaseModel):
    id: int
    original_filename: str
    file_type: str
    byte_size: int
    sheet_names: list[str]
    status: str
    expires_at: datetime

    model_config = {"from_attributes": True}


class PreviewResponse(BaseModel):
    upload_id: int
    sheet_name: str | None
    columns: list[dict[str, Any]]
    rows: list[dict[str, Any]]
    total_rows: int


class ImportRequest(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)] | None = None
    dataset_id: int | None = None
    sheet_name: str | None = Field(default=None, max_length=255)
    append: bool = False
    mapping: dict[str, ColumnSpec] | None = None


class RowBatch(BaseModel):
    rows: list[dict[str, Any]] = Field(max_length=1000)


class RowUpdate(BaseModel):
    values: dict[str, Any]

