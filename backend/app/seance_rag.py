"""Grounded Séance RAG engine: pure-Python BM25 retrieval, optional LLM persona, and deterministic extractive fallback."""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from .ast_analyzer import verify_citations
from .models import Citation, CommitNode, RepoSummary, SeanceAskResponse

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

_CAMEL_SPLIT_RE = re.compile(r"([a-z0-9])([A-Z])")
_TOKEN_SPLIT_RE = re.compile(r"[A-Za-z0-9]+")
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_EVOLUTION_MSG_RE = re.compile(r"\b(refactor|migrate|migration|revert|rewrite|rewrote|replace|replaced)\b", re.I)

_STOP_WORDS = frozenset(
    {
        "the",
        "is",
        "are",
        "was",
        "were",
        "a",
        "an",
        "of",
        "to",
        "in",
        "for",
        "on",
        "and",
        "or",
        "this",
        "that",
        "it",
        "with",
        "be",
        "as",
        "by",
        "at",
        "from",
        "do",
        "does",
        "did",
        "can",
        "could",
        "has",
        "have",
        "had",
        "what",
        "which",
        "who",
        "where",
        "when",
        "how",
        "why",
        "about",
        "into",
        "there",
    }
)

_HOTSPOT_INTENT = frozenset(
    {
        "hotspot",
        "hotspots",
        "fragile",
        "bug",
        "bugs",
        "bugfix",
        "crash",
        "race",
        "unstable",
        "risk",
        "risky",
        "broken",
        "security",
        "vulnerability",
        "cve",
        "broke",
        "fail",
    }
)

_GENESIS_INTENT = frozenset(
    {
        "genesis",
        "untouched",
        "original",
        "unchanged",
        "relic",
        "oldest",
        "survived",
        "initial",
        "started",
        "first",
        "remained",
    }
)

_EVOLUTION_INTENT = frozenset(
    {
        "rewrite",
        "rewritten",
        "drift",
        "theseus",
        "evolution",
        "architecture",
        "architectural",
        "changed",
        "deleted",
        "removed",
        "refactor",
        "migrate",
        "migrated",
        "summarize",
        "summary",
        "history",
        "overview",
        "explain",
    }
)


def get_llm_config() -> tuple[str | None, str | None, str | None, str | None]:
    """Resolve active LLM provider credentials dynamically from environment variables."""
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key:
        endpoint = os.getenv(
            "GROQ_API_BASE", "https://api.groq.com/openai/v1/chat/completions"
        ).strip()
        model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
        return "groq", groq_key, endpoint, model

    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if openai_key:
        endpoint = os.getenv(
            "OPENAI_API_BASE", "https://api.openai.com/v1/chat/completions"
        ).strip()
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
        return "openai", openai_key, endpoint, model

    return None, None, None, None


def get_llm_status() -> tuple[bool, str]:
    """Return (is_configured, provider_or_extractive)."""
    provider, _, _, _ = get_llm_config()
    if provider:
        return True, provider
    return False, "extractive"


def _tokenize(text: str) -> list[str]:
    """Tokenize camelCase, snake_case, paths, and prose into lowercase searchable terms."""
    if not text:
        return []
    separated = _CAMEL_SPLIT_RE.sub(r"\1 \2", text.replace("_", " "))
    raw = [tok.lower() for tok in _TOKEN_SPLIT_RE.findall(separated)]
    filtered = [tok for tok in raw if tok not in _STOP_WORDS]
    return filtered if filtered else raw


def _commit_document_tokens(commit: CommitNode) -> list[str]:
    """Build weighted token list for a single CommitNode."""
    msg_tokens = _tokenize(commit.message)
    file_tokens = _tokenize(" ".join(commit.files_changed))
    symbol_tokens = _tokenize(
        " ".join(sym for diff in commit.diffs for sym in diff.symbols)
    )
    author_tokens = _tokenize(commit.author)
    diff_tokens = _tokenize(" ".join(diff.diff_snippet for diff in commit.diffs))
    return (
        msg_tokens * 3
        + file_tokens * 2
        + symbol_tokens * 2
        + author_tokens
        + diff_tokens
    )


