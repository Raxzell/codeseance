"""Deterministic AST symbol extraction, Ship-of-Theseus drift scoring, and citation verification."""

from __future__ import annotations

import ast
import math
import re
from collections import Counter
from pathlib import PurePosixPath
from typing import Any, Sequence

from .models import (
    MAX_COMMITS,
    MAX_DIFF_CHARS,
    Citation,
    CommitNode,
    FileDiff,
    FileHotspot,
    RepoSummary,
)

MAX_DIFF_LINES = 40
MAX_SYMBOLS_PER_ITEM = 25

BUGFIX_PATTERN = re.compile(
    r"\b("
    r"fix|fixes|fixed|fixing|bug|bugfix|hotfix|patch|patched|"
    r"race|crash|crashes|regression|revert|reverted|leak|deadlock|"
    r"security|vuln|vulnerability|cve|broken|corrupt|"
    r"double[- ]charge|fixation"
    r")\b",
    re.IGNORECASE,
)

_PY_DEF_FALLBACK_RE = re.compile(
    r"^\s*(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(|"
    r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\s*[:(]",
    re.MULTILINE,
)

_JS_TS_SYMBOL_PATTERNS = (
    re.compile(
        r"\b(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\("
    ),
    re.compile(
        r"\b(?:export\s+(?:default\s+)?)?(?:abstract\s+)?class\s+([A-Za-z_$][A-Za-z0-9_$]*)\b"
    ),
    re.compile(
        r"\b(?:export\s+)?(?:interface|type)\s+([A-Za-z_$][A-Za-z0-9_$]*)\b"
    ),
    re.compile(
        r"\b(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][A-Za-z0-9_$]*)\s*=>"
    ),
    re.compile(
        r"^\s*(?:public|private|protected|static|async|\s)*([A-Za-z_$][A-Za-z0-9_$]*)\s*\([^)]*\)\s*(?::\s*[\w<>[\]|&\s]+)?\s*\{"
    ),
)

_JS_EXCLUDED_KEYWORDS = frozenset(
    {
        "if",
        "else",
        "for",
        "while",
        "switch",
        "catch",
        "return",
        "constructor",
        "try",
        "throw",
        "await",
        "typeof",
        "super",
    }
)

_LANGUAGE_MAP: dict[str, str] = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".sql": "SQL",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".json": "JSON",
    ".md": "Markdown",
    ".go": "Go",
    ".rs": "Rust",
    ".css": "CSS",
    ".html": "HTML",
    ".sh": "Shell",
    ".toml": "TOML",
}


def is_bugfix_commit(message: str) -> bool:
    """Return True if commit message describes a bug fix, security patch, or regression repair."""
    return bool(message and BUGFIX_PATTERN.search(message))


def truncate_diff(
    diff_snippet: str,
    max_chars: int = MAX_DIFF_CHARS,
    max_lines: int = MAX_DIFF_LINES,
) -> str:
    """Bound a diff hunk by both line count and character count."""
    if not diff_snippet or max_chars <= 0 or max_lines <= 0:
        return ""
    lines = diff_snippet.splitlines()
    was_cut = False
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        was_cut = True
    clipped = "\n".join(lines)
    if len(clipped) > max_chars or was_cut:
        suffix = "\n... [truncated]"
        if max_chars <= len(suffix):
            return clipped[:max_chars]
        keep = max_chars - len(suffix)
        return clipped[:keep].rstrip() + suffix
    return clipped


def detect_language(file_path: str) -> str | None:
    """Infer programming/config language from file extension."""
    suffix = PurePosixPath(file_path.replace("\\", "/")).suffix.lower()
    return _LANGUAGE_MAP.get(suffix)


def clamp_drift(value: float) -> float:
    """Clamp a drift percentage strictly to a finite float in [0.0, 100.0]."""
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return 0.0
    bounded = max(0.0, min(100.0, float(value)))
    return round(bounded, 2)


def get_drift_verdict(score: float) -> str:
    """Map a Ship-of-Theseus drift percentage to a human-readable architectural verdict."""
    bounded = clamp_drift(score)
    if bounded < 20.0:
        return "Preserved Relic"
    if bounded < 50.0:
        return "Evolving Vessel"
    if bounded < 80.0:
        return "Mutated Architecture"
    return "Complete Ship of Theseus"


def _strip_diff_markers(code_or_diff: str) -> str:
    """Extract clean added/context code lines from unified diff hunks."""
    cleaned_lines: list[str] = []
    for line in code_or_diff.splitlines():
        if line.startswith(("diff --git", "index ", "--- ", "+++ ", "@@ ", "\\ No newline")):
            continue
        if line.startswith("-") and not line.startswith("---"):
            continue
        if line.startswith("+") and not line.startswith("+++"):
            cleaned_lines.append(line[1:])
        elif line.startswith(" "):
            cleaned_lines.append(line[1:])
        else:
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def _dedupe_preserve(items: Sequence[str], limit: int = MAX_SYMBOLS_PER_ITEM) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
            if len(ordered) >= limit:
                break
    return ordered


