from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.backend.app.schemas.api import ExperimentInput


class TemplateRecord(BaseModel):
    id: str
    name: str
    category: str
    description: str
    built_in: bool
    payload: ExperimentInput
    tags: list[str] = Field(default_factory=list)
    usage_count: int = 0


class TemplateListResponse(BaseModel):
    templates: list[TemplateRecord]
    total: int = 0


class TemplateCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    category: str = Field(default="Custom", min_length=1, max_length=60)
    description: str = Field(min_length=1, max_length=240)
    tags: list[str] = Field(default_factory=list, max_length=8)
    payload: ExperimentInput


class TemplateDeleteResponse(BaseModel):
    id: str
    deleted: Literal[True]
