"""
enrichment/enricher.py

Two-API enrichment pipeline: transforms raw contractor records into actionable
sales intelligence a rep can use on their next call.

Three distinct phases per contractor:
    1. SCORING — deterministic Python formula (no AI involvement)
    2. RESEARCH — Perplexity sonar model searches the live web for business signals
    3. SYNTHESIS — OpenAI structured output generates rep-ready sales intelligence

WHY two APIs instead of one:
    Perplexity is purpose-built for live web search — it finds current hiring posts,
    BBB ratings, and news articles that OpenAI's training cutoff can't reach.
    OpenAI is purpose-built for structured synthesis — it takes everything we know
    and produces a validated JSON object matching our exact schema.
    Each API does what it's best at. No overlap, no redundancy.

PRODUCTION PATH:
    Replace asyncio.gather with a Celery task queue backed by Redis.
    Each enrich_one() becomes a Celery task. Failed tasks go to a dead-letter queue
    with exponential backoff retry. The semaphore pattern here mirrors that concurrency
    control — the interface stays the same, only the execution substrate changes.
"""

from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
import openai
from pydantic import BaseModel, ValidationError, field_validator

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import init_db, SessionLocal, ContractorDB, EnrichmentDB
from models.contractor import GAFTier


# ─────────────────────────────────────────────────────────────
# PYDANTIC MODEL FOR AI OUTPUT VALIDATION
# ─────────────────────────────────────────────────────────────

class EnrichmentOutput(BaseModel):
    """
    Pydantic schema enforced on every OpenAI response.
    If the model returns something that doesn't match this, we catch
    the ValidationError, log it, and mark the contractor as failed.
    Never let a malformed AI response enter the database.
    """
    talking_points: list[str]
    likely_product_needs: list[str]
    outreach_angle: str
    risk_flags: list[str]

    @field_validator("talking_points")
    @classmethod
    def exactly_three_talking_points(cls, v):
        if len(v) != 3:
            raise ValueError(f"Expected exactly 3 talking points, got {len(v)}")
        return v

    @field_validator("likely_product_needs")
    @classmethod
    def exactly_three_product_needs(cls, v):
        if len(v) != 3:
            raise ValueError(f"Expected exactly 3 product needs, got {len(v)}")
        return v

    @field_validator("outreach_angle")
    @classmethod
    def valid_outreach_angle(cls, v):
        allowed = {"new_relationship", "upsell", "reactivation"}
        if v not in allowed:
            raise ValueError(f"outreach_angle must be one of {allowed}, got '{v}'")
        return v

    @field_validator("risk_flags")
    @classmethod
    def max_three_risk_flags(cls, v):
        if len(v) > 3:
            raise ValueError(f"Expected 0-3 risk flags, got {len(v)}")
        return v


# ─────────────────────────────────────────────────────────────
# STEP 1: DETERMINISTIC SCORING — Python only, no AI
# ─────────────────────────────────────────────────────────────

def compute_base_score(contractor: ContractorDB) -> tuple[int, str]:
    """
    Deterministic opportunity score from known signals.
    Returns (score: int, reasoning: str)

    WHY in code not AI: reproducible, explainable, zero hallucination risk.
    A rep can always ask "why this score?" and get a formula-based answer.
    """
    score = 0
    reasons = []

    tier_points = {
        "Master Elite": 40,
        "Certified Plus": 25,
        "Certified": 15,
        "Registered": 5,
    }
    tier_score = tier_points.get(contractor.gaf_tier, 0)
    score += tier_score
    if tier_score:
        reasons.append(f"{contractor.gaf_tier} tier (+{tier_score})")

    dist = contractor.distance_miles or 99
    if dist <= 5:
        score += 30
        reasons.append(f"{dist}mi away (+30)")
    elif dist <= 15:
        score += 20
        reasons.append(f"{dist}mi away (+20)")
    elif dist <= 25:
        score += 10
        reasons.append(f"{dist}mi away (+10)")

    specialties_lower = [s.lower() for s in (contractor.specialties or [])]
    if any("commercial" in s for s in specialties_lower):
        score += 15
        reasons.append("Commercial specialty (+15)")
    if any("flat" in s for s in specialties_lower):
        score += 10
        reasons.append("Flat roofing (+10)")
    if any("solar" in s for s in specialties_lower):
        score += 10
        reasons.append("Solar specialty (+10)")

    reviews = contractor.reviews_count or 0
    if reviews > 100:
        score += 10
        reasons.append(f"{reviews} reviews (+10)")
    elif reviews > 50:
        score += 5
        reasons.append(f"{reviews} reviews (+5)")

    if contractor.rating and contractor.rating >= 4.8:
        score += 5
        reasons.append(f"{contractor.rating}★ rating (+5)")

    final = min(score, 100)
    reasoning = " | ".join(reasons) + f" | Base: {final}/100"
    return final, reasoning