def extract_symbols(file_path: str, code_or_diff: str) -> list[str]:
    """Extract function, class, and type symbols from Python (AST + fallback) or JS/TS code/diffs."""
    if not code_or_diff:
        return []

    suffix = PurePosixPath(file_path.replace("\\", "/")).suffix.lower()
    source = _strip_diff_markers(code_or_diff).replace("\x00", "")
    if not source.strip():
        return []

    if suffix == ".py":
        found: list[str] = []
        try:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    found.append(node.name)
        except (SyntaxError, ValueError, TypeError, RecursionError, MemoryError):
            pass
        if not found:
            for match in _PY_DEF_FALLBACK_RE.finditer(source):
                name = match.group(1) or match.group(2)
                if name:
                    found.append(name)
        return _dedupe_preserve(found)

    if suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
        found_js: list[str] = []
        for pattern in _JS_TS_SYMBOL_PATTERNS:
            for match in pattern.finditer(source):
                name = match.group(1)
                if name and name not in _JS_EXCLUDED_KEYWORDS:
                    found_js.append(name)
        return _dedupe_preserve(found_js)

    return []


def compute_file_drift(
    created_in_genesis: bool,
    was_deleted: bool,
    initial_lines: int,
    post_additions: int,
    post_deletions: int,
) -> float:
    """Compute a file's Ship-of-Theseus drift percentage strictly within [0.0, 100.0]."""
    if not created_in_genesis or was_deleted:
        return 100.0

    pa = max(0, int(post_additions))
    pd = max(0, int(post_deletions))
    if pa == 0 and pd == 0:
        return 0.0

    genesis_size = max(1, int(initial_lines))
    deletion_ratio = min(1.0, pd / genesis_size)
    addition_ratio = (pa / (genesis_size + pa)) if pa > 0 else 0.0
    raw = (0.65 * deletion_ratio + 0.35 * addition_ratio) * 100.0
    return clamp_drift(raw)


def _merge_file_list(commit: CommitNode) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for fp in commit.files_changed:
        norm = fp.strip()
        if norm and norm not in seen:
            seen.add(norm)
            ordered.append(norm)
    for diff in commit.diffs:
        norm = diff.file_path.strip()
        if norm and norm not in seen:
            seen.add(norm)
            ordered.append(norm)
    return ordered


def _enrich_commit(commit: CommitNode) -> CommitNode:
    """Normalize diff bounds, symbol extraction, bug-fix flags, and churn totals."""
    files_changed = _merge_file_list(commit)
    enriched_diffs: list[FileDiff] = []
    for diff in commit.diffs:
        bounded_snippet = truncate_diff(diff.diff_snippet)
        extracted = extract_symbols(diff.file_path, bounded_snippet)
        merged_symbols = _dedupe_preserve([*diff.symbols, *extracted])
        enriched_diffs.append(
            FileDiff(
                file_path=diff.file_path,
                status=diff.status,
                additions=max(0, int(diff.additions)),
                deletions=max(0, int(diff.deletions)),
                diff_snippet=bounded_snippet,
                symbols=merged_symbols,
            )
        )

    diff_adds = sum(d.additions for d in enriched_diffs)
    diff_dels = sum(d.deletions for d in enriched_diffs)
    total_adds = max(int(commit.additions), diff_adds)
    total_dels = max(int(commit.deletions), diff_dels)

    return CommitNode(
        commit_hash=commit.commit_hash,
        short_hash=commit.short_hash or commit.commit_hash[:7],
        author=commit.author,
        date=commit.date,
        message=commit.message,
        files_changed=files_changed,
        additions=max(0, total_adds),
        deletions=max(0, total_dels),
        is_bugfix=commit.is_bugfix or is_bugfix_commit(commit.message),
        diffs=enriched_diffs,
    )


