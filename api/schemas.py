"""
api/schemas.py

Pydantic response models for the API layer.

These are NOT the DB models (those live in db/database.py). These define
exactly what the API returns. Never expose raw DB rows directly — always
serialize through these schemas.
"""

from pydantic import BaseModel
from typing import Optional


class EnrichmentSchema(BaseModel):
    """AI enrichment data returned in lead detail views."""
    opportunity_score: Optional[int] = None
    score_reasoning: Optional[str] = None
    talking_points: Optional[list[str]] = None
    likely_product_needs: Optional[list[str]] = None
    outreach_angle: Optional[str] = None
    risk_flags: Optional[list[str]] = None
    web_research_summary: Optional[str] = None
    qualifier_bonus: Optional[int] = None
    model_version: Optional[str] = None
    prompt_version: Optional[str] = None
    created_at: Optional[str] = None


class ContractorListItem(BaseModel):
    """Lightweight — used in the leads list view. No enrichment details."""
    id: str
    name: str
    city: Optional[str] = None
    state: Optional[str] = None
    phone: Optional[str] = None
    gaf_tier: str
    distance_miles: Optional[float] = None
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    pipeline_stage: str
    opportunity_score: Optional[int] = None
    outreach_angle: Optional[str] = None
    has_enrichment: bool


class ContractorDetail(ContractorListItem):
    """Full profile — used in the lead detail view."""
    address: Optional[str] = None
    zip_code: Optional[str] = None
    website: Optional[str] = None
    specialties: Optional[list[str]] = None
    gaf_profile_url: Optional[str] = None
    scraped_at: Optional[str] = None
    enrichment: Optional[EnrichmentSchema] = None


class PaginatedLeads(BaseModel):
    total: int
    page: int
    page_size: int
    results: list[ContractorListItem]


class StageUpdateRequest(BaseModel):
    stage: str


class StageUpdateResponse(BaseModel):
    id: str
    pipeline_stage: str
    updated_at: str


class PipelineRunRequest(BaseModel):
    zip_code: str = "10013"
    distance: int = 25


class PipelineRunResponse(BaseModel):
    run_id: str
    status: str
    message: str


class PipelineStatusResponse(BaseModel):
    run_id: Optional[str] = None
    status: Optional[str] = None
    contractors_scraped: Optional[int] = None
    contractors_new: Optional[int] = None
    enrichments_created: Optional[int] = None
    enrichments_failed: Optional[int] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    zip_code: Optional[str] = None