def _best_file_for_commit(commit: CommitNode, query_tokens: set[str]) -> str | None:
    """Pick the changed file in commit with highest lexical alignment to query_tokens."""
    if not commit.files_changed:
        return None
    diff_by_file = {d.file_path: d for d in commit.diffs}
    best_file = commit.files_changed[0]
    best_overlap = -1
    for fp in commit.files_changed:
        text = fp
        d = diff_by_file.get(fp)
        if d is not None:
            text += " " + " ".join(d.symbols) + " " + d.diff_snippet
        toks = set(_tokenize(text))
        overlap = len(toks & query_tokens)
        if overlap > best_overlap:
            best_overlap = overlap
            best_file = fp
    return best_file


def retrieve_relevant_commits(
    repo: RepoSummary,
    question: str,
    top_k: int = 5,
) -> list[tuple[CommitNode, float, str | None]]:
    """Rank commits using BM25 + deterministic archaeological intent boosts."""
    if not repo.commits or top_k <= 0:
        return []

    raw_query = _tokenize(question)
    if not raw_query:
        return []
    query_set = set(raw_query)

    has_hotspot_intent = bool(query_set & _HOTSPOT_INTENT)
    has_genesis_intent = bool(query_set & _GENESIS_INTENT)
    has_evolution_intent = bool(query_set & _EVOLUTION_INTENT)

    docs = [_commit_document_tokens(c) for c in repo.commits]
    n_docs = len(docs)
    avg_dl = sum(len(d) for d in docs) / max(1, n_docs)
    if avg_dl <= 0.0:
        avg_dl = 1.0

    doc_freqs: Counter[str] = Counter()
    doc_tf: list[Counter[str]] = []
    for doc in docs:
        tf = Counter(doc)
        doc_tf.append(tf)
        for term in tf:
            doc_freqs[term] += 1

    k1 = 1.5
    b = 0.75

    top_hotspot_files = [h.file_path for h in repo.hotspots[:2]]
    relic_files = {h.file_path for h in repo.hotspots if h.drift_score == 0.0}
    genesis_hash = repo.commits[-1].commit_hash

    scored: list[tuple[CommitNode, float, str | None]] = []
    for idx, commit in enumerate(repo.commits):
        tf_map = doc_tf[idx]
        dl = max(1, len(docs[idx]))
        bm25 = 0.0

        for term in raw_query:
            tf = tf_map.get(term, 0)
            if tf == 0:
                continue
            df = doc_freqs.get(term, 0)
            idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)
            denom = tf + k1 * (1.0 - b + b * (dl / avg_dl))
            bm25 += idf * ((tf * (k1 + 1.0)) / denom)

        boost = 0.0
        if has_hotspot_intent:
            if top_hotspot_files and top_hotspot_files[0] in commit.files_changed:
                boost += 1.6
            elif len(top_hotspot_files) > 1 and top_hotspot_files[1] in commit.files_changed:
                boost += 1.0
            if commit.is_bugfix:
                boost += 1.2

        if has_genesis_intent:
            if commit.commit_hash == genesis_hash:
                boost += 2.0
            if relic_files and (set(commit.files_changed) & relic_files):
                boost += 1.2

        if has_evolution_intent:
            churn = commit.additions + commit.deletions
            if churn > 0:
                boost += min(1.5, math.log1p(churn) * 0.25)
            if any(d.status == "deleted" for d in commit.diffs):
                boost += 1.2
            if _EVOLUTION_MSG_RE.search(commit.message):
                boost += 1.2

        total = bm25 + boost
        if total > 0.0:
            best_file = _best_file_for_commit(commit, query_set)
            scored.append((commit, round(total, 4), best_file))

    scored.sort(key=lambda item: (-item[1], item[0].date))
    return scored[:top_k]