# ─────────────────────────────────────────────────────────────
# STEP 2: PERPLEXITY WEB RESEARCH
# ─────────────────────────────────────────────────────────────

async def research_contractor_web(
    contractor: ContractorDB,
    client: httpx.AsyncClient,
) -> tuple[str, int]:
    """
    Use Perplexity's sonar model to find live web intelligence
    about this contractor that isn't in our scraped data.

    Returns (research_summary: str, qualifier_bonus: int)

    qualifier_bonus adds 0-15 points to base score based on
    positive signals found (hiring, growth, awards, recent activity).

    PRODUCTION PATH: Cache Perplexity results for 7 days per contractor.
    Web research is expensive and contractor profiles don't change daily.
    Use Redis with TTL=604800. Only re-research on pipeline_stage change
    or manual re-enrichment trigger.
    """
    api_key = os.getenv("PERPLEXITY_API_KEY")
    model = os.getenv("PERPLEXITY_MODEL", "llama-3.1-sonar-large-128k-online")

    if not api_key:
        print(f"[enricher] No PERPLEXITY_API_KEY — skipping web research for {contractor.name}")
        return "No web research available.", 0

    prompt = f"""Research this roofing contractor for a sales intelligence report:

Contractor: {contractor.name}
Location: {contractor.city}, {contractor.state}
GAF Certification: {contractor.gaf_tier}

Find and summarize (in 150-200 words):
1. Are they currently hiring? (indicates growth/capacity)
2. Any recent news, awards, or press coverage?
3. BBB rating or any customer complaints?
4. How active is their online/social media presence?
5. Any signals of business expansion or contraction?
6. Any red flags a sales rep should know before calling?

Be factual. If you can't find information on a point, say so briefly.
Focus on signals relevant to whether this is a high-value sales target."""

    try:
        response = await client.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a business research assistant. Provide factual, "
                            "concise intelligence about businesses to help sales teams "
                            "prioritize outreach."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 400,
                "temperature": 0.2,
            },
            timeout=20.0,
        )
        response.raise_for_status()
        data = response.json()
        summary = data["choices"][0]["message"]["content"]

        bonus = _compute_qualifier_bonus(summary)
        print(f"[enricher] Perplexity: {contractor.name} | bonus=+{bonus}pts")
        return summary, bonus

    except httpx.TimeoutException:
        print(f"[enricher] Perplexity TIMEOUT for {contractor.name} — skipping")
        return "Web research timed out.", 0
    except httpx.HTTPStatusError as e:
        print(f"[enricher] Perplexity HTTP {e.response.status_code} for {contractor.name}")
        return "Web research unavailable.", 0
    except Exception as e:
        print(f"[enricher] Perplexity UNEXPECTED ERROR for {contractor.name}: {e}")
        return "Web research unavailable.", 0


def _compute_qualifier_bonus(research_summary: str) -> int:
    """
    Extract a qualifier bonus (0-15) from Perplexity's research summary.
    Keyword-based heuristic — fast, transparent, no additional API call.

    PRODUCTION PATH: Replace with a small classifier or a structured
    Perplexity response schema to make this more reliable.
    """
    bonus = 0
    text = research_summary.lower()

    positive_signals = [
        ("hiring", 5),
        ("expanding", 5),
        ("award", 4),
        ("bbb accredited", 3),
        ("a+ rating", 3),
        ("active", 2),
        ("recently", 2),
    ]
    negative_signals = [
        ("complaint", -3),
        ("lawsuit", -5),
        ("closed", -10),
        ("out of business", -10),
        ("red flag", -3),
    ]

    for keyword, pts in positive_signals:
        if keyword in text:
            bonus += pts

    for keyword, pts in negative_signals:
        if keyword in text:
            bonus += pts

    return max(0, min(bonus, 15))


