"""Hypothesis property-based tests proving zero-hallucination and drift invariants."""

from __future__ import annotations

import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.ast_analyzer import analyze_commits, compute_file_drift, verify_citations  # noqa: E402
from app.models import MAX_COMMITS, MAX_DIFF_CHARS, CommitNode, FileDiff, RepoSummary  # noqa: E402

_HEX_HASH_ST = st.text(alphabet="0123456789abcdef", min_size=40, max_size=40)
_FILE_PATH_ST = st.sampled_from(
    [
        "src/core.py",
        "src/auth.ts",
        "billing/ledger.py",
        "cache/store.py",
        "README.md",
        "infra/deploy.yml",
    ]
)
_STATUS_ST = st.sampled_from(["added", "modified", "deleted", "renamed"])
_DIFF_SNIPPET_ST = st.one_of(
    st.text(min_size=0, max_size=120),
    st.just("+def ghost_fn():\n+    return 1\n\x00"),
    st.just("+" + ("x" * 2400)),
)


@st.composite
def commit_graph_strategy(draw: st.DrawFn) -> list[CommitNode]:
    """Generate arbitrary commit graphs (0..75 commits) with unique SHA-1 hashes."""
    count = draw(st.integers(min_value=0, max_value=75))
    if count == 0:
        return []

    hashes = draw(st.lists(_HEX_HASH_ST, min_size=count, max_size=count, unique=True))
    base_time = datetime(2023, 1, 1, tzinfo=timezone.utc)
    commits: list[CommitNode] = []

    for idx, sha in enumerate(hashes):
        dt = (base_time + timedelta(days=idx)).isoformat()
        author = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=1, max_size=16)).strip() or "dev"
        message = draw(st.text(min_size=0, max_size=60))
        files = draw(st.lists(_FILE_PATH_ST, min_size=0, max_size=3, unique=True))

        diffs: list[FileDiff] = []
        total_adds = 0
        total_dels = 0
        for fp in files:
            adds = draw(st.integers(min_value=0, max_value=2000))
            dels = draw(st.integers(min_value=0, max_value=2000))
            status = draw(_STATUS_ST)
            snippet = draw(_DIFF_SNIPPET_ST)
            total_adds += adds
            total_dels += dels
            diffs.append(
                FileDiff(
                    file_path=fp,
                    status=status,
                    additions=adds,
                    deletions=dels,
                    diff_snippet=snippet,
                )
            )

        commits.append(
            CommitNode(
                commit_hash=sha,
                short_hash=sha[:7],
                author=author,
                date=dt,
                message=message,
                files_changed=files,
                additions=total_adds,
                deletions=total_dels,
                diffs=diffs,
            )
        )

    return commits


def _build_repo_from_commits(raw_commits: list[CommitNode]) -> RepoSummary:
    timeline, hotspots, drift, verdict, langs, genesis_dt, latest_dt = analyze_commits(raw_commits)
    return RepoSummary(
        repo_id="pbt:synthetic",
        name="synthetic/repo",
        source_type="preset",
        total_commits=len(timeline),
        genesis_date=genesis_dt,
        latest_date=latest_dt,
        theseus_drift_score=drift,
        drift_verdict=verdict,
        commits=timeline,
        hotspots=hotspots,
        languages=langs,
    )


@settings(max_examples=25, deadline=None)
@given(
    raw_commits=commit_graph_strategy(),
    fake_hashes=st.lists(_HEX_HASH_ST, min_size=0, max_size=8),
    pick_indices=st.lists(st.integers(min_value=0, max_value=74), min_size=0, max_size=6),
)
def test_property_citation_hashes_strict_membership(
    raw_commits: list[CommitNode],
    fake_hashes: list[str],
    pick_indices: list[int],
) -> None:
    """Property 1: Every verified citation hash MUST belong to the repo's verified commit set."""
    repo = _build_repo_from_commits(raw_commits)
    valid_map = {c.commit_hash: c for c in repo.commits}

    candidates: list[dict[str, object]] = [
        {"commit_hash": h, "author": "Hallucinated", "file_path": "ghost/fake.py"}
        for h in fake_hashes
    ]
    if repo.commits:
        for idx in pick_indices:
            target = repo.commits[idx % len(repo.commits)]
            candidates.append(
                {
                    "commit_hash": target.commit_hash,
                    "author": "Spoofed Author",
                    "date": "1970-01-01",
                    "file_path": "hallucinated/path.py",
                    "relevance_score": 0.85,
                }
            )

    fallback_commits = list(repo.commits[:3]) + [
        CommitNode(
            commit_hash="f" * 40,
            short_hash="fffffff",
            author="Rogue",
            date="2020-01-01",
            message="hallucinated fallback",
        )
    ]

    citations = verify_citations(repo, candidates, fallback_commits=fallback_commits, max_citations=5)
    seen: set[str] = set()
    for citation in citations:
        assert citation.commit_hash in valid_map
        assert citation.commit_hash not in seen
        seen.add(citation.commit_hash)

        real_commit = valid_map[citation.commit_hash]
        assert citation.short_hash == real_commit.short_hash
        assert citation.author == real_commit.author
        assert citation.date == real_commit.date
        assert citation.commit_message == real_commit.message