def analyze_commits(
    commits: Sequence[CommitNode],
) -> tuple[list[CommitNode], list[FileHotspot], float, str, dict[str, int], str, str]:
    """Analyze up to MAX_COMMITS recent commits into timeline, hotspots, drift score, and languages."""
    if not commits:
        return [], [], 0.0, get_drift_verdict(0.0), {}, "", ""

    indexed = list(enumerate(commits))
    # Sort chronologically oldest -> newest, preserving original order as tie-breaker
    indexed.sort(key=lambda pair: (pair[1].date, pair[0]))
    capped_chronological = [_enrich_commit(c) for _, c in indexed[-MAX_COMMITS:]]

    file_stats: dict[str, dict[str, Any]] = {}
    lang_counter: Counter[str] = Counter()

    for idx, commit in enumerate(capped_chronological):
        is_genesis = idx == 0
        diffs_by_file: dict[str, list[FileDiff]] = {}
        for d in commit.diffs:
            diffs_by_file.setdefault(d.file_path, []).append(d)

        # Fallback distribution when a commit lists files_changed without per-file FileDiff stats
        files_without_diffs = [fp for fp in commit.files_changed if fp not in diffs_by_file]
        rem_adds = max(0, commit.additions - sum(d.additions for d in commit.diffs))
        rem_dels = max(0, commit.deletions - sum(d.deletions for d in commit.diffs))

        for pos, fp in enumerate(commit.files_changed):
            lang = detect_language(fp)
            if fp not in file_stats and lang:
                lang_counter[lang] += 1

            file_diffs = diffs_by_file.get(fp, [])
            if file_diffs:
                file_adds = sum(d.additions for d in file_diffs)
                file_dels = sum(d.deletions for d in file_diffs)
                statuses = [d.status for d in file_diffs]
                file_status = (
                    "deleted"
                    if "deleted" in statuses
                    else ("added" if "added" in statuses else statuses[-1])
                )
                commit_symbols = [sym for d in file_diffs for sym in d.symbols]
            else:
                n_no_diff = max(1, len(files_without_diffs))
                no_diff_idx = files_without_diffs.index(fp) if fp in files_without_diffs else 0
                file_adds = (rem_adds // n_no_diff) + (1 if no_diff_idx < (rem_adds % n_no_diff) else 0)
                file_dels = (rem_dels // n_no_diff) + (1 if no_diff_idx < (rem_dels % n_no_diff) else 0)
                file_status = "added" if is_genesis else "modified"
                commit_symbols = []

            if fp not in file_stats:
                created_in_genesis = is_genesis and file_status != "deleted"
                file_stats[fp] = {
                    "created_in_genesis": created_in_genesis,
                    "was_deleted": file_status == "deleted",
                    "initial_lines": max(1, file_adds) if created_in_genesis else 0,
                    "post_additions": 0 if created_in_genesis else file_adds,
                    "post_deletions": 0 if created_in_genesis else file_dels,
                    "commit_count": 1,
                    "bugfix_count": 1 if commit.is_bugfix else 0,
                    "total_churn": max(0, file_adds + file_dels),
                    "symbols": list(commit_symbols),
                    "last_modified": commit.date,
                }
            else:
                st = file_stats[fp]
                if st["was_deleted"] and file_status == "added":
                    # Deleted and re-created later: treat as completely replaced code
                    st["created_in_genesis"] = False
                    st["was_deleted"] = False
                elif file_status == "deleted":
                    st["was_deleted"] = True

                st["post_additions"] += max(0, file_adds)
                st["post_deletions"] += max(0, file_dels)
                st["commit_count"] += 1
                if commit.is_bugfix:
                    st["bugfix_count"] += 1
                st["total_churn"] += max(0, file_adds + file_dels)
                st["symbols"].extend(commit_symbols)
                st["last_modified"] = commit.date

    single_commit_repo = len(capped_chronological) <= 1
    hotspots: list[FileHotspot] = []
    weighted_drift_sum = 0.0
    total_weight = 0

    for fp, st in file_stats.items():
        if single_commit_repo:
            drift_score = 0.0
        else:
            drift_score = compute_file_drift(
                created_in_genesis=st["created_in_genesis"],
                was_deleted=st["was_deleted"],
                initial_lines=st["initial_lines"],
                post_additions=st["post_additions"],
                post_deletions=st["post_deletions"],
            )

        churn = max(0, int(st["total_churn"]))
        commit_count = max(1, int(st["commit_count"]))
        bugfix_count = max(0, min(commit_count, int(st["bugfix_count"])))
        hotspot_score = round(commit_count * 1.5 + bugfix_count * 3.0 + math.log1p(churn), 2)

        weight = max(1, int(st["initial_lines"]) + churn)
        weighted_drift_sum += drift_score * weight
        total_weight += weight

        hotspots.append(
            FileHotspot(
                file_path=fp,
                commit_count=commit_count,
                bugfix_count=bugfix_count,
                total_churn=churn,
                drift_score=drift_score,
                hotspot_score=max(0.0, hotspot_score),
                symbols=_dedupe_preserve(st["symbols"]),
                last_modified=st["last_modified"],
            )
        )

    hotspots.sort(key=lambda h: (-h.hotspot_score, -h.commit_count, -h.total_churn, h.file_path))

    if single_commit_repo or total_weight == 0:
        theseus_drift = 0.0
    else:
        theseus_drift = clamp_drift(weighted_drift_sum / total_weight)

    drift_verdict = get_drift_verdict(theseus_drift)
    languages = dict(sorted(lang_counter.items(), key=lambda item: (-item[1], item[0])))

    genesis_date = capped_chronological[0].date
    latest_date = capped_chronological[-1].date
    timeline_newest_first = list(reversed(capped_chronological))
    return (
        timeline_newest_first,
        hotspots,
        theseus_drift,
        drift_verdict,
        languages,
        genesis_date,
        latest_date,
    )


def build_verified_citation(
    commit: CommitNode,
    preferred_file: str | None = None,
    relevance_score: float = 1.0,
) -> Citation:
    """Construct a Citation strictly hydrated from a verified CommitNode."""
    valid_files = list(commit.files_changed)
    diff_by_file = {d.file_path: d for d in commit.diffs}

    chosen_file: str
    if preferred_file and preferred_file in valid_files:
        chosen_file = preferred_file
    elif commit.diffs and commit.diffs[0].file_path in valid_files:
        chosen_file = commit.diffs[0].file_path
    elif valid_files:
        chosen_file = valid_files[0]
    else:
        chosen_file = "(commit-level)"

    matched_diff = diff_by_file.get(chosen_file)
    if matched_diff and matched_diff.diff_snippet:
        snippet = truncate_diff(matched_diff.diff_snippet)
    elif commit.diffs:
        snippet = truncate_diff(commit.diffs[0].diff_snippet)
    else:
        snippet = ""

    clean_score = (
        round(max(0.0, float(relevance_score)), 4)
        if isinstance(relevance_score, (int, float)) and math.isfinite(float(relevance_score))
        else 0.0
    )

    return Citation(
        commit_hash=commit.commit_hash,
        short_hash=commit.short_hash,
        date=commit.date,
        author=commit.author,
        file_path=chosen_file,
        commit_message=commit.message,
        diff_snippet=snippet,
        relevance_score=clean_score,
    )


def _resolve_commit(
    token: str,
    full_map: dict[str, CommitNode],
    short_map: dict[str, CommitNode],
    all_commits: Sequence[CommitNode],
) -> CommitNode | None:
    key = token.strip().lower()
    if not key:
        return None
    if key in full_map:
        return full_map[key]
    if key in short_map:
        return short_map[key]
    if len(key) >= 7:
        prefix_matches = [c for c in all_commits if c.commit_hash.lower().startswith(key)]
        if len(prefix_matches) == 1:
            return prefix_matches[0]
    return None


def verify_citations(
    repo: RepoSummary,
    candidates: Sequence[dict[str, Any] | Citation | str],
    fallback_commits: Sequence[CommitNode] | None = None,
    max_citations: int = 5,
) -> list[Citation]:
    """Strip any fabricated or mismatched citations against the repo's verified commit index."""
    if max_citations <= 0 or not repo.commits:
        return []

    full_map: dict[str, CommitNode] = {}
    short_counts: Counter[str] = Counter()
    for commit in repo.commits:
        full_map[commit.commit_hash.lower()] = commit
        short_counts[commit.short_hash.lower()] += 1

    short_map: dict[str, CommitNode] = {
        commit.short_hash.lower(): commit
        for commit in repo.commits
        if short_counts[commit.short_hash.lower()] == 1
    }

    verified: list[Citation] = []
    seen_hashes: set[str] = set()

    for candidate in candidates:
        raw_hash = ""
        preferred_file: str | None = None
        score = 1.0

        if isinstance(candidate, Citation):
            raw_hash = candidate.commit_hash
            preferred_file = candidate.file_path
            score = candidate.relevance_score
        elif isinstance(candidate, dict):
            raw_hash = str(candidate.get("commit_hash") or candidate.get("short_hash") or "")
            raw_file = candidate.get("file_path")
            preferred_file = str(raw_file) if raw_file is not None else None
            raw_score = candidate.get("relevance_score", 1.0)
            score = float(raw_score) if isinstance(raw_score, (int, float)) else 1.0
        elif isinstance(candidate, str):
            raw_hash = candidate

        matched = _resolve_commit(raw_hash, full_map, short_map, repo.commits)
        if not matched or matched.commit_hash in seen_hashes:
            continue

        seen_hashes.add(matched.commit_hash)
        verified.append(
            build_verified_citation(
                matched,
                preferred_file=preferred_file,
                relevance_score=score,
            )
        )
        if len(verified) >= max_citations:
            return verified

    if not verified and fallback_commits:
        for idx, commit in enumerate(fallback_commits):
            matched = full_map.get(commit.commit_hash.lower())
            if not matched or matched.commit_hash in seen_hashes:
                continue
            seen_hashes.add(matched.commit_hash)
            verified.append(
                build_verified_citation(
                    matched,
                    relevance_score=max(0.1, round(1.0 - idx * 0.1, 2)),
                )
            )
            if len(verified) >= max_citations:
                break

    return verified
