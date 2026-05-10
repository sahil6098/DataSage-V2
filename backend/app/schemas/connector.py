from pydantic import BaseModel, Field, field_validator


class ConnectDatabaseRequest(BaseModel):
    type: str
    connection_uri: str = Field(min_length=8, max_length=4096)
    database_name: str | None = Field(default=None, max_length=120)
    save_to_library: bool = True

    @field_validator("type")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"mongodb", "postgresql"}:
            raise ValueError("Only MongoDB Atlas and Supabase PostgreSQL are supported.")
        return normalized


class SavedSourceOut(BaseModel):
    id: str
    source_type: str
    display_name: str
    database_name: str | None = None
    masked_uri: str
    updated_at: str | None = None


class PreviewField(BaseModel):
    name: str
    type: str | None = None
    nullable: bool | None = None
    samples: list[str] = Field(default_factory=list)
    description: str | None = None


class PreviewTable(BaseModel):
    name: str
    row_count: int | None = None
    fields: list[PreviewField] = Field(default_factory=list)
    selected: bool = True
    description: str | None = None


class SchemaResponse(BaseModel):
    source_type: str
    database_name: str | None = None
    database_description: str | None = None
    selected_table_count: int = 0
    tables: list[PreviewTable] = Field(default_factory=list)


class PreviewRowsResponse(BaseModel):
    table_name: str
    rows: list[dict[str, object]] = Field(default_factory=list)


class SchemaContextUpdateRequest(BaseModel):
    selected_tables: list[str] = Field(default_factory=list)
    database_description: str | None = Field(default=None, max_length=2000)
    table_descriptions: dict[str, str] = Field(default_factory=dict)
    field_descriptions: dict[str, dict[str, str]] = Field(default_factory=dict)
