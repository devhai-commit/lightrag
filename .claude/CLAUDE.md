# CLAUDE.md — miccoRAG v3 Project Memory

> **Language**: Code in English; comments can be Vietnamese
> **Last updated**: 2026-09-07

---

## 📖 What This Software Does

miccoRAG is an enterprise **RAG (Retrieval-Augmented Generation) knowledge platform**:

- Users upload documents (PDF/DOCX/TXT) into per-department **workspaces** (knowledge bases).
- The **NexusRAG** pipeline parses, chunks, embeds, and indexes documents into ChromaDB, with optional Knowledge Graph extraction.
- Employees chat with an AI assistant that answers grounded in indexed documents — streaming responses, cited sources, and a graph explorer for entity relationships.
- **RBAC** (3 roles) governs who can upload, approve, and view documents by department.
- A **B2B portal** (in progress) will let external business users query public product/service docs and receive AI-driven package recommendations, without access to internal documents.

---

## 🏗️ Architecture at a Glance

Two FastAPI backends share one PostgreSQL database:

| | **micco-backend** (NexusRAG) | **micco-server** (Legacy) |
|---|---|---|
| Purpose | Workspaces, RAG, documents, KG | Auth, admin, approvals, dashboard |
| API prefix | `/api/v1/...` | `/api/...` |

- **micco-frontend**: React 19 + Vite SPA (port 5174), plain JS/JSX (no TypeScript). `src/utils/api.js` centralizes calls — `ragFetch()` → micco-server, `ragFetchV2()` → micco-backend, `readSSEStream()` parses streaming chat.
- **Data**: PostgreSQL `:5435`, ChromaDB `:8003` (non-default ports to avoid local conflicts).
- **Document lifecycle**: `PENDING → PARSING → PROCESSING → INDEXING → INDEXED` (or `FAILED`); non-admin uploads also need approval.
- Full directory map, models, and endpoint-by-endpoint reference: see `README.md` and the code itself — don't duplicate that detail here.
- Domain rules live in `.claude/rules/*.md` (api-design, llm-integration, rag-pipeline, testing, frontend, multi-agent) — consult those before implementing in that area.

---

## ✅ Coding Rules

- **Clean code first**: small focused functions, descriptive names, no dead code or commented-out blocks, no duplicated logic.
- **YAGNI**: don't add abstractions, config flags, or "just in case" parameters until a real need exists. Prefer extending existing modules over creating new ones.
- **API contract**: every endpoint is `async def`, has a typed Pydantic v2 schema in/out, and returns `{"data": ..., "meta": ...}` / `{"error": {...}}` (see `.claude/rules/api-design.md`).
- **LLM access**: always through `get_llm_provider()` / `get_embedding_provider()` — never call an LLM SDK directly from business logic.
- **Validation**: validate all external input (uploads, request bodies) at the boundary; never trust client data.
- **Before calling work done**: `npm run lint` (frontend) passes, and `pytest` is green for anything you touched (backend). For UI/full-stack features, run `/e2e-test` before committing.

---

## 🔀 Git Workflow

- **Branch per feature**: any non-trivial new feature or refactor gets its own branch off the current integration branch, named `feature/<short-name>` (`fix/<short-name>` for bug fixes). Don't build large features directly on `main` or `v2/b2b`.
- **Auto-commit on completion**: as soon as a coherent, verified unit of work is done (tests pass / feature works end-to-end / lint clean), **create the commit immediately — do not wait for the user to ask each time**. Also commit right away whenever the user explicitly asks to commit. Never leave finished, verified work uncommitted. Don't bundle unrelated changes into one commit. Conventional Commits format: `feat|fix|refactor|docs|test|chore|perf: <description>`.
- **Never commit**: `.env` files, credentials, or scratch artifacts (exported docs, dumps, query results dropped at repo root).
- Still ask first for anything history-rewriting or shared-state-affecting: force-push, `git reset --hard`, amending a pushed commit, pushing to a remote.

---

## ⚙️ Key Commands

**Backend**
```bash
cd micco-backend && docker compose -f docker-compose.services.yml up -d   # Postgres + ChromaDB
cd micco-backend/backend && alembic upgrade head                          # migrations
cd micco-backend/backend && uvicorn app.main:app --reload --port 8000     # run
cd micco-backend/backend && pytest tests/ -x --tb=short                   # test
```

**Frontend**
```bash
cd micco-frontend && npm install
npm run dev      # port 5174
npm run build
npm run lint
```

**Claude Code skills**: `/backend-dev`, `/frontend-dev`, `/qa-tester`, `/coordinate-task`, `/run-qa`, `/rag-test`, `/e2e-test`, `/add-provider`, `/simplify`.

---

## 🐛 Known Issues

1. `app/core/config.py` defines some `Settings` fields (JWT_*, COMPAT_*) twice — last one wins, harmless but should be cleaned up.
2. `VITE_SKIP_AUTH=true` bypasses auth in dev via a `"dev-skip"` token — dev convenience only, must stay off in production.
3. Documents stuck in `PARSING`/`PROCESSING`/`INDEXING` for >10 minutes auto-recover to `FAILED` on backend startup.

---

## 📋 Naming Conventions

| Type | Convention | Example |
|---|---|---|
| Python files/functions | `snake_case` | `rag_service.py`, `get_llm_provider` |
| Python classes | `PascalCase` | `DocumentStatus` |
| JS/JSX files, React components | `PascalCase` | `ChatAssistant.jsx` |
| API routes | `/snake_case` | `/api/v1/rag/chat` |
| Env vars | `UPPER_SNAKE_CASE` | `LLM_PROVIDER` |
| Git branches | `kebab-case` | `feature/new-chat-ui` |

---

## 🚫 Immutable Tech Decisions

> Do NOT change these without consulting the team:

1. Async FastAPI only — no sync endpoints
2. Pydantic v2 only
3. LLM access via provider abstraction only (`get_llm_provider()`)
4. ChromaDB for vectors, same embedding model across a collection
5. SSE streaming for all chat endpoints
6. JWT Bearer auth — no session cookies
7. RBAC with 3 roles — Admin / Trưởng phòng / Nhân viên
8. NexusRAG pipeline for ingestion (chunk → embed → rerank → KG)
9. Vite proxy for API calls in development (not direct CORS)
10. React 19 + Vite 7 frontend stack
