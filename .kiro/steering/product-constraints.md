---
inclusion: always
---

# CodeSéance Product & Engineering Constraints

CodeSéance stitches **deterministic Git commit archaeology and AST/structural diffing** with a **grounded conversational AI persona** ("Frankenstein" architecture for Kiroween 2026). Every implementation decision across the backend, frontend, and tests MUST obey the non-negotiable constraints below.

---

## 1. Zero-Hallucination Grounding Invariant (Mandatory)

- Every `commit_hash`, `short_hash`, `author`, `date`, `file_path`, and `diff_snippet` cited or returned by the Séance Engine (`backend/app/seance_rag.py`)—in both `"llm"` and `"extractive"` modes—**MUST** exist in the ingested repository's verified commit index (`repo_index.commit_map`).
- Zero fabricated commit hashes, invented authors, guessed dates, or unverified file paths are permitted.
- Any candidate citation produced by an LLM prompt whose `commit_hash` (or `short_hash`) does not resolve to an exact entry in `valid_commit_hashes` **MUST** be stripped by the deterministic post-verification guard (`verify_citations`), and all citation metadata (`short_hash`, `date`, `author`, `commit_message`, `file_path`, `diff_snippet`) **MUST** be hydrated strictly from verified `CommitNode` records.
- If the ingested commit history contains no relevant evidence for a user's question, the Séance Engine **MUST** state clearly that the repository archive holds no matching commit record rather than speculating or inventing history.

---

## 2. Shallow History Cap & Bounded Payloads

- Repository ingestion in `backend/app/git_archaeologist.py` **MUST** cap extracted commit history at **`MAX_COMMITS = 60`** most recent commits (`git clone --depth 60 --single-branch --no-tags` or GitHub REST API paginated and capped at 60 commits).
- Stored diff snippets per file per commit **MUST** be bounded (maximum `2,000` characters / `40` lines per file hunk, and maximum `10` file diffs with stored hunks per commit) to prevent LLM context/token overflow, excessive memory consumption, and slow ingestion on large repositories.
- Binary files and massive lockfiles/generated artifacts must have diff text omitted or summarized without inflating snippet budgets.

---

## 3. Zero-Friction Offline Demo Mode & Deterministic Fallback

- All 3 built-in demo preset repositories (`legacy-billing-monolith`, `phoenix-auth-gateway`, `haunted-cache-daemon`) **MUST** be bundled completely offline inside `backend/app/git_archaeologist.py` and operate with **zero external network requests** and **zero API keys**, ensuring hackathon judges never hit rate limits or authentication barriers.
- `POST /api/seance/ask` **MUST** seamlessly default to deterministic BM25/TF-IDF extractive citation mode (`mode: "extractive"`) whenever neither `GROQ_API_KEY` nor `OPENAI_API_KEY` is configured in the environment/dotenv—and **MUST** fall back to `"extractive"` if an upstream LLM call errors or times out.

---

## 4. Quantitative & Bounded Metric Invariants

- All Ship-of-Theseus drift scores—both repository-level `theseus_drift_score` and per-file `FileHotspot.drift_score`—**MUST** be finite floating-point numbers strictly within `[0.0, 100.0]`:
  - `0.0` = untouched genesis code
  - `100.0` = completely rewritten, deleted, or post-genesis replacement code
- All `FileHotspot` metrics **MUST** uphold:
  - `commit_count >= 1`
  - `0 <= bugfix_count <= commit_count`
  - `total_churn >= 0`
  - `hotspot_score >= 0.0`
  - Hotspot lists deterministically sorted in descending order of `hotspot_score`.

---

## 5. Security, Subprocess Hygiene & Kiro Traceability

- Public GitHub URL ingestion **MUST** strictly validate `https://github.com/<owner>/<repo>` URLs and reject `file://`, `ssh://`, `git://`, local filesystem paths, embedded credentials, or shell metacharacters.
- Every `git` subprocess invocation **MUST** use an argument list with `shell=False`, explicit `--` end-of-options guards before URLs or paths, strict execution timeouts, and automatic temporary directory cleanup (`tempfile.TemporaryDirectory`).
- Secrets (`GROQ_API_KEY`, `OPENAI_API_KEY`, `GITHUB_TOKEN`) **MUST** be loaded only from environment variables or untracked `.env` files and never hardcoded or committed to source control.
- The `.kiro/` directory (steering, specs, and hooks) **MUST** remain explicitly tracked in Git.