# ─────────────────────────────────────────────────────────────
# STEP 3: OPENAI SYNTHESIS — qualitative fields only
# ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a sales intelligence assistant for a GAF roofing materials distributor.
Your job is to help sales reps prepare for outreach calls to roofing contractors.
Given a contractor's profile and web research, generate specific, actionable sales intelligence.
Be concrete — name specific GAF product lines where relevant (Timberline HDZ, EverGuard TPO,
Cobra ventilation, WeatherWatch underlayment, etc.).
Do not be generic. A rep must be able to use your output verbatim on a call.
Respond ONLY with valid JSON. No explanation, no markdown, just the JSON object."""


async def synthesize_with_openai(
    contractor: ContractorDB,
    base_score: int,
    web_research: str,
    client: openai.AsyncOpenAI,
) -> tuple[EnrichmentOutput, str]:
    """
    OpenAI synthesizes everything we know into structured sales intelligence.

    Note: score is NOT in the output schema — we never ask the LLM to score.
    The score is already computed deterministically. OpenAI's job is qualitative
    context only: what to say, what to sell, what to watch out for.
    """
    user_prompt = f"""Contractor Profile:
- Name: {contractor.name}
- Location: {contractor.city}, {contractor.state}
- GAF Certification: {contractor.gaf_tier}
- Specialties: {', '.join(contractor.specialties or ['Unknown'])}
- Rating: {contractor.rating or 'N/A'} ({contractor.reviews_count or 0} reviews)
- Distance from distributor: {contractor.distance_miles or 'Unknown'} miles
- Website: {contractor.website or 'None found'}
- Opportunity Score: {base_score}/100

Web Research Summary:
{web_research}

Generate a JSON object with these exact fields:
{{
  "talking_points": ["point 1", "point 2", "point 3"],
  "likely_product_needs": ["product 1", "product 2", "product 3"],
  "outreach_angle": "new_relationship" | "upsell" | "reactivation",
  "risk_flags": ["flag 1"]
}}

