"""
api/main.py

FastAPI application entry point.

Handles CORS configuration, DB initialization on startup, and
router registration. Run from the project root:

    uvicorn api.main:app --reload --port 8000

Docs auto-generated at /docs (Swagger) and /redoc (ReDoc).

PRODUCTION PATH:
    - Add rate limiting middleware (slowapi or similar)
    - Add structured logging middleware (JSON logs for Datadog/ELK)
    - Add auth middleware (JWT from Clerk/Auth0, not rolled by hand)
    - Replace SQLite with PostgreSQL via DATABASE_URL env var
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from db.database import init_db
from api.routes import leads, pipeline, stages

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run DB init on startup. Clean shutdown on exit."""
    init_db()
    yield


app = FastAPI(
    title="FindMyLead — Roofing Sales Intelligence API",
    description="AI-powered lead generation for roofing distributor sales teams.",
    version="1.0.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(leads.router,    prefix="/leads",    tags=["Leads"])
app.include_router(pipeline.router, prefix="/pipeline", tags=["Pipeline"])
app.include_router(stages.router,   prefix="/leads",    tags=["Pipeline Stages"])


@app.get("/health")
def health():
    return {"status": "ok", "service": "findmylead-api"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