def _summarize_diff_lines(diff_snippet: str) -> str:
    """Extract up to 2 compact changed code lines from a diff snippet for prose grounding."""
    if not diff_snippet:
        return ""
    interesting: list[str] = []
    for line in diff_snippet.splitlines():
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith(("+", "-")) and len(line.strip()) > 1:
            interesting.append(line.strip()[:100])
            if len(interesting) >= 2:
                break
    return " | ".join(interesting)


def build_extractive_answer(
    repo: RepoSummary,
    question: str,
    citations: list[Citation],
) -> str:
    """Synthesize a deterministic forensic archivist answer strictly from verified records."""
    if not repo.commits:
        return (
            f"The archive for **{repo.name}** is silent—zero commits have been ingested, "
            "so no architectural spirits can be summoned."
        )

    if not citations:
        top_hint = (
            f" Highest-churn file on record: `{repo.hotspots[0].file_path}`."
            if repo.hotspots
            else ""
        )
        return (
            f"The archive for **{repo.name}** ({repo.theseus_drift_score:.1f}% Ship-of-Theseus drift — "
            f"**{repo.drift_verdict}**) holds no verified commit record matching \"{question}\".{top_hint}"
        )

    query_set = set(_tokenize(question))
    lines: list[str] = [
        f"**Archive Verdict for {repo.name}** — `{repo.theseus_drift_score:.1f}%` rewritten since genesis "
        f"(**{repo.drift_verdict}** across `{repo.total_commits}` commits, `{repo.genesis_date[:10]}` -> `{repo.latest_date[:10]}`)."
    ]

    if (query_set & _HOTSPOT_INTENT) and repo.hotspots:
        top = repo.hotspots[0]
        lines.append(
            f"\n**Primary Fragility Hotspot:** `{top.file_path}` "
            f"({top.commit_count} commits, {top.bugfix_count} bug-fixes, {top.total_churn} lines churned, "
            f"{top.drift_score:.1f}% drift)."
        )

    if query_set & _GENESIS_INTENT:
        relics = [h.file_path for h in repo.hotspots if h.drift_score == 0.0]
        if relics:
            relic_list = ", ".join(f"`{fp}`" for fp in relics[:3])
            lines.append(f"\n**Untouched Genesis Relics (0.0% drift):** {relic_list}.")

    lines.append("\n**Verified Commit Evidence:**")
    commit_lookup = {c.commit_hash: c for c in repo.commits}
    for cit in citations:
        commit_obj = commit_lookup.get(cit.commit_hash)
        symbols: list[str] = []
        if commit_obj:
            for d in commit_obj.diffs:
                if d.file_path == cit.file_path and d.symbols:
                    symbols = d.symbols[:3]
                    break
        symbol_note = f" — symbols: `{', '.join(symbols)}`" if symbols else ""
        excerpt = _summarize_diff_lines(cit.diff_snippet)
        excerpt_note = f"\n  - Diff excerpt: `{excerpt}`" if excerpt else ""
        lines.append(
            f"- `[{cit.short_hash}]` ({cit.date[:10]} by **{cit.author}**) in `{cit.file_path}`: "
            f"\"{cit.commit_message}\"{symbol_note}{excerpt_note}"
        )

    return "\n".join(lines)


