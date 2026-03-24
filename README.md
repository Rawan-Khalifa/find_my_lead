# FindMyLead

AI-powered B2B sales intelligence platform for a roofing materials distributor. Scrapes the GAF contractor directory, scores leads with a deterministic formula, enriches them with two AI APIs (Perplexity for live web research, OpenAI for structured synthesis), and serves everything through a FastAPI REST API so a sales rep walks into every call already prepared.

## Use Case

A roofing distributor's sales team needs to prioritize which contractors to call next. Today they manually search GAF's directory, Google each company, and guess who's worth calling. This system automates the entire workflow:

1. **Scrape** — pulls certified contractors from GAF's directory for a given ZIP + radius
2. **Score** — ranks each lead 0-100 based on GAF tier, proximity, specialties, reviews
3. **Research** — Perplexity searches the live web for hiring signals, BBB ratings, news
4. **Synthesize** — OpenAI generates talking points, product recommendations, and risk flags
5. **Serve** — API delivers a sorted, filterable lead list with one-click stage management

The rep opens the dashboard, sees their top 20 leads sorted by score, clicks into a lead, and gets a sales brief they can use on the call verbatim.

## Architecture

```
GAF Website ──→ Scraper ──→ Pydantic Validation ──→ SQLAlchemy Upsert ──→ contractors table
                                                                              │
                                                                              ▼
                                                          Enrichment Pipeline (per contractor)
                                                          ├─ Step 1: Deterministic scoring (Python)
                                                          ├─ Step 2: Web research (Perplexity)
                                                          └─ Step 3: Synthesis (OpenAI)
                                                                              │
                                                                              ▼
                                                                      enrichments table
                                                                              │
FastAPI ◄──────────────────────────────────────────────────── LEFT JOIN ──────┘
  ├─ GET  /leads              (list, filter, sort, paginate)
  ├─ GET  /leads/:id          (full profile + enrichment)
  ├─ PATCH /leads/:id/stage   (rep moves lead through pipeline)
  ├─ POST /pipeline/run       (trigger scrape + enrich in background)
  └─ GET  /pipeline/status    (poll progress)
```

## System Design Decisions

### 1. Two tables, not one

`contractors` holds scraped facts (source: GAF). `enrichments` holds AI output (source: our models). They never mix. This means we can re-enrich with a new model/prompt without re-scraping, roll back bad enrichments without losing source data, and audit exactly what the AI said via `raw_llm_response` + `model_version` + `prompt_version`.

### 2. Scoring is code, not AI

`opportunity_score` is a weighted Python formula (GAF tier, distance, specialties, reviews). The LLM only generates qualitative fields: talking points, product needs, risk flags. Scores are reproducible, explainable ("Master Elite +40, 2.1mi +30"), and never hallucinated. A rep can always ask "why this score?" and get a formula-based answer.

### 3. Deterministic IDs via MD5(name + address)

Contractor IDs are `MD5(name + address)` cast to UUID. Same contractor always gets the same ID. This is what makes the daily pipeline idempotent — upsert instead of blind insert, no duplicates ever.

### 4. Two AI APIs, each doing what it's best at

Perplexity (sonar model) does live web search — it finds current hiring posts, BBB ratings, and news that OpenAI's training cutoff can't reach. OpenAI does structured synthesis — takes everything we know and produces a validated JSON object matching our Pydantic schema. No overlap between the two.

### 5. Rep-owned state is protected

`pipeline_stage` (new → contacted → qualified → customer → disqualified) is set only by the rep through `PATCH /leads/:id/stage`. The scraper and enricher never touch it. A re-scrape refreshes data without resetting a rep's work.

### 6. Multi-strategy scraping with graceful degradation

GAF's site is JS-rendered (Coveo-powered search). The scraper tries four strategies in order:
1. **Direct Coveo API** — reverse-engineered the public search API, no browser needed, sub-second response
2. **Playwright XHR interception** — captures Coveo JSON mid-flight if the direct API fails
3. **DOM extraction** — multi-selector fallback from the rendered page
4. **Mock data** — for demo/testing only, never silently used in production

## Two Problems I Solved

### Problem 1: Duplicate contractors on repeated pipeline runs

**The issue:** The pipeline is designed to run daily. A naive insert creates a new row every run — 50 contractors × 30 days = 1,500 rows for 50 contractors. Worse, a rep's `pipeline_stage` would be lost because their lead now has 30 copies.

**The fix:** Deterministic ID generation. `MD5(name.lower() + address.lower())` produces the same UUID every time for the same contractor. The `upsert_contractor()` function checks if the ID exists: if yes, it updates scraped fields (phone, rating, tier) but **never overwrites `pipeline_stage`**. If no, it inserts with `pipeline_stage = "new"`. The pipeline is fully idempotent — run it 100 times, same result.

```python
def _deterministic_id(name: str, address: str) -> str:
    key = f"{name.lower().strip()}:{(address or '').lower().strip()}"
    return str(uuid.UUID(hashlib.md5(key.encode()).hexdigest()))
```

### Problem 2: Bot detection on GAF's JS-rendered directory

**The issue:** GAF uses Akamai EdgeSuite for bot detection. A standard `requests.get()` returns an empty shell — the contractor list is loaded client-side via Coveo's search API. Even headless Chromium gets blocked because Akamai fingerprints `navigator.webdriver`, missing `chrome.runtime`, and other automation signals.

**The fix:** Two-layer approach. **Primary:** reverse-engineered GAF's Coveo API — the search key is a public read-only token embedded in every page load. Call the API directly with a bounding-box geo-filter, compute haversine distances in Python, no browser at all. **Fallback:** Playwright with stealth patches injected via `add_init_script()` before any page JS runs — clears `webdriver` flag, fakes `navigator.languages`, stubs `chrome.runtime`, and patches `permissions.query`. XHR interception captures the Coveo response mid-flight. If that fails too, DOM extraction with multiple CSS selector strategies.

## Running Locally

```bash
git clone <repo> && cd find_my_lead
pip install -r requirements.txt
playwright install chromium          # only needed if Coveo API is blocked
cp .env.example .env                 # add your OPENAI_API_KEY and PERPLEXITY_API_KEY
```

```bash
# Run the API
uvicorn api.main:app --reload --port 8000

# Or run pipeline components individually
python ingestion/pipeline_runner.py  # scrape + upsert
python enrichment/enricher.py        # enrich all un-enriched contractors
```

API docs at `http://localhost:8000/docs`

## What Changes in Production

| MVP (now) | Production |
|---|---|
| SQLite | PostgreSQL + PgBouncer connection pooling |
| `BackgroundTasks` | Celery + Redis with retry/dead-letter queues |
| In-memory concurrency (`asyncio.Semaphore`) | Distributed task queue with per-task observability |
| Hardcoded ZIP coords | Google Maps Geocoding API |
| No auth | JWT via Clerk/Auth0 |
| No caching | Redis cache (7-day TTL on Perplexity results) |
| `print()` logging | Structured JSON logs → Datadog/ELK |
| Manual pipeline trigger | Cron / Airflow DAG with alerting |
| No schema migrations | Alembic |

## Tech Stack

Python 3.11+ · FastAPI · SQLAlchemy 2.x · Pydantic v2 · Playwright · OpenAI SDK · Perplexity API · httpx · SQLite (dev) / PostgreSQL (prod)
