# Implementation Plan — CodeSéance Core

## Task 1: Kiro Foundation, Steering, Specs & Hooks
- [x] 1.1 Create `.kiro/steering/product-constraints.md` (`inclusion: always`) enforcing zero-hallucination citations, 60-commit shallow cap, offline demo presets, deterministic extractive fallback, bounded drift metrics, and subprocess security.
- [x] 1.2 Create `.kiro/specs/codeseance-core/requirements.md` using EARS acceptance criteria covering presets, GitHub ingestion, AST/drift analysis, grounded Séance Q&A, spectral UI, and verification.
- [x] 1.3 Create `.kiro/specs/codeseance-core/design.md` documenting the Frankenstein architecture, Mermaid flow diagram, Pydantic schemas, Ship-of-Theseus math, and Correctness Properties 1–6.
- [x] 1.4 Create `.kiro/specs/codeseance-core/tasks.md` sequencing the 5 build phases.
- [x] 1.5 Create `.kiro/hooks/test-on-save.kiro.hook` to execute `pytest backend/tests -v` whenever `backend/**/*.py` files are edited.
- [x] 1.6 Create MIT `LICENSE` and `.gitignore` (explicitly keeping `.kiro/` tracked).

---

## Task 2: Git Archaeologist, Ship-of-Theseus Analyzer & Property-Based Testing
_Requirements: 1, 2, 3, 6 | Correctness Properties: 1, 2, 3, 4, 6_
- [x] 2.1 Create `backend/requirements.txt` and `backend/app/__init__.py`.
- [x] 2.2 Implement Pydantic v2 schemas in `backend/app/models.py` (`FileDiff`, `CommitNode`, `FileHotspot`, `PresetRepoInfo`, `RepoSummary`, `Citation`, `SummonRequest`, `SeanceAskRequest`, `SeanceAskResponse`, `HealthResponse`).
- [x] 2.3 Implement `backend/app/ast_analyzer.py` for Ship-of-Theseus per-file and repo drift scoring (`[0.0, 100.0]`), bug-fix classification, `FileHotspot` ranking, and Python AST + JS/TS symbol extraction.
- [x] 2.4 Implement `backend/app/git_archaeologist.py` with 3 rich offline demo presets (`legacy-billing-monolith`, `phoenix-auth-gateway`, `haunted-cache-daemon`), strict public GitHub URL validation, `git clone --depth 60` subprocess extraction (`shell=False`), GitHub REST API fallback, and bounded `RepoStore`.
- [x] 2.5 Write unit tests in `backend/tests/test_archaeologist.py` and Hypothesis property-based tests in `backend/tests/test_citation_properties.py`, then run `pytest backend/tests -v` until 100% pass.

---

## Task 3: Grounded Séance RAG Engine & FastAPI Endpoints
_Requirements: 1, 2, 3, 4, 6 | Correctness Properties: 1, 2, 5_
- [x] 3.1 Implement `backend/app/seance_rag.py` with pure-Python BM25/TF-IDF commit retrieval, optional Groq/OpenAI LLM responder, deterministic extractive citation fallback (`mode: "extractive"`), and mandatory `verify_citations` post-guard.
- [x] 3.2 Implement `backend/app/main.py` exposing `GET /api/health`, `GET /api/presets`, `POST /api/repo/summon`, and `POST /api/seance/ask` with CORS and structured error handling.
- [x] 3.3 Add API integration, extractive fallback, and adversarial citation-verification tests in `backend/tests/` and verify `pytest backend/tests -v` passes 100%.

---

## Task 4: Atmospheric React Frontend (Timeline, Drift Gauge & Séance Chat)
_Requirements: 5_
- [ ] 4.1 Scaffold Vite + React + TypeScript + Tailwind CSS + Framer Motion inside `frontend/` (`package.json`, `index.html`, `src/main.tsx`, `src/App.tsx`, styles/types).
- [ ] 4.2 Implement `frontend/src/components/RepoSummoner.tsx` with GitHub URL input, 3 one-click preset repo cards, and animated Ship-of-Theseus Drift Gauge (`X% Rewritten Since Genesis`).
- [ ] 4.3 Implement `frontend/src/components/TheseusTimeline.tsx` with File Hotspot Radar filtering and interactive vertical commit chronology with churn & bug-fix badges.
- [ ] 4.4 Implement `frontend/src/components/SeanceChat.tsx` with suggested séance prompts, `LLM` vs `Extractive` mode badge, streaming-style display, and clickable commit hash citation pills opening a raw diff inspection drawer/modal.
- [ ] 4.5 Build `frontend/` (`npm run build`) and verify zero TypeScript or bundler errors.

---

## Task 5: Deployment Configs, End-to-End Audit & Hackathon README
_Requirements: 6 | Steering Compliance Audit_
- [ ] 5.1 Create `render.yaml`, `vercel.json`, and `backend/.env.example`.
- [ ] 5.2 Audit the full codebase against `.kiro/steering/product-constraints.md` (zero-hallucination guard, 60-commit cap, offline presets, drift bounds, subprocess hygiene) and re-run `pytest backend/tests -v`.
- [ ] 5.3 Write judge-ready `README.md` documenting the Frankenstein premise, Ship-of-Theseus metric, Mermaid system diagram, quickstart guide, and Kiro Specs/Steering/Hooks/PBT methodology.
