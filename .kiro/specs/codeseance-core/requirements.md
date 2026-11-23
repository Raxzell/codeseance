# Requirements Document — CodeSéance Core

## Introduction

**CodeSéance** ("Summoning the ghosts of past commits to explain why legacy code exists") is built for the **Kiroween 2026 Hackathon** under the **Frankenstein** category. It stitches together two fundamentally distinct paradigms into a cohesive developer intelligence platform:

1. **Deterministic Git Commit Archaeology & AST Structural Diffing:** Extracts bounded commit chronologies, file churn metrics, bug-fix hotspots, Python/JS symbol definitions, and a quantitative *Ship-of-Theseus* drift score (`0%` = untouched genesis code, `100%` = completely rewritten).
2. **Grounded Conversational AI Persona:** Lets developers "interview" an archive through an atmospheric Ouija/spectral-terminal interface where every explanation is anchored to verifiable, clickable commit hashes and exact raw diff snippets—never hallucinated history.

---

## Glossary

- **Git Archaeologist:** The backend module (`backend/app/git_archaeologist.py`) responsible for validating public GitHub URLs, performing shallow repository ingestion (`<= 60` commits) via `git` or GitHub REST API, and serving bundled offline preset repositories.
- **Ship-of-Theseus Drift Score:** A bounded percentage in `[0.0, 100.0]` measuring how much a file or repository has been overwritten, deleted, or replaced since its genesis commit.
- **File Hotspot:** A tracked repository file ranked by commit frequency, bug-fix commit density, and cumulative line churn (`additions + deletions`).
- **Séance Engine:** The retrieval and synthesis component (`backend/app/seance_rag.py`) that indexes commit records via BM25/TF-IDF and generates grounded answers via either a configured LLM (`"llm"` mode) or deterministic extractive fallback (`"extractive"` mode).
- **Verified Commit Index:** The canonical set and map of ingested `CommitNode` objects for a summoned `repo_id`, used as the single source of truth for citation validation.
- **Citation:** A structured evidence record (`commit_hash`, `short_hash`, `date`, `author`, `file_path`, `commit_message`, `diff_snippet`, `relevance_score`) verified against the Verified Commit Index.
- **Preset Repository:** One of three bundled offline Git histories (`legacy-billing-monolith`, `phoenix-auth-gateway`, `haunted-cache-daemon`) stored locally so judges can test immediately with zero network or API keys.
- **Extractive Fallback Mode:** Deterministic answer synthesis using BM25/TF-IDF commit retrieval and verified diff excerpts when no LLM API key is configured or when an LLM call fails.

---

## Requirements

### Requirement 1: Instant Offline Demo Preset Summoning

**User Story:** As a Kiroween hackathon judge or developer, I want to summon built-in demo repositories in one click with zero API keys or network calls so that I can immediately explore CodeSéance without hitting GitHub rate limits or configuration errors.

#### Acceptance Criteria

1. The backend shall expose `GET /api/presets` returning exactly 3 built-in offline `PresetRepoInfo` entries (`legacy-billing-monolith`, `phoenix-auth-gateway`, `haunted-cache-daemon`), each including `preset_id`, `name`, `tagline`, `description`, `language`, `commit_count`, `estimated_drift`, and suggested `sample_questions`.
2. WHEN a client submits `POST /api/repo/summon` with a valid `preset_id`, the Git Archaeologist shall load the bundled commit history completely offline with zero external HTTP or subprocess network calls and return a complete `RepoSummary` within 1 second.
3. WHEN a client submits `POST /api/repo/summon` with an unrecognized `preset_id`, the backend shall return HTTP `404` with a descriptive error detail.
4. Each bundled preset repository shall contain rich, realistic multi-commit evolutionary narratives (genesis commit, architectural rewrites, bug-fix hotspots, and concrete diff hunks) suitable for interactive Q&A.

---

### Requirement 2: Public GitHub Repository Ingestion & Shallow Cap

**User Story:** As a developer investigating a real open-source codebase, I want to paste any public GitHub repository URL and extract its recent commit archaeology safely without hanging on huge histories.

#### Acceptance Criteria

1. WHEN a client submits `POST /api/repo/summon` with a `repo_url`, the Git Archaeologist shall validate that the URL strictly matches `https://github.com/<owner>/<repo>` (with optional `.git` suffix or trailing slash) and reject local paths, non-HTTPS schemes (`file://`, `ssh://`, `git://`), embedded credentials, or shell metacharacters with HTTP `400` or `422`.
2. WHEN neither `preset_id` nor `repo_url` is provided in `POST /api/repo/summon`, the backend shall reject the request with HTTP `422`.
3. WHEN ingesting a valid public GitHub repository, the Git Archaeologist shall cap extracted history at `<= 60` most recent commits (`git clone --depth 60 --single-branch --no-tags` with `shell=False` and strict timeout, falling back to the GitHub REST API if `git` clone is unavailable or fails).
4. For every ingested commit, the Git Archaeologist shall extract `commit_hash`, `short_hash`, `author`, ISO-8601 `date`, `message`, `files_changed`, `additions`, `deletions`, and bounded `FileDiff` entries (with diff snippets capped at `<= 2,000` characters).
5. IF a public GitHub repository is unreachable, private, or returns a non-recoverable upstream failure, THEN the backend shall clean up any temporary directory and return an actionable HTTP `400` or `502` error without crashing the server.

---

### Requirement 3: AST Symbol Extraction & Ship-of-Theseus Drift Analysis

**User Story:** As an architect evaluating legacy technical debt, I want quantified Ship-of-Theseus drift metrics, bug-fix hotspot rankings, and extracted code symbols so that I can identify which modules are original relics versus heavily mutated danger zones.

