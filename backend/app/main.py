"""FastAPI entrypoint for CodeSéance repository summoning and grounded séance Q&A."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .git_archaeologist import (
    InvalidRepoURLError,
    PresetNotFoundError,
    RepoIngestionError,
    get_summoned_repo,
    list_presets,
    repo_store,
    summon_repository,
)
from .models import (
    HealthResponse,
    PresetRepoInfo,
    RepoSummary,
    SeanceAskRequest,
    SeanceAskResponse,
    SummonRequest,
)
from .seance_rag import ask_seance, get_llm_status

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def _resolve_cors_origins() -> list[str]:
    origins = list(DEFAULT_CORS_ORIGINS)
    for env_key in ("FRONTEND_ORIGINS", "FRONTEND_URL"):
        raw = os.getenv(env_key, "").strip()
        if raw:
            for item in raw.split(","):
                cleaned = item.strip().rstrip("/")
                if cleaned and cleaned not in origins:
                    origins.append(cleaned)
    return origins


app = FastAPI(
    title="CodeSéance API",
    description="Summoning the ghosts of past commits to explain why legacy code exists.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_resolve_cors_origins(),
    allow_origin_regex=r"^https://.*\.vercel\.app$",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Return service readiness, LLM availability, and cached repository counts."""
    llm_configured, llm_provider = get_llm_status()
    return HealthResponse(
        status="ok",
        llm_configured=llm_configured,
        llm_provider=llm_provider,
        presets_available=len(list_presets()),
        summoned_repos_cached=repo_store.count(),
    )


@app.get("/api/presets", response_model=list[PresetRepoInfo])
def get_presets() -> list[PresetRepoInfo]:
    """Return the 3 bundled offline demo repositories."""
    return list_presets()


@app.post("/api/repo/summon", response_model=RepoSummary)
def summon_repo(payload: SummonRequest) -> RepoSummary:
    """Ingest a bundled preset ID or public GitHub URL and compute Ship-of-Theseus metrics."""
    try:
        return summon_repository(repo_url=payload.repo_url, preset_id=payload.preset_id)
    except PresetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidRepoURLError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RepoIngestionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/seance/ask", response_model=SeanceAskResponse)
def seance_ask(payload: SeanceAskRequest) -> SeanceAskResponse:
    """Answer a natural-language question strictly grounded in verified commit citations."""
    repo = get_summoned_repo(payload.repo_id)
    if repo is None:
        raise HTTPException(
            status_code=404,
            detail=f"Repository '{payload.repo_id}' has not been summoned. Summon a repository first.",
        )
    return ask_seance(repo, payload.question, top_k=payload.top_k)