Rules:
- talking_points: exactly 3 items, specific to this contractor
- likely_product_needs: exactly 3 items, name specific GAF products
- outreach_angle: must be exactly one of "new_relationship", "upsell", or "reactivation"
- risk_flags: 0-3 items (can be empty list if no risks)"""

    response = await client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=600,
        temperature=0.3,
    )

    raw_json = response.choices[0].message.content
    parsed = json.loads(raw_json)
    return EnrichmentOutput(**parsed), raw_json


# ─────────────────────────────────────────────────────────────
# IDEMPOTENT UPSERT
# ─────────────────────────────────────────────────────────────

def upsert_enrichment(
    db,
    contractor_id: str,
    score: int,
    reasoning: str,
    web_research: str,
    ai_output: EnrichmentOutput,
    raw_response: str,
) -> bool:
    """
    Insert or update enrichment record for a contractor.

    Returns True if this is a new record, False if updated.

    WHY upsert: model/prompt improvements mean we re-enrich existing contractors.
    We want the latest intelligence, not a stack of stale versions.

    PRODUCTION PATH: in prod, keep a versioned history table (enrichment_history)
    so managers can compare how intelligence changed across prompt versions.
    The current table always holds the latest; history holds all previous.
    """
    now = datetime.now(timezone.utc).isoformat()
    model_version = os.getenv("OPENAI_MODEL", "gpt-4o")
    prompt_version = os.getenv("PROMPT_VERSION", "1.0.0")

    bonus = _compute_qualifier_bonus(web_research)

    existing = db.query(EnrichmentDB).filter(
        EnrichmentDB.contractor_id == contractor_id
    ).first()

    if existing:
        existing.opportunity_score    = score
        existing.score_reasoning      = reasoning
        existing.web_research_summary = web_research
        existing.qualifier_bonus      = bonus
        existing.talking_points       = ai_output.talking_points
        existing.likely_product_needs = ai_output.likely_product_needs
        existing.outreach_angle       = ai_output.outreach_angle
        existing.risk_flags           = ai_output.risk_flags
        existing.raw_llm_response     = raw_response
        existing.model_version        = model_version
        existing.prompt_version       = prompt_version
        existing.updated_at           = now
        db.commit()
        return False
    else:
        record = EnrichmentDB(
            id=str(uuid.uuid4()),
            contractor_id=contractor_id,
            opportunity_score=score,
            score_reasoning=reasoning,
            web_research_summary=web_research,
            qualifier_bonus=bonus,
            talking_points=ai_output.talking_points,
            likely_product_needs=ai_output.likely_product_needs,
            outreach_angle=ai_output.outreach_angle,
            risk_flags=ai_output.risk_flags,
            raw_llm_response=raw_response,
            model_version=model_version,
            prompt_version=prompt_version,
            created_at=now,
            updated_at=now,
        )
        db.add(record)
        db.commit()
        return True


# ─────────────────────────────────────────────────────────────
# STEP 4: SINGLE CONTRACTOR ENRICHMENT
# ─────────────────────────────────────────────────────────────

async def enrich_one(
    contractor: ContractorDB,
    openai_client: openai.AsyncOpenAI,
    http_client: httpx.AsyncClient,
    db_session,
) -> bool:
    """
    Full enrichment for a single contractor.
    Returns True on success, False on any failure.
    Errors are caught here — never bubble up to kill the batch.
    """
    try:
        print(f"[enricher] Processing: {contractor.name}")

        base_score, reasoning = compute_base_score(contractor)
        print(f"[enricher] Base score: {contractor.name} -> {base_score}/100")

        web_research, qualifier_bonus = await research_contractor_web(
            contractor, http_client
        )

        final_score = min(base_score + qualifier_bonus, 100)
        full_reasoning = reasoning.replace(
            f"Base: {base_score}/100",
            f"Base: {base_score}/100 | Web research bonus: +{qualifier_bonus} | Final: {final_score}/100",
        )

        ai_output, raw_response = await synthesize_with_openai(
            contractor, final_score, web_research, openai_client
        )

        upsert_enrichment(
            db=db_session,
            contractor_id=contractor.id,
            score=final_score,
            reasoning=full_reasoning,
            web_research=web_research,
            ai_output=ai_output,
            raw_response=raw_response,
        )

        print(f"[enricher] OK  {contractor.name} | score={final_score} | angle={ai_output.outreach_angle}")
        return True

    except openai.RateLimitError as e:
        print(f"[enricher] RATE LIMIT: {contractor.name} — {e}")
    except openai.APIError as e:
        print(f"[enricher] OPENAI ERROR: {contractor.name} — {e}")
    except ValidationError as e:
        print(f"[enricher] SCHEMA ERROR: {contractor.name} — {e}")
    except Exception as e:
        print(f"[enricher] UNEXPECTED: {contractor.name} — {e}")

    return False


# ─────────────────────────────────────────────────────────────
# STEP 5: BATCH PIPELINE WITH SEMAPHORE
# ─────────────────────────────────────────────────────────────

async def run_enrichment_pipeline(
    contractor_ids: list[str] | None = None,
) -> dict:
    """
    Main entry point. Enriches all un-enriched contractors by default,
    or a specific list of IDs for targeted re-enrichment.

    PRODUCTION PATH: This function becomes a Celery task.
    contractor_ids becomes the task payload.
    Each enrich_one() becomes its own sub-task with retry logic.
    Dead-letter queue captures permanently failed enrichments for manual review.
    """
    if not os.getenv("OPENAI_API_KEY"):
        raise EnvironmentError(
            "[enricher] OPENAI_API_KEY not set. "
            "Copy .env.example to .env and add your key."
        )

    init_db()
    db = SessionLocal()
    start = time.time()

    try:
        if contractor_ids:
            contractors = (
                db.query(ContractorDB)
                .filter(ContractorDB.id.in_(contractor_ids))
                .all()
            )
        else:
            enriched_ids = {
                e.contractor_id
                for e in db.query(EnrichmentDB.contractor_id).all()
            }
            contractors = [
                c for c in db.query(ContractorDB).all()
                if c.id not in enriched_ids
            ]

        if not contractors:
            print("[enricher] No contractors to enrich — all up to date")
            return {"enriched": 0, "failed": 0, "skipped": 0, "run_duration_seconds": 0}

        print(f"[enricher] Starting | {len(contractors)} contractors to process")

        openai_client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        concurrency = int(os.getenv("ENRICHMENT_CONCURRENCY", "5"))
        sem = asyncio.Semaphore(concurrency)

        async def enrich_with_limit(contractor):
            async with sem:
                async with httpx.AsyncClient() as http:
                    return await enrich_one(contractor, openai_client, http, db)

        results = await asyncio.gather(
            *[enrich_with_limit(c) for c in contractors],
            return_exceptions=True,
        )

        enriched = sum(1 for r in results if r is True)
        failed = sum(1 for r in results if r is False or isinstance(r, Exception))
        duration = round(time.time() - start, 1)

        for r in results:
            if isinstance(r, Exception):
                print(f"[enricher] EXCEPTION in gather: {r}")

        print(f"\n[enricher] Complete | enriched={enriched} | failed={failed} | duration={duration}s")
        return {
            "enriched": enriched,
            "failed": failed,
            "skipped": len(contractors) - enriched - failed,
            "run_duration_seconds": duration,
        }

    finally:
        db.close()


# ─────────────────────────────────────────────────────────────
# CLI ENTRYPOINT
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    result = asyncio.run(run_enrichment_pipeline())
    print(f"\n{'='*50}")
    print("ENRICHMENT SUMMARY")
    print(f"{'='*50}")
    for k, v in result.items():
        print(f"  {k}: {v}")
