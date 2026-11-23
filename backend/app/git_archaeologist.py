"""Git repository ingestion: bundled offline demo presets, shallow git clone, and GitHub API fallback."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

import httpx

from .ast_analyzer import analyze_commits, truncate_diff
from .models import (
    MAX_COMMITS,
    CommitNode,
    FileDiff,
    PresetRepoInfo,
    RepoSummary,
)

MAX_DIFF_FILES_PER_COMMIT = 10
REPO_STORE_CAPACITY = 64

_GITHUB_URL_RE = re.compile(
    r"^https://github\.com/"
    r"([A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?)/"
    r"([A-Za-z0-9._-]{1,100}?)(?:\.git)?/?$"
)
_UNSAFE_URL_CHARS_RE = re.compile(r"[\s;|&$`<>'\"\\@?#]")
_DIFF_HEADER_RE = re.compile(r'^diff --git "?a/(.+?)"? "?b/(.+?)"?$')
_SUMMARY_CREATE_RE = re.compile(r"^\s*create mode \d+\s+(.+)$")
_SUMMARY_DELETE_RE = re.compile(r"^\s*delete mode \d+\s+(.+)$")
_SUMMARY_RENAME_RE = re.compile(r"^\s*rename\s+(.+)\s+\(\d+%\)$")


class InvalidRepoURLError(ValueError):
    """Raised when a supplied GitHub URL is malformed or fails security validation."""


class PresetNotFoundError(KeyError):
    """Raised when a requested demo preset ID does not exist."""


class RepoIngestionError(RuntimeError):
    """Raised when ingesting a public GitHub repository fails across all strategies."""


def parse_github_url(url: str) -> tuple[str, str, str]:
    """Validate and normalize a public HTTPS GitHub repository URL."""
    if not url or not isinstance(url, str):
        raise InvalidRepoURLError("Repository URL must be a non-empty string.")
    raw = url.strip()
    if _UNSAFE_URL_CHARS_RE.search(raw) or ".." in raw:
        raise InvalidRepoURLError(
            "Invalid GitHub URL. Provide a clean https://github.com/<owner>/<repo> URL."
        )
    match = _GITHUB_URL_RE.match(raw)
    if not match:
        raise InvalidRepoURLError(
            "Only public https://github.com/<owner>/<repo> URLs are permitted."
        )
    owner, repo = match.group(1), match.group(2)
    if repo in {".", ".."}:
        raise InvalidRepoURLError("Invalid GitHub repository name.")
    clean_url = f"https://github.com/{owner}/{repo}.git"
    return owner, repo, clean_url


def _c(
    commit_hash: str,
    author: str,
    date: str,
    message: str,
    diffs: list[tuple[str, str, int, int, str]],
) -> CommitNode:
    """Helper to build rich offline fixture CommitNode entries concisely."""
    file_diffs = [
        FileDiff(
            file_path=fp,
            status=status,  # type: ignore[arg-type]
            additions=adds,
            deletions=dels,
            diff_snippet=snippet,
        )
        for fp, status, adds, dels, snippet in diffs
    ]
    return CommitNode(
        commit_hash=commit_hash,
        short_hash=commit_hash[:7],
        author=author,
        date=date,
        message=message,
        files_changed=[d.file_path for d in file_diffs],
        additions=sum(d.additions for d in file_diffs),
        deletions=sum(d.deletions for d in file_diffs),
        diffs=file_diffs,
    )


_PRESET_DEFINITIONS: dict[str, dict[str, Any]] = {
    "legacy-billing-monolith": {
        "name": "Chronos Billing Engine",
        "tagline": "Python / FastAPI Ledger Haunted by Float Rounding & Premature Microservices",
        "description": (
            "A 12-commit forensic trail of an evolving fintech billing core: witness the shift from "
            "floating-point invoices to Decimal math, a midnight double-charge race hotfix, raw SQL "
            "remediation, and the eventual teardown of an over-engineered RabbitMQ queue split."
        ),
        "language": "Python",
        "sample_questions": [
            "Why was the billing ledger rewritten from float to Decimal?",
            "Which file is the biggest bug hotspot and what broke?",
            "Why was queue_worker.py deleted from the architecture?",
            "Which module has remained untouched since the genesis commit?",
        ],
        "commits": [
            _c(
                "1a09f2c8d3b4e5a678901234567890abcdef0101",
                "Ada Vance",
                "2023-03-14T09:15:00+00:00",
                "feat: genesis commit for Chronos billing config, ledger, and sqlite storage",
                [
                    (
                        "billing/config.py",
                        "added",
                        18,
                        0,
                        "@@ -0,0 +1,10 @@\n"
                        "+CURRENCY = 'USD'\n"
                        "+TAX_PRECISION = 2\n"
                        "+class BillingSettings:\n"
                        "+    retry_limit = 3\n"
                        "+    grace_period_days = 7\n",
                    ),
                    (
                        "billing/ledger.py",
                        "added",
                        24,
                        0,
                        "@@ -0,0 +1,10 @@\n"
                        "+def calculate_invoice_total(subtotal: float, tax_rate: float) -> float:\n"
                        "+    return round(subtotal * (1.0 + tax_rate), 2)\n"
                        "+\n"
                        "+def charge_customer(account_id: str, amount: float) -> dict:\n"
                        "+    return {'account_id': account_id, 'charged': amount}\n",
                    ),
                    (
                        "billing/db.py",
                        "added",
                        20,
                        0,
                        "@@ -0,0 +1,8 @@\n"
                        "+import sqlite3\n"
                        "+def fetch_account_balance(conn, account_id: str):\n"
                        "+    query = f\"SELECT balance FROM accounts WHERE id = '{account_id}'\"\n"
                        "+    return conn.execute(query).fetchone()\n",
                    ),
                ],
            ),
            _c(
                "2b18e3d7c4a5f607891234567890abcdef0202",
                "Marcus Thorne",
                "2023-05-02T14:40:00+00:00",
                "fix: patch penny rounding drift on split-tax float invoices",
                [
                    (
                        "billing/ledger.py",
                        "modified",
                        8,
                        4,
                        "@@ -1,4 +1,8 @@\n"
                        "-def calculate_invoice_total(subtotal: float, tax_rate: float) -> float:\n"
                        "-    return round(subtotal * (1.0 + tax_rate), 2)\n"
                        "+def calculate_invoice_total(subtotal: float, tax_rate: float) -> float:\n"
                        "+    # Temporary epsilon nudge for IEEE-754 half-cent truncation\n"
                        "+    raw = (subtotal * 100.0) * (1.0 + tax_rate)\n"
                        "+    return round((raw + 1e-9) / 100.0, 2)\n",
                    ),
                ],
            ),
            _c(
                "3c29d4e6b5f708192034567890abcdef0303",
                "Elena Rostova",
                "2023-07-19T18:05:00+00:00",
                "fix(security): parameterize SQL queries to close account lookup injection",
                [
                    (
                        "billing/db.py",
                        "modified",
                        10,
                        6,
                        "@@ -1,6 +1,10 @@\n"
                        " def fetch_account_balance(conn, account_id: str):\n"
                        "-    query = f\"SELECT balance FROM accounts WHERE id = '{account_id}'\"\n"
                        "-    return conn.execute(query).fetchone()\n"
                        "+    query = \"SELECT balance FROM accounts WHERE id = ?\"\n"
                        "+    return conn.execute(query, (account_id,)).fetchone()\n",
                    ),
                ],
            ),
            _c(
                "4d3af5c8a6e9102837465564738291abcdef0404",
                "Marcus Thorne",
                "2023-10-11T11:20:00+00:00",
                "feat: add Stripe webhook receiver for async settlement events",
                [
                    (
                        "billing/webhooks.py",
                        "added",
                        28,
                        0,
                        "@@ -0,0 +1,10 @@\n"
                        "+def handle_stripe_webhook(payload: dict) -> str:\n"
                        "+    event_type = payload.get('type')\n"
                        "+    if event_type == 'invoice.paid':\n"
                        "+        return 'settled'\n"
                        "+    return 'ignored'\n",
                    ),
                ],
            ),
            _c(
                "5e4b06d9b7f8213948576675849302abcdef0505",
                "Ada Vance",
                "2024-01-08T03:45:00+00:00",
                "hotfix: prevent double-charge race condition with idempotency lock",
                [
                    (
                        "billing/ledger.py",
                        "modified",
                        18,
                        6,
                        "@@ -6,5 +6,14 @@\n"
                        "-def charge_customer(account_id: str, amount: float) -> dict:\n"
                        "-    return {'account_id': account_id, 'charged': amount}\n"
                        "+_PROCESSED_KEYS: set[str] = set()\n"
                        "+def charge_customer(account_id: str, amount: float, idempotency_key: str) -> dict:\n"
                        "+    if idempotency_key in _PROCESSED_KEYS:\n"
                        "+        raise RuntimeError('Duplicate charge blocked')\n"
                        "+    _PROCESSED_KEYS.add(idempotency_key)\n"
                        "+    return {'account_id': account_id, 'charged': amount, 'key': idempotency_key}\n",
                    ),
                ],
            ),
            _c(
                "6f5c17e0c8a9324059687786950413abcdef0606",
                "Devon Patel",
                "2024-04-22T16:30:00+00:00",
                "feat: extract async billing queue_worker for RabbitMQ microservice split",
                [
                    (
                        "billing/queue_worker.py",
                        "added",
                        36,
                        0,
                        "@@ -0,0 +1,11 @@\n"
                        "+class BillingQueueWorker:\n"
                        "+    def __init__(self, broker_url: str):\n"
                        "+        self.broker_url = broker_url\n"
                        "+\n"
                        "+    def publish_charge_job(self, invoice_id: str) -> None:\n"
                        "+        # Dispatches billing event to external RabbitMQ exchange\n"
                        "+        pass\n",
                    ),
                ],
            ),
            _c(
                "706d28f1d9b0435160798897061524abcdef0707",
                "Ada Vance",
                "2024-07-30T10:12:00+00:00",
                "refactor!: rewrite billing ledger from float to exact Decimal arithmetic",
                [
                    (
                        "billing/ledger.py",
                        "modified",
                        32,
                        22,
                        "@@ -1,14 +1,18 @@\n"
                        "+from decimal import Decimal, ROUND_HALF_UP\n"
                        "-\n"
                        "-def calculate_invoice_total(subtotal: float, tax_rate: float) -> float:\n"
                        "-    raw = (subtotal * 100.0) * (1.0 + tax_rate)\n"
                        "-    return round((raw + 1e-9) / 100.0, 2)\n"
                        "+class DecimalLedgerService:\n"
                        "+    def calculate_invoice_total(self, subtotal: Decimal, tax_rate: Decimal) -> Decimal:\n"
                        "+        total = subtotal * (Decimal('1') + tax_rate)\n"
                        "+        return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)\n",
                    ),
                ],
            ),
            _c(
                "817e39a2e0c1546271809908172635abcdef0808",
                "Elena Rostova",
                "2024-11-04T21:05:00+00:00",
                "fix(security): enforce HMAC webhook signature verification and replay window",
                [
                    (
                        "billing/webhooks.py",
                        "modified",
                        20,
                        6,
                        "@@ -1,6 +1,13 @@\n"
                        "+import hmac, hashlib\n"
                        "+def verify_webhook_signature(secret: bytes, payload: bytes, sig: str) -> bool:\n"
                        "+    expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()\n"
                        "+    return hmac.compare_digest(expected, sig)\n"
                        "+\n"
                        " def handle_stripe_webhook(payload: dict) -> str:\n"
                        "     event_type = payload.get('type')\n",
                    ),
                ],
            ),
            _c(
                "928f40b3f1d2657382910019283746abcdef0909",
                "Elena Rostova",
                "2025-02-17T13:50:00+00:00",
                "refactor: replace raw sqlite queries with parameterized AccountRepository",
                [
                    (
                        "billing/db.py",
                        "modified",
                        28,
                        16,
                        "@@ -1,10 +1,14 @@\n"
                        "-import sqlite3\n"
                        "-def fetch_account_balance(conn, account_id: str):\n"
                        "+class AccountRepository:\n"
                        "+    def __init__(self, session_factory):\n"
                        "+        self.session_factory = session_factory\n"
                        "+\n"
                        "+    def fetch_account_balance(self, account_id: str):\n"
                        "+        with self.session_factory() as session:\n"
                        "+            return session.get_balance(account_id)\n",
                    ),
                ],
            ),
            _c(
                "a39051c402e3768493021120394857abcdef1010",
                "Marcus Thorne",
                "2025-06-05T09:00:00+00:00",
                "revert: remove premature RabbitMQ queue_worker to restore transactional consistency",
                [
                    (
                        "billing/queue_worker.py",
                        "deleted",
                        0,
                        36,
                        "@@ -1,11 +0,0 @@\n"
                        "-class BillingQueueWorker:\n"
                        "-    # Removed: out-of-order queue retries caused orphaned ledger entries\n",
                    ),
                ],
            ),
            _c(
                "b4a162d513f4879504132231405968abcdef1111",
                "Ada Vance",
                "2025-08-29T15:18:00+00:00",
                "fix: guard ledger idempotency cache against concurrent retry deadlock",
                [
                    (
                        "billing/ledger.py",
                        "modified",
                        16,
                        5,
                        "@@ -10,5 +10,12 @@\n"
                        "+import threading\n"
                        "+_LEDGER_LOCK = threading.Lock()\n"
                        " class DecimalLedgerService:\n"
                        "+    def execute_idempotent_charge(self, account_id: str, amount: Decimal, key: str) -> dict:\n"
                        "+        with _LEDGER_LOCK:\n"
                        "+            return {'account_id': account_id, 'amount': str(amount), 'key': key}\n",
                    ),
                ],
            ),
            _c(
                "c5b273e62405980615243342516079abcdef1212",
                "Devon Patel",
                "2025-10-19T12:42:00+00:00",
                "fix: flush dead-letter retry state when ledger settlement rolls back",
                [
                    (
                        "billing/ledger.py",
                        "modified",
                        12,
                        4,
                        "@@ -18,4 +18,10 @@\n"
                        " class DecimalLedgerService:\n"
                        "+    def rollback_pending_charge(self, key: str) -> bool:\n"
                        "+        with _LEDGER_LOCK:\n"
                        "+            return True\n",
                    ),
                ],
            ),
        ],
    },
    "phoenix-auth-gateway": {
        "name": "Specter Auth Gateway",
        "tagline": "TypeScript Auth Edge Migrating from MD5 Cookies to OAuth2 PKCE",
        "description": (
            "An 11-commit security evolution tracing an authentication gateway from brittle MD5 "
            "cookies to HS256 JWTs, surviving a session-fixation vulnerability, CORS wildcard leaks, "
            "and finally adopting OAuth2 PKCE with refresh token rotation."
        ),
        "language": "TypeScript",
        "sample_questions": [
            "How did session handling evolve to fix the session fixation vulnerability?",
            "Why was the CORS middleware patched?",
            "Which TypeScript file is the primary bug hotspot?",
            "What configuration file survived untouched since genesis?",
        ],
        "commits": [
            _c(
                "d10011a2b3c4d5e6f7081920a1b2c3d4e5f60101",
                "Nadia Chen",
                "2023-07-02T10:00:00+00:00",
                "feat: genesis commit for auth constants, MD5 password util, and cookie sessions",
                [
                    (
                        "src/config/constants.ts",
                        "added",
                        14,
                        0,
                        "@@ -0,0 +1,6 @@\n"
                        "+export const AUTH_HEADER = 'Authorization';\n"
                        "+export const TOKEN_PREFIX = 'Bearer ';\n"
                        "+export interface AuthConfig { issuer: string; audience: string; }\n",
                    ),
                    (
                        "src/auth/password.ts",
                        "added",
                        16,
                        0,
                        "@@ -0,0 +1,6 @@\n"
                        "+import crypto from 'crypto';\n"
                        "+export function hashPassword(raw: string): string {\n"
                        "+  return crypto.createHash('md5').update(raw).digest('hex');\n"
                        "+}\n",
                    ),
                    (
                        "src/auth/session.ts",
                        "added",
                        24,
                        0,
                        "@@ -0,0 +1,8 @@\n"
                        "+const COOKIE_STORE = new Map<string, string>();\n"
                        "+export function createSession(userId: string, sid: string): string {\n"
                        "+  COOKIE_STORE.set(sid, userId);\n"
                        "+  return sid;\n"
                        "+}\n",
                    ),
                ],
            ),
            _c(
                "d20022b3c4d5e6f7081920a1b2c3d4e5f60202",
                "Liam O'Connor",
                "2023-09-14T15:25:00+00:00",
                "feat: introduce CORS middleware for SPA client portal",
                [
                    (
                        "src/middleware/cors.ts",
                        "added",
                        18,
                        0,
                        "@@ -0,0 +1,6 @@\n"
                        "+export function applyCorsHeaders(headers: Record<string, string>): void {\n"
                        "+  headers['Access-Control-Allow-Origin'] = '*';\n"
                        "+  headers['Access-Control-Allow-Credentials'] = 'true';\n"
                        "+}\n",
                    ),
                ],
            ),
            _c(
                "d30033c4d5e6f7081920a1b2c3d4e5f60303",
                "Nadia Chen",
                "2023-11-28T20:10:00+00:00",
                "fix(security): forbid wildcard CORS origin when credentials are enabled",
                [
                    (
                        "src/middleware/cors.ts",
                        "modified",
                        12,
                        4,
                        "@@ -1,4 +1,9 @@\n"
                        "-export function applyCorsHeaders(headers: Record<string, string>): void {\n"
                        "-  headers['Access-Control-Allow-Origin'] = '*';\n"
                        "+const ALLOWED_ORIGINS = new Set(['https://app.codeseance.dev']);\n"
                        "+export function applyCorsHeaders(origin: string, headers: Record<string, string>): void {\n"
                        "+  if (ALLOWED_ORIGINS.has(origin)) {\n"
                        "+    headers['Access-Control-Allow-Origin'] = origin;\n"
                        "+  }\n",
                    ),
                ],
            ),
            _c(
                "d40044d5e6f7081920a1b2c3d4e5f60404",
                "Samira Al-Mansoor",
                "2024-02-09T11:45:00+00:00",
                "fix(security): upgrade password hashing from MD5 to salted SHA-256",
                [
                    (
                        "src/auth/password.ts",
                        "modified",
                        14,
                        8,
                        "@@ -1,5 +1,8 @@\n"
                        "+export function hashPassword(raw: string, salt: string): string {\n"
                        "+  return crypto.scryptSync(raw, salt, 64).toString('hex');\n"
                        "+}\n",
                    ),
                ],
            ),
            _c(
                "d50055e6f7081920a1b2c3d4e5f60505",
                "Nadia Chen",
                "2024-05-03T08:30:00+00:00",
                "refactor: migrate stateful cookie store to stateless HS256 JWT sessions",
                [
                    (
                        "src/auth/session.ts",
                        "modified",
                        26,
                        18,
                        "@@ -1,8 +1,11 @@\n"
                        "+export interface SessionClaims { sub: string; jti: string; exp: number; }\n"
                        "+export class JwtSessionManager {\n"
                        "+  issueToken(userId: string): string {\n"
                        "+    return `jwt.${userId}.sig`;\n"
                        "+  }\n"
                        "+}\n",
                    ),
                ],
            ),
            _c(
                "d60066f7081920a1b2c3d4e5f60606",
                "Samira Al-Mansoor",
                "2024-07-16T23:55:00+00:00",
                "hotfix(cve): regenerate jti on login to remediate session fixation vulnerability",
                [
                    (
                        "src/auth/session.ts",
                        "modified",
                        14,
                        4,
                        "@@ -3,5 +3,9 @@\n"
                        " export class JwtSessionManager {\n"
                        "+  rotateSessionId(priorJti: string): string {\n"
                        "+    // Invalidate pre-auth session identifier to block fixation\n"
                        "+    return crypto.randomUUID();\n"
                        "+  }\n",
                    ),
                ],
            ),
            _c(
                "d70077a81920b1c2d3e4f506172839a4b5c60707",
                "Liam O'Connor",
                "2024-10-21T14:15:00+00:00",
                "fix: reject reused refresh tokens after password reset",
                [
                    (
                        "src/auth/session.ts",
                        "modified",
                        12,
                        3,
                        "@@ -8,4 +8,9 @@\n"
                        "+  revokeFamily(familyId: string): boolean {\n"
                        "+    return Boolean(familyId);\n"
                        "+  }\n",
                    ),
                ],
            ),
            _c(
                "d80088b92031c2d3e4f506172839a4b5c60808",
                "Samira Al-Mansoor",
                "2025-01-19T17:40:00+00:00",
                "refactor!: switch password verifier to Argon2id with legacy scrypt migration",
                [
                    (
                        "src/auth/password.ts",
                        "modified",
                        18,
                        10,
                        "@@ -1,6 +1,10 @@\n"
                        "+export async function verifyAndUpgradeHash(raw: string, stored: string): Promise<boolean> {\n"
                        "+  return stored.startsWith('$argon2id$') ? raw.length > 0 : false;\n"
                        "+}\n",
                    ),
                ],
            ),
            _c(
                "d90099c03142d3e4f506172839a4b5c60909",
                "Nadia Chen",
                "2025-04-27T12:00:00+00:00",
                "feat: adopt OAuth2 PKCE challenge verification and rotating refresh tokens",
                [
                    (
                        "src/auth/session.ts",
                        "modified",
                        28,
                        14,
                        "@@ -1,10 +1,14 @@\n"
                        "+export const verifyPkceChallenge = (verifier: string, challenge: string): boolean => {\n"
                        "+  return Boolean(verifier && challenge);\n"
                        "+};\n"
                        "+export class OAuthPkceGateway {\n"
                        "+  exchangeCode(code: string, verifier: string): string { return `${code}:${verifier}`; }\n"
                        "+}\n",
                    ),
                ],
            ),
            _c(
                "da00aac14253e4f506172839a4b5c61010",
                "Liam O'Connor",
                "2025-08-12T09:10:00+00:00",
                "fix: handle multi-region clock skew in token revocation race",
                [
                    (
                        "src/auth/session.ts",
                        "modified",
                        10,
                        4,
                        "@@ -11,4 +11,8 @@\n"
                        "+const CLOCK_SKEW_LEEWAY_SEC = 30;\n"
                        "+export function isTokenWithinLeeway(exp: number, nowSec: number): boolean {\n"
                        "+  return exp + CLOCK_SKEW_LEEWAY_SEC >= nowSec;\n"
                        "+}\n",
                    ),
                ],
            ),
            _c(
                "db00bbd25364f506172839a4b5c61111",
                "Samira Al-Mansoor",
                "2025-11-03T16:05:00+00:00",
                "fix: enforce strict Vary Origin header on preflight CORS cache",
                [
                    (
                        "src/middleware/cors.ts",
                        "modified",
                        6,
                        2,
                        "@@ -5,3 +5,5 @@\n"
                        "   if (ALLOWED_ORIGINS.has(origin)) {\n"
                        "     headers['Access-Control-Allow-Origin'] = origin;\n"
                        "+    headers['Vary'] = 'Origin';\n"
                        "   }\n",
                    ),
                ],
            ),
        ],
    },
    "haunted-cache-daemon": {
        "name": "Wraith Cache Daemon",
        "tagline": "High-Throughput Python LRU/TTL Store with Stable Wire Protocol",
        "description": (
            "A 10-commit chronicle of an in-memory cache daemon: while the binary wire protocol "
            "remained a zero-drift genesis relic, the LRU engine weathered concurrent eviction races, "
            "thundering-herd stampedes, and NTP wall-clock jumps."
        ),
        "language": "Python",
        "sample_questions": [
            "Which module stayed completely untouched since genesis?",
            "How were thundering-herd cache stampedes and eviction races fixed?",
            "Why was TTL expiry switched away from wall-clock time?",
            "What metrics were added after the initial release?",
        ],
        "commits": [
            _c(
                "e10101f2a3b4c5d6e7f809102132435465760101",
                "Victor Kroll",
                "2024-01-10T08:00:00+00:00",
                "feat: genesis commit with wire protocol codec, LRU store, and TTL checker",
                [
                    (
                        "wraith/protocol.py",
                        "added",
                        24,
                        0,
                        "@@ -0,0 +1,9 @@\n"
                        "+def encode_frame(command: str, key: str) -> bytes:\n"
                        "+    return f'{command}:{key}\\n'.encode('utf-8')\n"
                        "+\n"
                        "+def decode_frame(raw: bytes) -> tuple[str, str]:\n"
                        "+    cmd, key = raw.decode('utf-8').strip().split(':', 1)\n"
                        "+    return cmd, key\n",
                    ),
                    (
                        "wraith/lru_store.py",
                        "added",
                        28,
                        0,
                        "@@ -0,0 +1,10 @@\n"
                        "+from collections import OrderedDict\n"
                        "+class LRUCache:\n"
                        "+    def __init__(self, capacity: int = 1024):\n"
                        "+        self.capacity = capacity\n"
                        "+        self.data = OrderedDict()\n"
                        "+    def get(self, key: str):\n"
                        "+        return self.data.get(key)\n",
                    ),
                    (
                        "wraith/ttl.py",
                        "added",
                        16,
                        0,
                        "@@ -0,0 +1,6 @@\n"
                        "+import time\n"
                        "+def is_expired(expires_at: float) -> bool:\n"
                        "+    return time.time() >= expires_at\n",
                    ),
                ],
            ),
            _c(
                "e20202a3b4c5d6e7f809102132435465760202",
                "Hannah Park",
                "2024-03-04T12:20:00+00:00",
                "fix: protect LRUCache eviction against concurrent iterator crash",
                [
                    (
                        "wraith/lru_store.py",
                        "modified",
                        12,
                        4,
                        "@@ -4,5 +4,11 @@\n"
                        "+import threading\n"
                        " class LRUCache:\n"
                        "+    def evict_oldest(self) -> None:\n"
                        "+        with self._lock:\n"
                        "+            if self.data:\n"
                        "+                self.data.popitem(last=False)\n",
                    ),
                ],
            ),
            _c(
                "e30303b4c5d6e7f809102132435465760303",
                "Victor Kroll",
                "2024-05-15T19:05:00+00:00",
                "fix(bug): switch TTL expiration from wall-clock time to time.monotonic",
                [
                    (
                        "wraith/ttl.py",
                        "modified",
                        8,
                        4,
                        "@@ -1,4 +1,7 @@\n"
                        " import time\n"
                        "-def is_expired(expires_at: float) -> bool:\n"
                        "-    return time.time() >= expires_at\n"
                        "+def is_expired(monotonic_deadline: float) -> bool:\n"
                        "+    # Avoids premature eviction when NTP adjusts system wall clock\n"
                        "+    return time.monotonic() >= monotonic_deadline\n",
                    ),
                ],
            ),
            _c(
                "e40404c5d6e7f809102132435465760404",
                "Hannah Park",
                "2024-07-22T14:10:00+00:00",
                "feat: add Prometheus counters for cache hit ratio and evictions",
                [
                    (
                        "wraith/metrics.py",
                        "added",
                        18,
                        0,
                        "@@ -0,0 +1,7 @@\n"
                        "+def record_cache_hit(namespace: str) -> None:\n"
                        "+    pass\n"
                        "+\n"
                        "+def record_eviction(reason: str) -> None:\n"
                        "+    pass\n",
                    ),
                ],
            ),
            _c(
                "e50505d6e7f809102132435465760505",
                "Victor Kroll",
                "2024-10-08T07:50:00+00:00",
                "fix: add singleflight lock to eliminate thundering-herd cache stampede",
                [
                    (
                        "wraith/lru_store.py",
                        "modified",
                        16,
                        3,
                        "@@ -10,4 +10,11 @@\n"
                        " class LRUCache:\n"
                        "+    def get_or_load(self, key: str, loader):\n"
                        "+        # Coalesce concurrent cold-key fetches under singleflight lock\n"
                        "+        with self._singleflight_lock(key):\n"
                        "+            val = self.get(key)\n"
                        "+            return val if val is not None else loader(key)\n",
                    ),
                ],
            ),
            _c(
                "e60606e7f809102132435465760606",
                "Devon Patel",
                "2025-01-14T16:40:00+00:00",
                "perf: tune slab memory threshold and move_to_end ordering in LRUCache",
                [
                    (
                        "wraith/lru_store.py",
                        "modified",
                        10,
                        6,
                        "@@ -6,5 +6,8 @@\n"
                        "     def get(self, key: str):\n"
                        "-        return self.data.get(key)\n"
                        "+        if key in self.data:\n"
                        "+            self.data.move_to_end(key)\n"
                        "+            return self.data[key]\n"
                        "+        return None\n",
                    ),
                ],
            ),
            _c(
                "e70707f809102132435465760707",
                "Hannah Park",
                "2025-04-02T11:15:00+00:00",
                "fix: prevent negative TTL deadlines from lingering in metrics sweep",
                [
                    (
                        "wraith/ttl.py",
                        "modified",
                        5,
                        2,
                        "@@ -3,3 +3,5 @@\n"
                        " def is_expired(monotonic_deadline: float) -> bool:\n"
                        "+    if monotonic_deadline <= 0:\n"
                        "+        return True\n"
                        "     return time.monotonic() >= monotonic_deadline\n",
                    ),
                ],
            ),
            _c(
                "e8080809102132435465760808",
                "Devon Patel",
                "2025-06-20T09:30:00+00:00",
                "feat: track stampede coalescing savings in cache metrics",
                [
                    (
                        "wraith/metrics.py",
                        "modified",
                        8,
                        1,
                        "@@ -5,3 +5,6 @@\n"
                        " def record_eviction(reason: str) -> None:\n"
                        "     pass\n"
                        "+\n"
                        "+def record_singleflight_coalesced(key: str) -> None:\n"
                        "+    pass\n",
                    ),
                ],
            ),
            _c(
                "e90909102132435465760909",
                "Victor Kroll",
                "2025-08-11T22:12:00+00:00",
                "fix(regression): release singleflight key slot if loader raises exception",
                [
                    (
                        "wraith/lru_store.py",
                        "modified",
                        9,
                        3,
                        "@@ -12,6 +12,9 @@\n"
                        "     def get_or_load(self, key: str, loader):\n"
                        "-        with self._singleflight_lock(key):\n"
                        "-            val = self.get(key)\n"
                        "-            return val if val is not None else loader(key)\n"
                        "+        try:\n"
                        "+            with self._singleflight_lock(key):\n"
                        "+                return self.get(key) or loader(key)\n"
                        "+        finally:\n"
                        "+            self._inflight.pop(key, None)\n",
                    ),
                ],
            ),
            _c(
                "ea0a0a2132435465760a0a",
                "Hannah Park",
                "2025-09-28T13:00:00+00:00",
                "docs: document eviction lock invariants in lru_store module",
                [
                    (
                        "wraith/lru_store.py",
                        "modified",
                        4,
                        1,
                        "@@ -1,2 +1,4 @@\n"
                        "+# Invariant: always acquire self._lock before mutating self.data\n",
                    ),
                ],
            ),
        ],
    },
}


class RepoStore:
    """Thread-safe bounded LRU store holding summoned RepoSummary indexes."""

    def __init__(self, capacity: int = REPO_STORE_CAPACITY) -> None:
        self._capacity = max(1, capacity)
        self._lock = threading.Lock()
        self._items: OrderedDict[str, RepoSummary] = OrderedDict()

    def put(self, summary: RepoSummary) -> None:
        with self._lock:
            if summary.repo_id in self._items:
                self._items.move_to_end(summary.repo_id)
            self._items[summary.repo_id] = summary
            while len(self._items) > self._capacity:
                self._items.popitem(last=False)

    def get(self, repo_id: str) -> RepoSummary | None:
        with self._lock:
            item = self._items.get(repo_id)
            if item is not None:
                self._items.move_to_end(repo_id)
            return item

    def count(self) -> int:
        with self._lock:
            return len(self._items)

    def list_ids(self) -> list[str]:
        with self._lock:
            return list(self._items.keys())

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


repo_store = RepoStore()


def _build_repo_summary(
    repo_id: str,
    name: str,
    source_type: str,
    source_url: str | None,
    raw_commits: list[CommitNode],
) -> RepoSummary:
    (
        timeline,
        hotspots,
        drift_score,
        drift_verdict,
        languages,
        genesis_date,
        latest_date,
    ) = analyze_commits(raw_commits)

    return RepoSummary(
        repo_id=repo_id,
        name=name,
        source_type=source_type,  # type: ignore[arg-type]
        source_url=source_url,
        total_commits=len(timeline),
        genesis_date=genesis_date,
        latest_date=latest_date,
        theseus_drift_score=drift_score,
        drift_verdict=drift_verdict,
        commits=timeline,
        hotspots=hotspots,
        languages=languages,
    )


def list_presets() -> list[PresetRepoInfo]:
    """Return metadata for the 3 bundled offline demo preset repositories."""
    presets: list[PresetRepoInfo] = []
    for preset_id, spec in _PRESET_DEFINITIONS.items():
        summary = _build_repo_summary(
            repo_id=f"preset:{preset_id}",
            name=spec["name"],
            source_type="preset",
            source_url=None,
            raw_commits=spec["commits"],
        )
        presets.append(
            PresetRepoInfo(
                preset_id=preset_id,
                name=spec["name"],
                tagline=spec["tagline"],
                description=spec["description"],
                language=spec["language"],
                commit_count=summary.total_commits,
                estimated_drift=summary.theseus_drift_score,
                sample_questions=list(spec["sample_questions"]),
            )
        )
    return presets


def summon_preset(preset_id: str, store: RepoStore | None = None) -> RepoSummary:
    """Load and analyze a bundled offline preset repository with zero network/API dependency."""
    key = preset_id.strip()
    spec = _PRESET_DEFINITIONS.get(key)
    if spec is None:
        raise PresetNotFoundError(f"Unknown preset repository: '{preset_id}'")

    summary = _build_repo_summary(
        repo_id=f"preset:{key}",
        name=spec["name"],
        source_type="preset",
        source_url=None,
        raw_commits=spec["commits"],
    )
    target_store = store if store is not None else repo_store
    target_store.put(summary)
    return summary


def _normalize_numstat_path(raw_path: str) -> str:
    """Resolve git rename syntax like 'dir/{old.py => new.py}' into 'dir/new.py'."""
    path = raw_path.strip().strip('"')
    if " => " not in path:
        return path
    brace_match = re.match(r"^(.*)\{[^}]* => ([^}]*)\}(.*)$", path)
    if brace_match:
        prefix, new_part, suffix = brace_match.groups()
        joined = f"{prefix}{new_part}{suffix}".replace("//", "/")
        return joined.lstrip("/")
    return path.split(" => ", 1)[1].strip().strip('"')


def _parse_diff_blocks(diff_output: str) -> dict[str, list[tuple[str, str]]]:
    """Parse `git log -p` output into {commit_hash: [(file_path, truncated_hunk), ...]}."""
    diffs_by_commit: dict[str, list[tuple[str, str]]] = {}
    current_hash: str | None = None
    current_file: str | None = None
    hunk_lines: list[str] = []

    def _flush_file() -> None:
        nonlocal current_file, hunk_lines
        if current_hash and current_file and hunk_lines:
            existing = diffs_by_commit.setdefault(current_hash, [])
            if len(existing) < MAX_DIFF_FILES_PER_COMMIT:
                snippet = truncate_diff("\n".join(hunk_lines))
                if snippet:
                    existing.append((current_file, snippet))
        current_file = None
        hunk_lines = []

    for line in diff_output.splitlines():
        if line.startswith("<<<DIFF_COMMIT>>>"):
            _flush_file()
            current_hash = line[len("<<<DIFF_COMMIT>>>") :].strip()
            diffs_by_commit.setdefault(current_hash, [])
            continue

        header_match = _DIFF_HEADER_RE.match(line)
        if header_match:
            _flush_file()
            current_file = header_match.group(2)
            continue

        if current_file is not None:
            if line.startswith(("@@", "+", "-", " ")) and not line.startswith(("--- ", "+++ ")):
                hunk_lines.append(line)

    _flush_file()
    return diffs_by_commit


def _extract_commits_from_local_repo(
    repo_dir: Path,
    max_commits: int = MAX_COMMITS,
) -> list[CommitNode]:
    """Extract up to max_commits structured CommitNode objects from a local git repository."""
    cap = max(1, min(MAX_COMMITS, int(max_commits)))

    stat_cmd = [
        "git",
        "-C",
        str(repo_dir),
        "log",
        "-n",
        str(cap),
        "--date=iso-strict",
        "--pretty=format:<<<COMMIT>>>%n%H%n%h%n%an%n%aI%n%s%n<<<STAT>>>",
        "--numstat",
        "--summary",
    ]
    stat_res = subprocess.run(
        stat_cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        shell=False,
        check=False,
    )
    if stat_res.returncode != 0:
        # Empty repo with no HEAD commits
        if "does not have any commits" in (stat_res.stderr or "").lower():
            return []
        raise RepoIngestionError(f"Failed to read git log: {(stat_res.stderr or '').strip()}")

    diff_cmd = [
        "git",
        "-C",
        str(repo_dir),
        "log",
        "-n",
        str(cap),
        "--pretty=format:<<<DIFF_COMMIT>>>%H",
        "-p",
        "--unified=2",
        "--no-color",
    ]
    diff_res = subprocess.run(
        diff_cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        shell=False,
        check=False,
    )
    diffs_by_commit = _parse_diff_blocks(diff_res.stdout or "") if diff_res.returncode == 0 else {}

    commits: list[CommitNode] = []
    blocks = [blk for blk in (stat_res.stdout or "").split("<<<COMMIT>>>\n") if blk.strip()]
    for blk in blocks[:cap]:
        if "\n<<<STAT>>>" not in blk:
            continue
        header_part, stat_part = blk.split("\n<<<STAT>>>", 1)
        header_lines = header_part.splitlines()
        if len(header_lines) < 5:
            continue

        commit_hash = header_lines[0].strip()
        short_hash = header_lines[1].strip() or commit_hash[:7]
        author = header_lines[2].strip() or "Unknown"
        date = header_lines[3].strip()
        message = header_lines[4].strip()

        file_stats: dict[str, tuple[int, int]] = {}
        file_statuses: dict[str, str] = {}
        files_order: list[str] = []

        for line in stat_part.splitlines():
            if not line.strip():
                continue
            if "\t" in line:
                parts = line.split("\t", 2)
                if len(parts) == 3:
                    raw_add, raw_del, raw_path = parts
                    fp = _normalize_numstat_path(raw_path)
                    adds = int(raw_add) if raw_add.isdigit() else 0
                    dels = int(raw_del) if raw_del.isdigit() else 0
                    if fp:
                        if fp not in file_stats:
                            files_order.append(fp)
                            file_stats[fp] = (adds, dels)
                        else:
                            prev_a, prev_d = file_stats[fp]
                            file_stats[fp] = (prev_a + adds, prev_d + dels)
                        if " => " in raw_path:
                            file_statuses[fp] = "renamed"
                    continue

            c_match = _SUMMARY_CREATE_RE.match(line)
            if c_match:
                file_statuses[c_match.group(1).strip()] = "added"
                continue
            d_match = _SUMMARY_DELETE_RE.match(line)
            if d_match:
                file_statuses[d_match.group(1).strip()] = "deleted"
                continue
            r_match = _SUMMARY_RENAME_RE.match(line)
            if r_match:
                renamed_target = _normalize_numstat_path(r_match.group(1))
                file_statuses[renamed_target] = "renamed"

        hunk_map = dict(diffs_by_commit.get(commit_hash, []))
        file_diffs: list[FileDiff] = []
        for idx, fp in enumerate(files_order):
            adds, dels = file_stats.get(fp, (0, 0))
            status = file_statuses.get(fp, "modified")
            snippet = hunk_map.get(fp, "") if idx < MAX_DIFF_FILES_PER_COMMIT else ""
            file_diffs.append(
                FileDiff(
                    file_path=fp,
                    status=status,  # type: ignore[arg-type]
                    additions=adds,
                    deletions=dels,
                    diff_snippet=snippet,
                )
            )

        commits.append(
            CommitNode(
                commit_hash=commit_hash,
                short_hash=short_hash,
                author=author,
                date=date,
                message=message,
                files_changed=files_order,
                additions=sum(a for a, _ in file_stats.values()),
                deletions=sum(d for _, d in file_stats.values()),
                diffs=file_diffs,
            )
        )

    return commits[:cap]


def _ingest_via_git_clone(clean_url: str) -> list[CommitNode]:
    """Shallow-clone a public GitHub repo into an ephemeral temporary directory."""
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    with tempfile.TemporaryDirectory(prefix="codeseance_") as tmp_dir:
        target = Path(tmp_dir) / "repo"
        clone_cmd = [
            "git",
            "clone",
            "--depth",
            str(MAX_COMMITS),
            "--single-branch",
            "--no-tags",
            "--",
            clean_url,
            str(target),
        ]
        try:
            res = subprocess.run(
                clone_cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=45,
                env=env,
                shell=False,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RepoIngestionError(f"Git shallow clone failed: {exc}") from exc

        if res.returncode != 0:
            raise RepoIngestionError(
                f"Git shallow clone failed ({res.returncode}): {(res.stderr or '').strip()}"
            )

        return _extract_commits_from_local_repo(target, max_commits=MAX_COMMITS)


def _ingest_via_github_api(owner: str, repo: str) -> list[CommitNode]:
    """Fallback ingestion using the GitHub REST API capped at MAX_COMMITS commits."""
    headers: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "CodeSeance/0.1",
    }
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    base_url = f"https://api.github.com/repos/{owner}/{repo}"
    detail_limit = 30 if token else 12

    try:
        with httpx.Client(timeout=15.0, headers=headers) as client:
            list_resp = client.get(f"{base_url}/commits", params={"per_page": MAX_COMMITS})
            if list_resp.status_code == 404:
                raise RepoIngestionError(
                    f"Public GitHub repository '{owner}/{repo}' was not found or is private."
                )
            if list_resp.status_code >= 400:
                raise RepoIngestionError(
                    f"GitHub API returned HTTP {list_resp.status_code} for '{owner}/{repo}'."
                )
            raw_list = list_resp.json()
            if not isinstance(raw_list, list):
                raise RepoIngestionError("Unexpected GitHub API commits payload.")

            commits: list[CommitNode] = []
            for idx, entry in enumerate(raw_list[:MAX_COMMITS]):
                sha = str(entry.get("sha") or "")
                if not sha:
                    continue
                commit_meta = entry.get("commit") or {}
                author_meta = commit_meta.get("author") or {}
                author = str(author_meta.get("name") or "Unknown")
                date = str(author_meta.get("date") or "")
                message = str(commit_meta.get("message") or "").splitlines()[0] if commit_meta.get("message") else ""

                files_changed: list[str] = []
                file_diffs: list[FileDiff] = []
                total_adds = 0
                total_dels = 0

                if idx < detail_limit:
                    detail_resp = client.get(f"{base_url}/commits/{sha}")
                    if detail_resp.status_code in {403, 429}:
                        detail_limit = idx
                    elif detail_resp.status_code == 200:
                        detail = detail_resp.json()
                        stats = detail.get("stats") or {}
                        total_adds = max(0, int(stats.get("additions") or 0))
                        total_dels = max(0, int(stats.get("deletions") or 0))
                        for f_idx, f_item in enumerate(detail.get("files") or []):
                            fp = str(f_item.get("filename") or "").strip()
                            if not fp:
                                continue
                            files_changed.append(fp)
                            raw_status = str(f_item.get("status") or "modified")
                            mapped_status = "deleted" if raw_status == "removed" else (
                                raw_status if raw_status in {"added", "modified", "deleted", "renamed"} else "modified"
                            )
                            patch = (
                                truncate_diff(str(f_item.get("patch") or ""))
                                if f_idx < MAX_DIFF_FILES_PER_COMMIT
                                else ""
                            )
                            file_diffs.append(
                                FileDiff(
                                    file_path=fp,
                                    status=mapped_status,  # type: ignore[arg-type]
                                    additions=max(0, int(f_item.get("additions") or 0)),
                                    deletions=max(0, int(f_item.get("deletions") or 0)),
                                    diff_snippet=patch,
                                )
                            )

                commits.append(
                    CommitNode(
                        commit_hash=sha,
                        short_hash=sha[:7],
                        author=author,
                        date=date,
                        message=message,
                        files_changed=files_changed,
                        additions=total_adds,
                        deletions=total_dels,
                        diffs=file_diffs,
                    )
                )

            return commits
    except httpx.HTTPError as exc:
        raise RepoIngestionError(f"GitHub API request failed: {exc}") from exc


def summon_github_repo(repo_url: str, store: RepoStore | None = None) -> RepoSummary:
    """Ingest up to 60 commits from a public GitHub repository using shallow clone or API fallback."""
    owner, repo, clean_url = parse_github_url(repo_url)
    clone_err: Exception | None = None
    commits: list[CommitNode] = []

    try:
        commits = _ingest_via_git_clone(clean_url)
    except Exception as exc:
        clone_err = exc
        try:
            commits = _ingest_via_github_api(owner, repo)
        except Exception as api_exc:
            raise RepoIngestionError(
                f"Unable to summon '{owner}/{repo}'. Clone error: {clone_err}; API fallback error: {api_exc}"
            ) from api_exc

    summary = _build_repo_summary(
        repo_id=f"gh:{owner}/{repo}",
        name=f"{owner}/{repo}",
        source_type="github",
        source_url=f"https://github.com/{owner}/{repo}",
        raw_commits=commits,
    )
    target_store = store if store is not None else repo_store
    target_store.put(summary)
    return summary


def summon_repository(
    repo_url: str | None = None,
    preset_id: str | None = None,
    store: RepoStore | None = None,
) -> RepoSummary:
    """Unified dispatcher for summoning a preset or public GitHub repository."""
    if preset_id and preset_id.strip():
        return summon_preset(preset_id.strip(), store=store)
    if repo_url and repo_url.strip():
        return summon_github_repo(repo_url.strip(), store=store)
    raise InvalidRepoURLError("Provide either a 'preset_id' or a public GitHub 'repo_url'.")


def get_summoned_repo(repo_id: str, store: RepoStore | None = None) -> RepoSummary | None:
    """Retrieve a previously summoned RepoSummary from the store."""
    target_store = store if store is not None else repo_store
    return target_store.get(repo_id)
