"""
api/routes/pipeline.py

Pipeline trigger and status endpoints.

POST /pipeline/run kicks off scrape + enrich as a BackgroundTask and
returns immediately. The frontend polls GET /pipeline/status to track
progress.

WHY BackgroundTasks instead of awaiting:
    The scrape + enrich pipeline takes 30-60 seconds. If we awaited it,
    the HTTP request would hang and the frontend would timeout or show
    a frozen spinner. BackgroundTasks returns the response instantly and
    runs the work after.

PRODUCTION PATH:
    Replace BackgroundTasks with Celery + Redis. Same interface — the
    endpoint creates a task and returns a task ID. The frontend polls
    status. Only the execution substrate changes (in-process → distributed).
"""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc

from db.database import get_db, SessionLocal, PipelineRunDB
from api.schemas import (
    PipelineRunRequest,
    PipelineRunResponse,
    PipelineStatusResponse,
)
from ingestion.pipeline_runner import run_ingestion_pipeline
from enrichment.enricher import run_enrichment_pipeline

router = APIRouter()


async def _run_full_pipeline(zip_code: str, distance: int):
    """
    Background task: runs the full scrape → enrich pipeline, then
    updates the pipeline run record with enrichment stats.
    """
    try:
        ingestion_result = await run_ingestion_pipeline(
            zip_code=zip_code, distance=distance
        )
        run_id = ingestion_result["run_id"]

        enrichment_result = await run_enrichment_pipeline()

        db = SessionLocal()
        try:
            run = db.query(PipelineRunDB).filter(PipelineRunDB.id == run_id).first()
            if run:
                run.enrichments_created = enrichment_result.get("enriched", 0)
                run.enrichments_failed = enrichment_result.get("failed", 0)
                db.commit()
        finally:
            db.close()

        print(f"[api] Pipeline complete | run_id={run_id[:8]}")

    except Exception as e:
        print(f"[api] Pipeline background task failed: {e}")


@router.post("/run", response_model=PipelineRunResponse)
async def trigger_pipeline(
    body: PipelineRunRequest,
    background_tasks: BackgroundTasks,
):
    """
    Trigger a full pipeline run (scrape + enrich) in the background.

    Returns immediately with a tracking ID. The actual pipeline run
    creates its own PipelineRunDB entry — poll GET /pipeline/status
    to see real progress.
    """
    background_tasks.add_task(_run_full_pipeline, body.zip_code, body.distance)

    return PipelineRunResponse(
        run_id=str(uuid.uuid4()),
        status="started",
        message=(
            f"Pipeline started for ZIP {body.zip_code} within "
            f"{body.distance} miles. Poll GET /pipeline/status for progress."
        ),
    )


@router.get("/status", response_model=PipelineStatusResponse)
def get_pipeline_status(db: Session = Depends(get_db)):
    """
    Return the most recent pipeline run status.

    Powers the "Last refreshed X minutes ago" indicator in the UI.
    Returns empty fields if no pipeline has ever run.
    """
    run = db.query(PipelineRunDB).order_by(
        desc(PipelineRunDB.started_at)
    ).first()

    if not run:
        return PipelineStatusResponse()

    return PipelineStatusResponse(
        run_id=run.id,
        status=run.status,
        contractors_scraped=run.contractors_scraped,
        contractors_new=run.contractors_new,
        enrichments_created=run.enrichments_created,
        enrichments_failed=run.enrichments_failed,
        started_at=run.started_at,
        completed_at=run.completed_at,
        zip_code=run.zip_code,
    )