@settings(max_examples=25, deadline=None)
@given(
    raw_commits=commit_graph_strategy(),
    tampered_paths=st.lists(st.text(min_size=1, max_size=30), min_size=1, max_size=5),
)
def test_property_citation_file_paths_grounded(
    raw_commits: list[CommitNode],
    tampered_paths: list[str],
) -> None:
    """Property 2: Every citation file_path MUST exist in that commit's files_changed (or '(commit-level)' if empty)."""
    repo = _build_repo_from_commits(raw_commits)
    valid_map = {c.commit_hash: c for c in repo.commits}

    candidates = [
        {
            "commit_hash": c.commit_hash,
            "file_path": tampered_paths[idx % len(tampered_paths)],
        }
        for idx, c in enumerate(repo.commits[:6])
    ]
    citations = verify_citations(repo, candidates, max_citations=5)
    for citation in citations:
        real_commit = valid_map[citation.commit_hash]
        if real_commit.files_changed:
            assert citation.file_path in real_commit.files_changed
        else:
            assert citation.file_path == "(commit-level)"
        assert len(citation.diff_snippet) <= MAX_DIFF_CHARS


@settings(max_examples=25, deadline=None)
@given(raw_commits=commit_graph_strategy())
def test_property_theseus_drift_bounded_and_history_capped(raw_commits: list[CommitNode]) -> None:
    """Properties 3 & 4: Drift stays in [0.0, 100.0] and commit count is capped at <= 60."""
    repo = _build_repo_from_commits(raw_commits)

    assert repo.total_commits == len(repo.commits)
    assert len(repo.commits) <= MAX_COMMITS

    assert math.isfinite(repo.theseus_drift_score)
    assert 0.0 <= repo.theseus_drift_score <= 100.0
    if len(repo.commits) <= 1:
        assert repo.theseus_drift_score == 0.0

    for hotspot in repo.hotspots:
        assert math.isfinite(hotspot.drift_score)
        assert 0.0 <= hotspot.drift_score <= 100.0


@settings(max_examples=25, deadline=None)
@given(raw_commits=commit_graph_strategy())
def test_property_hotspot_invariants_and_monotonic_order(raw_commits: list[CommitNode]) -> None:
    """Property 6: Hotspots uphold non-negativity, bugfix bounds, and descending sort order."""
    repo = _build_repo_from_commits(raw_commits)

    for idx, hotspot in enumerate(repo.hotspots):
        assert hotspot.commit_count >= 1
        assert 0 <= hotspot.bugfix_count <= hotspot.commit_count
        assert hotspot.total_churn >= 0
        assert math.isfinite(hotspot.hotspot_score) and hotspot.hotspot_score >= 0.0
        if idx > 0:
            assert repo.hotspots[idx - 1].hotspot_score >= hotspot.hotspot_score


@settings(max_examples=25, deadline=None)
@given(
    created_in_genesis=st.booleans(),
    was_deleted=st.booleans(),
    initial_lines=st.integers(min_value=-1000, max_value=100_000),
    post_additions=st.integers(min_value=-1000, max_value=100_000),
    post_deletions=st.integers(min_value=-1000, max_value=100_000),
)
def test_property_compute_file_drift_edge_bounds(
    created_in_genesis: bool,
    was_deleted: bool,
    initial_lines: int,
    post_additions: int,
    post_deletions: int,
) -> None:
    """Direct fuzzing of Ship-of-Theseus file drift formula across boundary values."""
    score = compute_file_drift(
        created_in_genesis=created_in_genesis,
        was_deleted=was_deleted,
        initial_lines=initial_lines,
        post_additions=post_additions,
        post_deletions=post_deletions,
    )
    assert math.isfinite(score)
    assert 0.0 <= score <= 100.0
    if not created_in_genesis or was_deleted:
        assert score == 100.0
    elif post_additions <= 0 and post_deletions <= 0:
        assert score == 0.0
