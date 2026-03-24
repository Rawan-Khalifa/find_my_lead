"""
api/routes/leads.py

Lead listing and detail endpoints.

The list endpoint powers the main dashboard table with filtering, sorting,
and pagination. The detail endpoint powers the lead profile drawer/page.

Both use a LEFT JOIN so contractors without enrichments still appear —
unenriched leads show has_enrichment=False and null score/angle fields.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc
from typing import Optional
import json

from db.database import get_db, ContractorDB, EnrichmentDB
from api.schemas import (
    ContractorListItem,
    ContractorDetail,
    PaginatedLeads,
    EnrichmentSchema,
)

router = APIRouter()


def _parse_json_field(value) -> list:
    """
    SQLite's JSON type can return a Python list or a raw JSON string
    depending on how the value was written. This normalizes both cases.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return []


@router.get("", response_model=PaginatedLeads)
def get_leads(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    tier: Optional[str] = None,
    stage: Optional[str] = None,
    city: Optional[str] = None,
    min_score: Optional[int] = None,
    sort_by: str = "opportunity_score",
    sort_order: str = "desc",
    db: Session = Depends(get_db),
):
    """
    List leads with filtering, sorting, and pagination.

    Joins contractors with enrichments (LEFT JOIN) so every contractor
    appears even if not yet enriched. Default sort puts highest-scoring
    leads first — the rep's most valuable next call is always at the top.
    """
    query = db.query(ContractorDB, EnrichmentDB).outerjoin(
        EnrichmentDB, ContractorDB.id == EnrichmentDB.contractor_id
    )

    if tier:
        query = query.filter(ContractorDB.gaf_tier == tier)
    if stage:
        query = query.filter(ContractorDB.pipeline_stage == stage)
    if city:
        query = query.filter(ContractorDB.city.ilike(f"%{city}%"))
    if min_score is not None:
        query = query.filter(EnrichmentDB.opportunity_score >= min_score)

    sort_column_map = {
        "opportunity_score": EnrichmentDB.opportunity_score,
        "distance_miles": ContractorDB.distance_miles,
        "name": ContractorDB.name,
    }
    sort_col = sort_column_map.get(sort_by, EnrichmentDB.opportunity_score)

    # PRODUCTION PATH: PostgreSQL treats NULL ordering differently (NULLs first
    # in DESC). Add nullslast()/nullsfirst() when migrating to Postgres.
    if sort_order == "asc":
        query = query.order_by(asc(sort_col))
    else:
        query = query.order_by(desc(sort_col))

    total = query.count()

    offset = (page - 1) * page_size
    rows = query.offset(offset).limit(page_size).all()

    results = []
    for contractor, enrichment in rows:
        results.append(ContractorListItem(
            id=contractor.id,
            name=contractor.name,
            city=contractor.city,
            state=contractor.state,
            phone=contractor.phone,
            gaf_tier=contractor.gaf_tier,
            distance_miles=contractor.distance_miles,
            rating=contractor.rating,
            reviews_count=contractor.reviews_count,
            pipeline_stage=contractor.pipeline_stage,
            opportunity_score=enrichment.opportunity_score if enrichment else None,
            outreach_angle=enrichment.outreach_angle if enrichment else None,
            has_enrichment=enrichment is not None,
        ))

    return PaginatedLeads(
        total=total,
        page=page,
        page_size=page_size,
        results=results,
    )


@router.get("/{contractor_id}", response_model=ContractorDetail)
def get_lead(contractor_id: str, db: Session = Depends(get_db)):
    """
    Full lead detail including nested enrichment data.

    Returns 404 if the contractor ID doesn't exist. Enrichment may be
    None if the contractor hasn't been through the enrichment pipeline yet.
    """
    contractor = db.query(ContractorDB).filter(
        ContractorDB.id == contractor_id
    ).first()
    if not contractor:
        raise HTTPException(status_code=404, detail="Contractor not found")

    enrichment = db.query(EnrichmentDB).filter(
        EnrichmentDB.contractor_id == contractor_id
    ).first()

    enrichment_schema = None
    if enrichment:
        enrichment_schema = EnrichmentSchema(
            opportunity_score=enrichment.opportunity_score,
            score_reasoning=enrichment.score_reasoning,
            talking_points=_parse_json_field(enrichment.talking_points),
            likely_product_needs=_parse_json_field(enrichment.likely_product_needs),
            outreach_angle=enrichment.outreach_angle,
            risk_flags=_parse_json_field(enrichment.risk_flags),
            web_research_summary=enrichment.web_research_summary,
            qualifier_bonus=enrichment.qualifier_bonus,
            model_version=enrichment.model_version,
            prompt_version=enrichment.prompt_version,
            created_at=enrichment.created_at,
        )

    return ContractorDetail(
        id=contractor.id,
        name=contractor.name,
        city=contractor.city,
        state=contractor.state,
        phone=contractor.phone,
        gaf_tier=contractor.gaf_tier,
        distance_miles=contractor.distance_miles,
        rating=contractor.rating,
        reviews_count=contractor.reviews_count,
        pipeline_stage=contractor.pipeline_stage,
        opportunity_score=enrichment.opportunity_score if enrichment else None,
        outreach_angle=enrichment.outreach_angle if enrichment else None,
        has_enrichment=enrichment is not None,
        address=contractor.address,
        zip_code=contractor.zip_code,
        website=contractor.website,
        specialties=_parse_json_field(contractor.specialties),
        gaf_profile_url=contractor.gaf_profile_url,
        scraped_at=contractor.scraped_at,
        enrichment=enrichment_schema,
    )
