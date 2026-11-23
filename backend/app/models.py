"""Pydantic v2 data contracts for CodeSéance."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

MAX_COMMITS = 60
MAX_DIFF_CHARS = 2000


class FileDiff(BaseModel):
    """Structured diff metadata and bounded hunk excerpt for a single file."""

    file_path: str = Field(..., min_length=1)
    status: Literal["added", "modified", "deleted", "renamed"] = "modified"
    additions: int = Field(default=0, ge=0)
    deletions: int = Field(default=0, ge=0)
    diff_snippet: str = ""
    symbols: list[str] = Field(default_factory=list)

    @field_validator("diff_snippet", mode="before")
    @classmethod
    def _cap_diff_snippet(cls, value: object) -> str:
        if value is None:
            return ""
        text = str(value)
        if len(text) <= MAX_DIFF_CHARS:
            return text
        suffix = "\n... [truncated]"
        keep = max(0, MAX_DIFF_CHARS - len(suffix))
        return text[:keep] + suffix


class CommitNode(BaseModel):
    """Single ingested Git commit with churn stats and bounded file diffs."""

    commit_hash: str = Field(..., min_length=1)
    short_hash: str = Field(..., min_length=1)
    author: str = Field(..., min_length=1)
    date: str = Field(..., min_length=1)
    message: str = ""
    files_changed: list[str] = Field(default_factory=list)
    additions: int = Field(default=0, ge=0)
    deletions: int = Field(default=0, ge=0)
    is_bugfix: bool = False
    diffs: list[FileDiff] = Field(default_factory=list)


class FileHotspot(BaseModel):
    """Aggregated churn, bug-fix density, and Ship-of-Theseus drift for a file."""

    file_path: str = Field(..., min_length=1)
    commit_count: int = Field(..., ge=1)
    bugfix_count: int = Field(default=0, ge=0)
    total_churn: int = Field(default=0, ge=0)
    drift_score: float = Field(..., ge=0.0, le=100.0)
    hotspot_score: float = Field(..., ge=0.0)
    symbols: list[str] = Field(default_factory=list)
    last_modified: str = ""


class PresetRepoInfo(BaseModel):
    """Metadata for a bundled offline demo preset repository."""

    preset_id: str
    name: str
    tagline: str
    description: str
    language: str
    commit_count: int = Field(..., ge=0, le=MAX_COMMITS)
    estimated_drift: float = Field(..., ge=0.0, le=100.0)
    sample_questions: list[str] = Field(default_factory=list)


class RepoSummary(BaseModel):
    """Complete verified archaeological summary for a summoned repository."""

    repo_id: str
    name: str
    source_type: Literal["preset", "github"]
    source_url: Optional[str] = None
    total_commits: int = Field(..., ge=0, le=MAX_COMMITS)
    genesis_date: str = ""
    latest_date: str = ""
    theseus_drift_score: float = Field(..., ge=0.0, le=100.0)
    drift_verdict: str = "Preserved Relic"
    commits: list[CommitNode] = Field(default_factory=list)
    hotspots: list[FileHotspot] = Field(default_factory=list)
    languages: dict[str, int] = Field(default_factory=dict)


class Citation(BaseModel):
    """Verified evidence record linking an answer claim to a real commit diff."""

    commit_hash: str
    short_hash: str
    date: str
    author: str
    file_path: str
    commit_message: str
    diff_snippet: str = ""
    relevance_score: float = Field(default=0.0, ge=0.0)


class SummonRequest(BaseModel):
    """Request payload for summoning either a preset or public GitHub repo."""

    repo_url: Optional[str] = None
    preset_id: Optional[str] = None

    @model_validator(mode="after")
    def _validate_target(self) -> "SummonRequest":
        url = self.repo_url.strip() if self.repo_url else None
        preset = self.preset_id.strip() if self.preset_id else None
        self.repo_url = url or None
        self.preset_id = preset or None
        if not self.repo_url and not self.preset_id:
            raise ValueError("Provide either 'preset_id' or 'repo_url'.")
        return self


class SeanceAskRequest(BaseModel):
    """Natural-language séance query anchored to an already-summoned repo."""

    repo_id: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=15)

    @field_validator("repo_id", "question", mode="before")
    @classmethod
    def _require_non_blank(cls, value: object) -> str:
        text = str(value).strip() if value is not None else ""
        if not text:
            raise ValueError("Value must not be empty or whitespace-only.")
        return text


class SeanceAskResponse(BaseModel):
    """Grounded séance response with verified citations and execution mode."""

    repo_id: str
    question: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    mode: Literal["llm", "extractive"]
    retrieved_commit_count: int = Field(default=0, ge=0)


class HealthResponse(BaseModel):
    """Service readiness and LLM configuration status."""

    status: str = "ok"
    llm_configured: bool = False
    llm_provider: str = "extractive"
    presets_available: int = 3
    summoned_repos_cached: int = 0
