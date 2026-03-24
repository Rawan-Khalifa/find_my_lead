"""
models/contractor.py

Pydantic models define the schema boundary between raw scraped data
and our internal data model. Any data that can't be validated here
never enters the database — this is our first line of data quality defense.

Production note: these models would also be used to generate JSON Schema
for API response validation and OpenAPI documentation.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from enum import Enum
import re


class GAFTier(str, Enum):
    """
    GAF certification tiers — ordered by value to the distributor.
    Master Elite = top 3% of contractors, highest purchase volume potential.
    This enum enforces we only store known tier values, never free-form strings.
    """
    MASTER_ELITE = "Master Elite"
    CERTIFIED_PLUS = "Certified Plus"
    CERTIFIED = "Certified"
    REGISTERED = "Registered"
    UNKNOWN = "Unknown"


class PipelineStage(str, Enum):
    """
    Sales pipeline stages — rep-managed, not system-managed.
    Reps drag leads through these stages in the UI.
    """
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    CUSTOMER = "customer"
    DISQUALIFIED = "disqualified"


class ContractorRaw(BaseModel):
    """
    Raw scraped data — exactly what comes off the page, minimally processed.
    We store this separately so we can re-enrich without re-scraping.

    Think of this as the 'bronze layer' in a medallion architecture:
    raw -> validated (silver) -> enriched (gold).
    """
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    gaf_tier: GAFTier = GAFTier.UNKNOWN
    specialties: list[str] = Field(default_factory=list)
    reviews_count: Optional[int] = None
    rating: Optional[float] = None
    distance_miles: Optional[float] = None
    gaf_profile_url: Optional[str] = None

    # Audit fields — critical for reproducibility
    source_url: str
    scraped_at: str

    @field_validator("phone", mode="before")
    @classmethod
    def normalize_phone(cls, v):
        """Strip formatting, store digits only. Display formatting is the UI's job."""
        if v is None:
            return None
        digits = re.sub(r"\D", "", str(v))
        return digits if len(digits) >= 10 else None

    @field_validator("rating", mode="before")
    @classmethod
    def clamp_rating(cls, v):
        if v is None:
            return None
        rating = float(v)
        return rating if 0.0 <= rating <= 5.0 else None

    @field_validator("gaf_tier", mode="before")
    @classmethod
    def normalize_tier(cls, v):
        """
        GAF page sometimes renders tier as 'Master Elite(R)' with trademark symbol.
        Normalize to clean enum value.
        """
        if not v:
            return GAFTier.UNKNOWN
        clean = str(v).replace("®", "").replace("™", "").strip()
        for tier in GAFTier:
            if tier.value.lower() in clean.lower():
                return tier
        return GAFTier.UNKNOWN


class ContractorRecord(ContractorRaw):
    """
    Validated contractor record — passed all checks, assigned a stable ID.
    This is what gets written to the database.
    """
    id: str
    pipeline_stage: PipelineStage = PipelineStage.NEW
    created_at: str
    updated_at: str
