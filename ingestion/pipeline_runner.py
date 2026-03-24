"""
ingestion/pipeline_runner.py

Orchestrates the full ingestion flow:
    scrape -> validate -> upsert to DB -> log pipeline run

This is the single entrypoint the scheduler (or API background task) calls.
Keeping orchestration separate from scraping and DB logic means each piece
is independently testable and replaceable.

PRODUCTION SCALING PATH:
    Current: runs as a single async Python process, triggered manually or by cron
    Next:    FastAPI BackgroundTask (already wired in the API layer)
    Scale:   Celery worker + Redis broker, one task per contractor for enrichment
             Pipeline runner becomes a DAG in Airflow / Prefect / Dagster
             Each stage (scrape / validate / enrich) becomes an independent task
             with retry logic, dead-letter queues, and per-task observability
"""

from dotenv import load_dotenv
load_dotenv()

import asyncio
import uuid
from datetime import datetime, timezone
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingestion.scraper import run_scrape
from db.database import init_db, SessionLocal, ContractorDB, PipelineRunDB
from models.contractor import ContractorRecord


def upsert_contractor(db, record: ContractorRecord) -> tuple[bool, str]:
    """
    Insert or update a contractor record.

    Returns (is_new: bool, contractor_id: str)

    WHY UPSERT over INSERT:
        Running this pipeline daily means the same contractors appear in
        every scrape. Blind inserts would duplicate. Upsert means:
        - New contractor -> INSERT, pipeline_new_count++
        - Existing contractor -> UPDATE (phone, rating, tier might change)
        - The contractor's pipeline_stage is NEVER overwritten by scraper
          (rep decisions are sacred -- the pipeline doesn't reset their work)
    """
    existing = db.query(ContractorDB).filter(ContractorDB.id == record.id).first()

    now = datetime.now(timezone.utc).isoformat()

    if existing:
        # Update scraped fields but preserve rep-managed state
        existing.name            = record.name
        existing.address         = record.address
        existing.city            = record.city
        existing.state           = record.state
        existing.zip_code        = record.zip_code
        existing.phone           = record.phone
        existing.website         = record.website
        existing.gaf_tier        = record.gaf_tier.value
        existing.specialties     = record.specialties
        existing.reviews_count   = record.reviews_count
        existing.rating          = record.rating
        existing.distance_miles  = record.distance_miles
        existing.gaf_profile_url = record.gaf_profile_url
        existing.source_url      = record.source_url
        existing.scraped_at      = record.scraped_at
        existing.updated_at      = now
        # NOTE: pipeline_stage intentionally NOT updated -- rep owns this field
        db.commit()
        return False, record.id
    else:
        db_record = ContractorDB(
            id              = record.id,
            name            = record.name,
            address         = record.address,
            city            = record.city,
            state           = record.state,
            zip_code        = record.zip_code,
            phone           = record.phone,
            website         = record.website,
            gaf_tier        = record.gaf_tier.value,
            specialties     = record.specialties,
            reviews_count   = record.reviews_count,
            rating          = record.rating,
            distance_miles  = record.distance_miles,
            gaf_profile_url = record.gaf_profile_url,
            pipeline_stage  = "new",
            source_url      = record.source_url,
            scraped_at      = record.scraped_at,
            created_at      = now,
            updated_at      = now,
        )
        db.add(db_record)
        db.commit()
        return True, record.id


async def run_ingestion_pipeline(
    zip_code: str = "10013",
    distance: int = 25,
) -> dict:
    """
    Full pipeline run. Returns a summary dict for the API response.
    """
    init_db()
    db = SessionLocal()
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()

    # Log pipeline start
    run_log = PipelineRunDB(
        id=run_id,
        started_at=started_at,
        zip_code=zip_code,
        distance_miles=distance,
        status="running",
    )
    db.add(run_log)
    db.commit()

    print(f"\n[pipeline] Run {run_id[:8]} started")

    try:
        # ── Scrape ────────────────────────────────────────────────────────────
        contractors = await run_scrape(zip_code=zip_code, distance=distance)
        run_log.contractors_scraped = len(contractors)
        db.commit()

        # ── Upsert ───────────────────────────────────────────────────────────
        new_count = 0
        for record in contractors:
            is_new, cid = upsert_contractor(db, record)
            if is_new:
                new_count += 1
                print(f"[pipeline] NEW      {record.name}")
            else:
                print(f"[pipeline] UPDATED  {record.name}")

        # ── Finalize run log ─────────────────────────────────────────────────
        run_log.completed_at    = datetime.now(timezone.utc).isoformat()
        run_log.contractors_new = new_count
        run_log.status          = "completed"
        db.commit()

        summary = {
            "run_id": run_id,
            "status": "completed",
            "contractors_scraped": len(contractors),
            "contractors_new": new_count,
            "contractors_updated": len(contractors) - new_count,
            "zip_code": zip_code,
            "distance_miles": distance,
            "started_at": started_at,
            "completed_at": run_log.completed_at,
        }

        print(f"\n[pipeline] Complete | {len(contractors)} scraped | {new_count} new")
        return summary

    except Exception as e:
        run_log.status       = "failed"
        run_log.error_log    = str(e)
        run_log.completed_at = datetime.now(timezone.utc).isoformat()
        db.commit()
        print(f"[pipeline] FAILED: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    result = asyncio.run(run_ingestion_pipeline())
    print("\n=== PIPELINE SUMMARY ===")
    for k, v in result.items():
        print(f"  {k}: {v}")