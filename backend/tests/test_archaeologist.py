"""Unit and local-git integration tests for Git Archaeologist & AST Analyzer."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.ast_analyzer import (  # noqa: E402
    analyze_commits,
    compute_file_drift,
    extract_symbols,
    is_bugfix_commit,
    truncate_diff,
    verify_citations,
)
from app.git_archaeologist import (  # noqa: E402
    InvalidRepoURLError,
    PresetNotFoundError,
    RepoIngestionError,
    RepoStore,
    _extract_commits_from_local_repo,
    list_presets,
    parse_github_url,
    summon_github_repo,
    summon_preset,
    summon_repository,
)
from app.models import MAX_COMMITS, MAX_DIFF_CHARS, CommitNode, FileDiff, SummonRequest  # noqa: E402


def test_list_presets_returns_three_valid_demos() -> None:
    presets = list_presets()
    assert len(presets) == 3
    ids = [p.preset_id for p in presets]
    assert ids == [
        "legacy-billing-monolith",
        "phoenix-auth-gateway",
        "haunted-cache-daemon",
    ]
    for preset in presets:
        assert 1 <= preset.commit_count <= MAX_COMMITS
        assert 0.0 <= preset.estimated_drift <= 100.0
        assert len(preset.sample_questions) >= 3


def test_summon_all_presets_offline_zero_network_or_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _forbid(*args, **kwargs):
        raise AssertionError("Preset summoning must never perform subprocess or network calls!")

    monkeypatch.setattr(subprocess, "run", _forbid)
    monkeypatch.setattr(httpx, "Client", _forbid)

    store = RepoStore()
    for preset in list_presets():
        summary = summon_preset(preset.preset_id, store=store)
        assert summary.repo_id == f"preset:{preset.preset_id}"
        assert summary.source_type == "preset"
        assert summary.total_commits == preset.commit_count
        assert len(summary.commits) == preset.commit_count
        assert 0.0 <= summary.theseus_drift_score <= 100.0
        assert summary.theseus_drift_score == preset.estimated_drift
        assert store.get(summary.repo_id) is summary


def test_legacy_billing_preset_forensic_narrative() -> None:
    store = RepoStore()
    summary = summon_preset("legacy-billing-monolith", store=store)
    hotspot_map = {h.file_path: h for h in summary.hotspots}

    # Untouched genesis relic
    assert hotspot_map["billing/config.py"].drift_score == 0.0
    assert "BillingSettings" in hotspot_map["billing/config.py"].symbols

    # Deleted post-genesis module
    assert hotspot_map["billing/queue_worker.py"].drift_score == 100.0

    # Primary bugfix hotspot
    assert summary.hotspots[0].file_path == "billing/ledger.py"
    assert summary.hotspots[0].bugfix_count >= 4
    assert "DecimalLedgerService" in hotspot_map["billing/ledger.py"].symbols
    assert summary.theseus_drift_score > 60.0


def test_phoenix_auth_and_haunted_cache_presets() -> None:
    store = RepoStore()
    auth = summon_preset("phoenix-auth-gateway", store=store)
    auth_hotspots = {h.file_path: h for h in auth.hotspots}
    assert auth_hotspots["src/config/constants.ts"].drift_score == 0.0
    assert auth.hotspots[0].file_path == "src/auth/session.ts"
    assert "JwtSessionManager" in auth_hotspots["src/auth/session.ts"].symbols
    assert "TypeScript" in auth.languages

    cache = summon_preset("haunted-cache-daemon", store=store)
    cache_hotspots = {h.file_path: h for h in cache.hotspots}
    assert cache_hotspots["wraith/protocol.py"].drift_score == 0.0
    assert "decode_frame" in cache_hotspots["wraith/protocol.py"].symbols
    assert cache.hotspots[0].file_path == "wraith/lru_store.py"


def test_unknown_preset_and_invalid_summon_request() -> None:
    with pytest.raises(PresetNotFoundError):
        summon_preset("nonexistent-phantom-repo")

    with pytest.raises(ValidationError):
        SummonRequest(repo_url="   ", preset_id="")

    with pytest.raises(InvalidRepoURLError):
        summon_repository(repo_url=None, preset_id=None)


@pytest.mark.parametrize(
    ("raw_url", "expected_owner", "expected_repo"),
    [
        ("https://github.com/fastapi/fastapi", "fastapi", "fastapi"),
        ("https://github.com/pallets/flask.git", "pallets", "flask"),
        ("https://github.com/org-1/my.repo_name/", "org-1", "my.repo_name"),
    ],
)
def test_parse_github_url_accepts_valid_public_urls(
    raw_url: str,
    expected_owner: str,
    expected_repo: str,
) -> None:
    owner, repo, clean_url = parse_github_url(raw_url)
    assert owner == expected_owner
    assert repo == expected_repo
    assert clean_url == f"https://github.com/{expected_owner}/{expected_repo}.git"


@pytest.mark.parametrize(
    "bad_url",
    [
        "",
        "http://github.com/fastapi/fastapi",
        "file:///etc/passwd",
        "ssh://git@github.com/fastapi/fastapi.git",
        "git://github.com/fastapi/fastapi.git",
        "https://gitlab.com/fastapi/fastapi",
        "https://user:pass@github.com/fastapi/fastapi",
        "https://github.com/fastapi/fastapi;rm -rf /",
        "https://github.com/fastapi/fastapi|cat",
        "https://github.com/fastapi/fastapi$(whoami)",
        "https://github.com/fastapi/../secret",
        "C:\\Windows\\System32",
    ],
)
def test_parse_github_url_rejects_unsafe_or_malformed_urls(bad_url: str) -> None:
    with pytest.raises(InvalidRepoURLError):
        parse_github_url(bad_url)


def test_local_git_repo_extraction_and_60_commit_cap(tmp_path: Path) -> None:
    repo_dir = tmp_path / "sample_repo"
    repo_dir.mkdir()

    def _git(*args: str) -> None:
        res = subprocess.run(
            ["git", "-C", str(repo_dir), *args],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.returncode == 0, f"git {args} failed: {res.stderr}"

    _git("init")
    _git("config", "user.name", "Ghost Test")
    _git("config", "user.email", "ghost@codeseance.dev")

    core_py = repo_dir / "core.py"
    relic_py = repo_dir / "relic.py"
    ui_ts = repo_dir / "widget.ts"

    relic_py.write_text("CONST_VERSION = 1\n", encoding="utf-8")
    core_py.write_text("def genesis_fn():\n    return 1\n", encoding="utf-8")
    _git("add", "relic.py", "core.py")
    _git("commit", "-m", "feat: genesis commit", "--date", "2024-01-01T00:00:00+00:00")

    # Add 64 more commits (total 65 -> extraction & analysis must cap at 60)
    for i in range(1, 65):
        if i == 10:
            ui_ts.write_text("export function renderGhost(): number { return 42; }\n", encoding="utf-8")
            _git("add", "widget.ts")
            _git("commit", "-m", "feat: add ts widget", "--date", f"2024-02-{i:02d}T12:00:00+00:00")
        elif i == 20:
            ui_ts.unlink()
            _git("add", "-A")
            _git("commit", "-m", "chore: delete ts widget", "--date", f"2024-02-{i:02d}T12:00:00+00:00")
        else:
            core_py.write_text(
                f"class EngineV{i}:\n    def compute_{i}(self):\n        return {i}\n",
                encoding="utf-8",
            )
            msg = f"fix: patch race #{i}" if i % 5 == 0 else f"chore: update core iteration {i}"
            day = (i % 28) + 1
            month = 3 + (i // 28)
            _git("add", "core.py")
            _git("commit", "-m", msg, "--date", f"2024-{month:02d}-{day:02d}T12:00:00+00:00")

    extracted = _extract_commits_from_local_repo(repo_dir, max_commits=MAX_COMMITS)
    assert len(extracted) == MAX_COMMITS

    timeline, hotspots, drift_score, verdict, languages, genesis_dt, latest_dt = analyze_commits(extracted)
    assert len(timeline) == MAX_COMMITS
    assert 0.0 <= drift_score <= 100.0
    assert verdict in {
        "Preserved Relic",
        "Evolving Vessel",
        "Mutated Architecture",
        "Complete Ship of Theseus",
    }
    assert genesis_dt <= latest_dt
    assert "Python" in languages

    hotspot_map = {h.file_path: h for h in hotspots}
    assert hotspot_map["core.py"].bugfix_count >= 1
    assert hotspot_map["widget.ts"].drift_score == 100.0


def test_github_summon_falls_back_to_api_and_handles_total_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_commit = CommitNode(
        commit_hash="a" * 40,
        short_hash="aaaaaaa",
        author="API Ghost",
        date="2025-05-01T10:00:00+00:00",
        message="fix: api fallback commit",
        files_changed=["app.py"],
        additions=10,
        deletions=2,
        diffs=[
            FileDiff(
                file_path="app.py",
                status="modified",
                additions=10,
                deletions=2,
                diff_snippet="+def api_handler():\n+    return True\n",
            )
        ],
    )

    monkeypatch.setattr(
        "app.git_archaeologist._ingest_via_git_clone",
        lambda _url: (_ for _ in ()).throw(RepoIngestionError("clone unavailable")),
    )
    monkeypatch.setattr(
        "app.git_archaeologist._ingest_via_github_api",
        lambda _owner, _repo: [fake_commit],
    )

    store = RepoStore()
    summary = summon_github_repo("https://github.com/octocat/Hello-World", store=store)
    assert summary.repo_id == "gh:octocat/Hello-World"
    assert summary.source_type == "github"
    assert summary.total_commits == 1
    assert summary.theseus_drift_score == 0.0
    assert store.get("gh:octocat/Hello-World") is summary

    monkeypatch.setattr(
        "app.git_archaeologist._ingest_via_github_api",
        lambda _owner, _repo: (_ for _ in ()).throw(RepoIngestionError("rate limited")),
    )
    with pytest.raises(RepoIngestionError):
        summon_github_repo("https://github.com/octocat/Hello-World", store=store)


def test_ast_analyzer_drift_and_symbol_edge_cases() -> None:
    # Empty and single-commit repositories -> 0.0 drift
    timeline, hotspots, drift, verdict, *_ = analyze_commits([])
    assert timeline == []
    assert hotspots == []
    assert drift == 0.0
    assert verdict == "Preserved Relic"

    # Untouched genesis vs deleted genesis vs post-genesis new file
    assert compute_file_drift(True, False, 50, 0, 0) == 0.0
    assert compute_file_drift(True, True, 50, 0, 50) == 100.0
    assert compute_file_drift(False, False, 0, 10, 0) == 100.0
    assert 0.0 < compute_file_drift(True, False, 20, 10, 10) < 100.0

    # Python AST + partial syntax fallback + JS/TS extraction
    py_diff = "@@ -1,3 +1,6 @@\n+class TokenBucket:\n+    async def acquire(self):\n+        pass\n"
    assert "TokenBucket" in extract_symbols("rate_limit.py", py_diff)
    assert "acquire" in extract_symbols("rate_limit.py", py_diff)

    partial_py_diff = "@@ -10,2 +10,3 @@\n+def broken_fragment(x:\n+    return x\n"
    assert "broken_fragment" in extract_symbols("fragment.py", partial_py_diff)
    assert "safe_fn" in extract_symbols("binary_blob.py", "+def safe_fn():\n+    pass\n\x00")

    ts_diff = (
        "+export interface UserSession { id: string; }\n"
        "+export const rotateToken = async (id: string) => id;\n"
        "+export function verifyJwt() { if (true) { return 1; } }\n"
    )
    ts_syms = extract_symbols("auth/session.ts", ts_diff)
    assert "UserSession" in ts_syms
    assert "rotateToken" in ts_syms
    assert "verifyJwt" in ts_syms
    assert "if" not in ts_syms

    assert is_bugfix_commit("hotfix: fix race crash") is True
    assert is_bugfix_commit("docs: update README badges") is False
    assert len(truncate_diff("x\n" * 5000)) <= MAX_DIFF_CHARS


def test_verify_citations_strips_hallucinations_and_tampered_fields() -> None:
    store = RepoStore()
    repo = summon_preset("legacy-billing-monolith", store=store)
    real = repo.commits[0]

    candidates = [
        {"commit_hash": "deadbeef" * 5, "author": "Fake Ghost", "file_path": "evil.py"},
        {
            "commit_hash": real.short_hash,  # resolved via short hash
            "author": "Tampered Author",
            "date": "1999-01-01",
            "file_path": "nonexistent/hallucinated.py",
            "relevance_score": 0.92,
        },
    ]

    verified = verify_citations(repo, candidates, max_citations=5)
    assert len(verified) == 1
    cited = verified[0]
    assert cited.commit_hash == real.commit_hash
    assert cited.short_hash == real.short_hash
    assert cited.author == real.author
    assert cited.date == real.date
    assert cited.file_path in real.files_changed
    assert cited.commit_message == real.message


def test_api_health_and_presets_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import app

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    client = TestClient(app)
    health_resp = client.get("/api/health")
    assert health_resp.status_code == 200
    health = health_resp.json()
    assert health["status"] == "ok"
    assert health["llm_configured"] is False
    assert health["llm_provider"] == "extractive"
    assert health["presets_available"] == 3

    presets_resp = client.get("/api/presets")
    assert presets_resp.status_code == 200
    presets = presets_resp.json()
    assert len(presets) == 3
    assert [p["preset_id"] for p in presets] == [
        "legacy-billing-monolith",
        "phoenix-auth-gateway",
        "haunted-cache-daemon",
    ]


def test_api_summon_preset_and_ask_extractive_roundtrip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.main import app

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def _forbid(*args, **kwargs):
        raise AssertionError("Extractive preset flow must never call network/LLM!")

    monkeypatch.setattr("app.git_archaeologist._ingest_via_git_clone", _forbid)
    monkeypatch.setattr("app.git_archaeologist._ingest_via_github_api", _forbid)
    monkeypatch.setattr("app.seance_rag._call_llm_responder", _forbid)

    client = TestClient(app)
    summon_resp = client.post("/api/repo/summon", json={"preset_id": "legacy-billing-monolith"})
    assert summon_resp.status_code == 200
    repo_data = summon_resp.json()
    valid_hashes = {c["commit_hash"] for c in repo_data["commits"]}

    questions = [
        "Why was the billing ledger rewritten from float to Decimal?",
        "Which file is the biggest bug hotspot?",
        "Why was queue_worker.py deleted from the architecture?",
        "Which module remained untouched since genesis?",
    ]
    for q in questions:
        ask_resp = client.post(
            "/api/seance/ask",
            json={"repo_id": repo_data["repo_id"], "question": q},
        )
        assert ask_resp.status_code == 200
        body = ask_resp.json()
        assert body["mode"] == "extractive"
        assert body["answer"].strip() != ""
        assert len(body["citations"]) >= 1
        for citation in body["citations"]:
            assert citation["commit_hash"] in valid_hashes


def test_api_error_status_codes() -> None:
    from app.main import app

    client = TestClient(app)

    assert client.post("/api/repo/summon", json={"preset_id": "does-not-exist"}).status_code == 404
    assert client.post("/api/repo/summon", json={"repo_url": "file:///etc/passwd"}).status_code == 400
    assert client.post("/api/repo/summon", json={}).status_code == 422
    assert (
        client.post(
            "/api/seance/ask",
            json={"repo_id": "preset:never-summoned", "question": "Why?"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/seance/ask",
            json={"repo_id": "preset:legacy-billing-monolith", "question": "   "},
        ).status_code
        == 422
    )


def test_seance_llm_mode_strips_hallucinated_hashes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.seance_rag import ask_seance

    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    repo = summon_preset("legacy-billing-monolith", store=RepoStore())
    real_commit = repo.commits[0]

    def _fake_post(self, url, **kwargs):
        payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "answer": f"Grounded response citing [{real_commit.short_hash}].",
                                "cited_hashes": [
                                    "deadbeef" * 5,
                                    real_commit.commit_hash,
                                    "12345678" * 5,
                                ],
                            }
                        )
                    }
                }
            ]
        }
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.Client, "post", _fake_post)

    result = ask_seance(repo, "Why was the ledger dead-letter retry state flushed?")
    assert result.mode == "llm"
    assert len(result.citations) == 1
    assert result.citations[0].commit_hash == real_commit.commit_hash
    assert result.citations[0].author == real_commit.author


def test_seance_llm_failure_falls_back_to_extractive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.seance_rag import ask_seance

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")

    repo = summon_preset("phoenix-auth-gateway", store=RepoStore())
    valid_hashes = {c.commit_hash for c in repo.commits}

    def _failing_post(self, url, **kwargs):
        raise httpx.ConnectError("Simulated network outage")

    monkeypatch.setattr(httpx.Client, "post", _failing_post)

    result = ask_seance(repo, "How did session handling fix the fixation vulnerability?")
    assert result.mode == "extractive"
    assert result.answer.strip() != ""
    assert len(result.citations) >= 1
    assert all(c.commit_hash in valid_hashes for c in result.citations)


def test_seance_off_topic_query_reports_no_matching_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.seance_rag import ask_seance

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    repo = summon_preset("haunted-cache-daemon", store=RepoStore())
    result = ask_seance(repo, "quantum banana smoothie recipe")
    assert result.mode == "extractive"
    assert result.citations == []
    assert result.retrieved_commit_count == 0
    assert "no verified commit record" in result.answer.lower()

