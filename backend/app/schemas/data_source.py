from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DataSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    database_type: Literal["postgresql", "mysql", "sqlserver"]
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    database_name: str = Field(min_length=1, max_length=255)
    schema_name: str | None = Field(default=None, max_length=255)
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=2048)
    options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", "host", "database_name", "username")
    @classmethod
    def strip_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Field cannot be blank")
        return normalized

    @field_validator("options")
    @classmethod
    def allowed_options(cls, value: dict[str, Any]) -> dict[str, Any]:
        if set(value) - {"encrypt", "trust_server_certificate"} or any(not isinstance(item, bool) for item in value.values()):
            raise ValueError("Unsupported connection options")
        return value


class DataSourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    database_name: str | None = Field(default=None, min_length=1, max_length=255)
    schema_name: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, min_length=1, max_length=255)
    password: str | None = Field(default=None, min_length=1, max_length=2048)
    options: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("At least one setting must be provided")
        for field_name in self.model_fields_set - {"schema_name"}:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        if self.options is not None and (set(self.options) - {"encrypt", "trust_server_certificate"} or any(not isinstance(item, bool) for item in self.options.values())):
            raise ValueError("Unsupported connection options")
        return self


class DataSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    workspace_id: int
    name: str
    database_type: str
    host: str
    port: int
    database_name: str
    schema_name: str | None
    username: str
    options: dict[str, Any]
    status: str
    discovery_status: str
    safe_error_code: str | None
    safe_error_message: str | None
    created_at: datetime
    updated_at: datetime
    last_tested_at: datetime | None
    last_discovered_at: datetime | None


class DiscoveredColumnResponse(BaseModel):
    name: str
    data_type: str
    nullable: bool
    is_primary_key: bool
    foreign_key: str | None
    profile: dict[str, Any]


class DiscoveredTableResponse(BaseModel):
    schema_name: str
    name: str
    table_type: str
    row_count_estimate: int | None
    foreign_keys: list[dict[str, Any]]
    profile: dict[str, Any]
    discovered_at: datetime
    columns: list[DiscoveredColumnResponse]


class SchemaResponse(BaseModel):
    data_source_id: int
    status: str
    discovered_at: datetime | None
    tables: list[DiscoveredTableResponse]


class KPIProfile(BaseModel):
    name: str
    description: str
    required_tables_and_columns: list[str]
    proposed_calculation: str
    assumptions: list[str]
    confidence: float = Field(ge=0, le=1)


class BusinessProfile(BaseModel):
    business_domain_hypothesis: str
    confidence: float = Field(ge=0, le=1)
    uncertainty: list[str]
    entities: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    suggested_kpis: list[KPIProfile]
    analytical_questions: list[str]
    dashboard_categories: list[str]
    missing_or_ambiguous_metadata: list[str]
    assumptions_requiring_confirmation: list[str]


class BusinessProfileResponse(BaseModel):
    status: Literal["available", "not_configured", "failed", "not_generated"]
    profile: BusinessProfile | None
    message: str | None