#### Acceptance Criteria

1. WHEN repository commits are analyzed by `backend/app/ast_analyzer.py`, the analyzer shall compute a per-file `drift_score` and a repository-wide `theseus_drift_score`, both strictly bounded finite floats in `[0.0, 100.0]`.
2. WHERE a repository has zero or one commit, the analyzer shall assign `theseus_drift_score = 0.0` (`"Preserved Relic"`).
3. WHEN a file created in the genesis commit receives zero subsequent additions, deletions, or deletion events, the analyzer shall assign that file `drift_score = 0.0`; WHEN a genesis file is deleted or a file is created strictly after the genesis commit, the analyzer shall assign `drift_score = 100.0`.
4. The analyzer shall assign a deterministic `drift_verdict` tier corresponding to `theseus_drift_score` (`Preserved Relic`, `Evolving Vessel`, `Mutated Architecture`, or `Complete Ship of Theseus`).
5. The analyzer shall classify bug-fix commits (`is_bugfix`) using commit-message heuristics (`fix`, `bug`, `hotfix`, `patch`, `race`, `crash`, `regression`, `vulnerability`, `cve`, `revert`) and produce `FileHotspot` records sorted descending by `hotspot_score`, upholding `commit_count >= 1`, `0 <= bugfix_count <= commit_count`, `total_churn >= 0`, and `hotspot_score >= 0.0`.
6. WHEN analyzing diff hunks or source code, the analyzer shall extract function and class symbols using Python's `ast` module (with regex fallback for partial diff fragments) for `.py` files and structural regex patterns for `.js`/`.ts`/`.jsx`/`.tsx` files.

---

### Requirement 4: Grounded Séance Q&A & Zero-Hallucination Citations

**User Story:** As a developer asking why legacy code looks the way it does, I want natural-language answers backed by verifiable commit hashes and exact diff snippets so that I can trust every claim made by the AI.

#### Acceptance Criteria

1. WHEN a client sends `POST /api/seance/ask` with `{ "repo_id", "question" }`, the Séance Engine shall retrieve the highest-scoring commits using BM25/TF-IDF over commit messages, changed file paths, authors, extracted symbols, and diff snippets.
2. WHERE `GROQ_API_KEY` or `OPENAI_API_KEY` is configured in environment variables, the Séance Engine shall invoke the LLM with strictly the retrieved commit context and a forensic archivist persona, returning `mode: "llm"`.
3. IF neither `GROQ_API_KEY` nor `OPENAI_API_KEY` is configured, OR if the upstream LLM request fails or times out, THEN the Séance Engine shall deterministically synthesize a clear, cited answer in `mode: "extractive"` without external network dependencies.
4. Before returning any response from `POST /api/seance/ask`, the Séance Engine shall execute `verify_citations` so that **100% of returned `Citation` objects** have a `commit_hash` strictly present in the repository's Verified Commit Index, exact matching `short_hash`, `date`, `author`, and `commit_message`, and a `file_path` belonging to that commit's `files_changed` (or `"(commit-level)"` when `files_changed` is empty).
5. WHEN a client asks about a `repo_id` that has not been summoned or does not exist in memory, the backend shall return HTTP `404`.
6. WHEN a client submits an empty or whitespace-only `question`, the backend shall reject the request with HTTP `422`.

---

### Requirement 5: Atmospheric Ouija/Archive Web Interface

**User Story:** As a user interacting with CodeSéance in the browser, I want a cohesive dark spectral-terminal interface linking the Drift Gauge, Commit Timeline, Hotspot Radar, and Séance Chat so I can inspect past diffs in one click.

#### Acceptance Criteria

1. The frontend (`frontend/`) shall render a dark spectral-terminal / Ouija-archive aesthetic built with React, Vite, TypeScript, Tailwind CSS, and Framer Motion.
2. The top bar (`RepoSummoner.tsx`) shall provide a GitHub URL input form, 3 one-click demo preset buttons, loading/error feedback, and an animated Ship-of-Theseus Drift Gauge showing `X% Rewritten Since Genesis` and its verdict label.
3. The left pane (`TheseusTimeline.tsx`) shall render an interactive File Hotspot Radar and vertical Commit Timeline displaying commit hashes, authors, dates, bug-fix/churn badges (`+additions / -deletions`), and click-to-filter by file path.
4. The right pane (`SeanceChat.tsx`) shall provide suggested séance prompt chips, a chat history display with a clear `LLM` vs `Extractive` mode badge, streaming-style answer reveal, and clickable commit hash citation pills.
5. WHEN a user clicks any commit hash pill in the Séance Chat or selects a commit in the Timeline, the interface shall open a drawer or modal displaying the exact commit metadata and raw syntax-styled diff snippet.

---

### Requirement 6: Observability, Deployment & Automated Verification

**User Story:** As a maintainer and Kiroween evaluator, I want health checks, deployment manifests, and automated property-based verification so that the system can be deployed cleanly and audited against steering constraints.

#### Acceptance Criteria

1. The backend shall expose `GET /api/health` returning service status, active LLM mode/availability (`groq`, `openai`, or `extractive`), preset count, and cached repository count.
2. The backend shall enable CORS supporting local Vite development origins and configurable `FRONTEND_ORIGINS` for Vercel production deployment.
3. The repository shall include `render.yaml`, `vercel.json`, and `backend/.env.example` (containing no real secrets).
4. The test suite shall include unit tests (`backend/tests/test_archaeologist.py`) and Hypothesis property-based tests (`backend/tests/test_citation_properties.py`) verifying citation hash integrity, drift bounds `[0.0, 100.0]`, history cap `<= 60`, and hotspot invariants, wired into `.kiro/hooks/test-on-save.kiro.hook`.
