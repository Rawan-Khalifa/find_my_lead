"""
api/routes/stages.py

Pipeline stage management — the ONLY place in the codebase that writes
pipeline_stage. This is a sacred rep-owned field: the ingestion pipeline
never touches it, the enrichment pipeline never touches it. Only an
explicit rep action through this endpoint changes a contractor's stage.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from db.database import get_db, ContractorDB
from api.schemas import StageUpdateRequest, StageUpdateResponse

router = APIRouter()

VALID_STAGES = {"new", "contacted", "qualified", "customer", "disqualified"}


@router.patch("/{contractor_id}/stage", response_model=StageUpdateResponse)
def update_stage(
    contractor_id: str,
    body: StageUpdateRequest,
    db: Session = Depends(get_db),
):
    """
    Update a contractor's pipeline stage.

    Validates against the allowed stage enum and returns 400 with a
    clear message if the stage is invalid. Returns 404 if the contractor
    doesn't exist.
    """
    if body.stage not in VALID_STAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid stage '{body.stage}'. Must be one of: {', '.join(sorted(VALID_STAGES))}",
        )

    contractor = db.query(ContractorDB).filter(
        ContractorDB.id == contractor_id
    ).first()
    if not contractor:
        raise HTTPException(status_code=404, detail="Contractor not found")

    now = datetime.now(timezone.utc).isoformat()
    contractor.pipeline_stage = body.stage
    contractor.updated_at = now
    db.commit()

    return StageUpdateResponse(
        id=contractor.id,
        pipeline_stage=contractor.pipeline_stage,
        updated_at=now,
    )
