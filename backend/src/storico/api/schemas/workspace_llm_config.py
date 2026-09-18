"""Workspace LLM configuration Pydantic schemas for Storico API."""

from pydantic import BaseModel, ConfigDict, Field


class LLMConfigRequest(BaseModel):
    """Request body for upserting workspace LLM config — all fields optional for partial updates."""

    model_config = ConfigDict(extra="forbid")

    provider: str | None = Field(None, max_length=50)
    model: str | None = Field(None, max_length=100)
    temperature: float | None = None
    max_tokens: int | None = None
    base_url: str | None = Field(None, max_length=500)
    api_key: str | None = Field(None, max_length=500)


class ModelInfo(BaseModel):
    """Describes a single available model from a provider."""

    id: str
    name: str


class LLMModelProbeRequest(BaseModel):
    """Optional selection the model list must describe.

    The settings form probes the provider the user has *chosen*, which is not
    necessarily the one already saved. When ``provider`` is present the body
    describes the probe entirely: a key or base URL left out is missing for this
    probe and is never borrowed from the saved row, because borrowing would send
    one provider's credential to another provider's endpoint. An absent body (or
    one without a provider) keeps the other reading — probe what is saved.
    """

    model_config = ConfigDict(extra="forbid")

    provider: str | None = Field(None, max_length=50)
    base_url: str | None = Field(None, max_length=500)
    api_key: str | None = Field(None, max_length=500)


class LLMConfigResponse(BaseModel):
    """Response body representing workspace LLM config with resolved defaults."""

    model_config = ConfigDict(from_attributes=True)

    provider: str
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    base_url: str | None = None
    api_key: str | None = None