def _call_llm_responder(
    repo: RepoSummary,
    question: str,
    retrieved: list[tuple[CommitNode, float, str | None]],
    provider: str,
    api_key: str,
    endpoint: str,
    model: str,
    top_k: int,
) -> tuple[str, list[Citation]]:
    """Invoke Groq/OpenAI chat endpoint and verify every cited commit hash."""
    evidence_packets: list[dict[str, Any]] = []
    meta_by_hash: dict[str, tuple[float, str | None]] = {}
    for commit, score, best_file in retrieved:
        meta_by_hash[commit.commit_hash] = (score, best_file)
        evidence_packets.append(
            {
                "commit_hash": commit.commit_hash,
                "short_hash": commit.short_hash,
                "date": commit.date,
                "author": commit.author,
                "message": commit.message,
                "is_bugfix": commit.is_bugfix,
                "files_changed": commit.files_changed,
                "diffs": [
                    {
                        "file_path": d.file_path,
                        "status": d.status,
                        "symbols": d.symbols[:6],
                        "diff_snippet": d.diff_snippet[:800],
                    }
                    for d in commit.diffs[:3]
                ],
            }
        )

    hotspot_summary = [
        {
            "file_path": h.file_path,
            "commit_count": h.commit_count,
            "bugfix_count": h.bugfix_count,
            "drift_score": h.drift_score,
        }
        for h in repo.hotspots[:3]
    ]

    system_prompt = (
        "You are CodeSéance, a forensic software archaeologist summoning evidence from Git history. "
        "Answer ONLY using facts present in the provided verified commit evidence packets. "
        "NEVER invent commit hashes, file paths, authors, or dates. If evidence is insufficient, say so plainly. "
        "Respond strictly as JSON with keys: "
        '{"answer": "<concise markdown explanation referencing short hashes>", '
        '"cited_hashes": ["<exact commit_hash strings from the packets>"]}.'
    )
    user_payload = {
        "repository": {
            "name": repo.name,
            "theseus_drift_score": repo.theseus_drift_score,
            "drift_verdict": repo.drift_verdict,
            "total_commits": repo.total_commits,
            "top_hotspots": hotspot_summary,
        },
        "question": question,
        "evidence_commits": evidence_packets,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload)},
        ],
    }

    with httpx.Client(timeout=20.0) as client:
        resp = client.post(endpoint, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()

    content = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    cleaned = _FENCE_RE.sub("", str(content).strip()).strip()
    parsed = json.loads(cleaned)
    answer_text = str(parsed.get("answer") or "").strip()
    if not answer_text:
        raise ValueError(f"{provider} returned empty answer")

    raw_hashes = parsed.get("cited_hashes") or []
    candidates: list[dict[str, Any]] = []
    if isinstance(raw_hashes, list):
        for item in raw_hashes:
            h_str = str(item).strip()
            score, pref = meta_by_hash.get(h_str, (1.0, None))
            candidates.append(
                {
                    "commit_hash": h_str,
                    "file_path": pref,
                    "relevance_score": score,
                }
            )

    verified = verify_citations(
        repo,
        candidates,
        fallback_commits=[c for c, _, _ in retrieved],
        max_citations=top_k,
    )
    return answer_text, verified


def ask_seance(
    repo: RepoSummary,
    question: str,
    top_k: int = 5,
) -> SeanceAskResponse:
    """Answer a question strictly grounded in verified commit records and diffs."""
    clean_question = question.strip()
    retrieved = retrieve_relevant_commits(repo, clean_question, top_k=top_k)

    if not retrieved:
        answer = build_extractive_answer(repo, clean_question, [])
        return SeanceAskResponse(
            repo_id=repo.repo_id,
            question=clean_question,
            answer=answer,
            citations=[],
            mode="extractive",
            retrieved_commit_count=0,
        )

    extractive_candidates = [
        {
            "commit_hash": commit.commit_hash,
            "file_path": best_file,
            "relevance_score": score,
        }
        for commit, score, best_file in retrieved
    ]
    verified_extractive = verify_citations(
        repo,
        extractive_candidates,
        fallback_commits=[c for c, _, _ in retrieved],
        max_citations=top_k,
    )

    provider, api_key, endpoint, model = get_llm_config()
    if provider and api_key and endpoint and model:
        try:
            answer_text, verified_llm = _call_llm_responder(
                repo=repo,
                question=clean_question,
                retrieved=retrieved,
                provider=provider,
                api_key=api_key,
                endpoint=endpoint,
                model=model,
                top_k=top_k,
            )
            return SeanceAskResponse(
                repo_id=repo.repo_id,
                question=clean_question,
                answer=answer_text,
                citations=verified_llm,
                mode="llm",
                retrieved_commit_count=len(retrieved),
            )
        except Exception:
            pass

    answer_text = build_extractive_answer(repo, clean_question, verified_extractive)
    return SeanceAskResponse(
        repo_id=repo.repo_id,
        question=clean_question,
        answer=answer_text,
        citations=verified_extractive,
        mode="extractive",
        retrieved_commit_count=len(retrieved),
    )
