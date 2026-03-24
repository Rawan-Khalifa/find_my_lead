"""
db/database.py

SQLAlchemy ORM setup with SQLite for development.

PRODUCTION PATH:
    Change DATABASE_URL to postgresql+asyncpg://user:pass@host/dbname
    Everything else -- models, queries, upsert logic -- stays identical.
    SQLAlchemy abstracts the dialect. One config change = different database.

    At scale we would add:
    - Connection pooling via PgBouncer (SQLite has no concurrency)
    - Read replicas for the API query layer
    - Redis cache in front of high-traffic endpoints (lead list, scores)
    - Alembic for schema migrations (never run raw ALTER TABLE in prod)
"""

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, Column, String, Float, Integer, Text, JSON
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timezone
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/roofing_intel.db")

engine = create_engine(
    DATABASE_URL,
    # check_same_thread is SQLite-only, safe for our single-process dev server
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class ContractorDB(Base):
    """
    ORM model for contractors table.

    Design decisions:
    - specialties: JSON array (avoids a join table for MVP; in prod use a
      proper many-to-many with a specialties lookup table for filtering)
    - phone: digits-only string (normalized at Pydantic boundary, formatted by UI)
    - pipeline_stage: rep-owned state, NOT in the enrichments table --
      important separation of concerns between AI output and human decisions
    - source_url + scraped_at: full audit trail per record
    """
    __tablename__ = "contractors"

    id              = Column(String, primary_key=True)
    name            = Column(String, nullable=False, index=True)
    address         = Column(String)
    city            = Column(String, index=True)
    state           = Column(String, index=True)
    zip_code        = Column(String)
    phone           = Column(String)
    website         = Column(String)

    gaf_tier        = Column(String, nullable=False, default="Unknown", index=True)
    specialties     = Column(JSON, default=list)
    reviews_count   = Column(Integer)
    rating          = Column(Float)
    distance_miles  = Column(Float, index=True)
    gaf_profile_url = Column(String)

    # Rep-managed state (NOT AI-generated)
    pipeline_stage  = Column(String, default="new", index=True)

    # Audit
    source_url      = Column(String)
    scraped_at      = Column(String)
    created_at      = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    updated_at      = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())


class EnrichmentDB(Base):
    """
    AI enrichment results -- stored separately from contractor facts.

    Why a separate table:
        Contractors are scraped once but enriched many times -- when we
        upgrade the model, refine the prompt, or refresh stale insights.
        Storing raw_llm_response and model_version means we can:
        1. Audit exactly why the AI said what it said
        2. Re-enrich only records enriched with an older model version
        3. Roll back if a prompt change degrades quality
    """
    __tablename__ = "enrichments"

    id                   = Column(String, primary_key=True)
    contractor_id        = Column(String, nullable=False, index=True)

    opportunity_score    = Column(Integer)         # 0-100
    score_reasoning      = Column(Text)            # human-readable explanation
    talking_points       = Column(JSON, default=list)
    likely_product_needs = Column(JSON, default=list)
    outreach_angle       = Column(String)          # new / upsell / reactivation
    risk_flags           = Column(JSON, default=list)

    # Perplexity web research
    web_research_summary = Column(Text)            # raw Perplexity output
    qualifier_bonus      = Column(Integer)         # pts added from web research

    # Full audit trail
    raw_llm_response     = Column(Text)            # never discard model output
    model_version        = Column(String)          # e.g. gpt-4o
    prompt_version       = Column(String)          # semantic version of prompt template

    created_at           = Column(String)
    updated_at           = Column(String)


class PipelineRunDB(Base):
    """
    Execution log for every pipeline run.

    Feeds:
    - Ops monitoring dashboard (did pipeline run? error rate?)
    - Manager UI (when were leads last refreshed?)
    - Alerting (if pipeline hasn't run in 24h, page on-call)
    """
    __tablename__ = "pipeline_runs"

    id                   = Column(String, primary_key=True)
    started_at           = Column(String)
    completed_at         = Column(String)
    zip_code             = Column(String)
    distance_miles       = Column(Integer)
    contractors_scraped  = Column(Integer, default=0)
    contractors_new      = Column(Integer, default=0)
    enrichments_created  = Column(Integer, default=0)
    enrichments_failed   = Column(Integer, default=0)
    status               = Column(String, default="running")  # running/completed/failed
    error_log            = Column(Text)


def init_db():
    """Create all tables. Idempotent -- safe to call on every startup."""
    import os
    os.makedirs("data", exist_ok=True)
    Base.metadata.create_all(bind=engine)
    print("[db] Tables initialized")


def get_db():
    """
    FastAPI dependency-injection pattern.
    Yields a session and guarantees cleanup even on unhandled exceptions.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
