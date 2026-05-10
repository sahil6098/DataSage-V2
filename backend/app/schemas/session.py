from datetime import datetime

from pydantic import BaseModel, Field


class SessionCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    draft: bool = True


class MessageOut(BaseModel):
    role: str
    content: str
    viz_data: str | None = None
    created_at: datetime | None = None


class SourceConfigOut(BaseModel):
    type: str
    file_name: str | None = None
    database_name: str | None = None
    connection_uri: str | None = None
    selected_tables: list[str] = Field(default_factory=list)
    database_description: str | None = None
    table_descriptions: dict[str, str] = Field(default_factory=dict)
    field_descriptions: dict[str, dict[str, str]] = Field(default_factory=dict)


class SessionOut(BaseModel):
    id: str
    title: str
    draft: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SessionDetailOut(SessionOut):
    messages: list[MessageOut] = Field(default_factory=list)
    data_source: SourceConfigOut | None = None
