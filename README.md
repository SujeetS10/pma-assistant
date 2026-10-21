# PMA Teaching Assistant

A course-specific AI teaching assistant for *Probability Models and Applications*. Instructors upload notes and
material; students sign in with their register number and chat with an assistant that answers **only** from that
material, with clickable sources. Everything is stored permanently and shared by all logins.

## Folder structure

```
pma-assistant/
├── frontend/                 Static web app (no build step): HTML, CSS, vanilla JS
│   ├── index.html
│   ├── css/styles.css
│   ├── js/  ui.js · render.js (safe Markdown+LaTeX) · api.js · app.js (login/routing) · student.js · admin.js
│   └── tests/render.test.js  (Node, no dependencies)
├── backend/
│   ├── app/
│   │   ├── main.py           FastAPI app: /api/* + serves the frontend
│   │   ├── routers/          auth.py · student.py · admin.py   (thin HTTP layer)
│   │   ├── services/         auth_service · ingestion · chat_service · factory (business logic, framework-free)
│   │   ├── rag/              parsers · chunking · embedding (ONNX/fastembed) · vector_store (SQLite+NumPy) · retrieval · citations · llm_client · rag
│   │   ├── db.py             SQLite schema + queries      security.py   hashing, tokens, rate limits
│   │   ├── config.py         settings from .env           deps.py       auth guards
│   ├── scripts/              create_admin · ingest_cli · ask
│   ├── evaluation/           metrics + run_evaluation + example dataset
│   ├── tests/                47 offline tests
│   ├── data_demo/            SYNTHETIC sample notes for smoke tests only
│   ├── requirements.txt  Dockerfile
├── data/                     CREATED AT RUNTIME, gitignored: app.db · vectors.db · uploads/   <- back this up
├── render.yaml               Render free-plan blueprint
├── docker-compose.yml  .env.example  .gitignore
```

## Run locally (Windows PowerShell; use `source .venv/bin/activate` on Linux/macOS)

```powershell
cd pma-assistant
Copy-Item .env.example .env          # edit: LLM_API_KEY, LLM_MODEL, ADMIN_USERNAME, ADMIN_PASSWORD (10+ chars)
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1         # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
uvicorn app.main:get_app --factory --reload
```

Open http://localhost:8000. The embedding model (~90 MB) is downloaded once into `.model_cache/` (or run `python -m scripts.prefetch_model`).
The LLM defaults to Groq (`https://api.groq.com/openai/v1`). Set `LLM_MODEL` to a model ID your account can use, e.g. `openai/gpt-oss-120b`. To use another OpenAI-compatible provider, also set `LLM_BASE_URL`.

Docker instead: `docker compose up --build` (data lives in the `pma_data` volume and survives rebuilds).

## Deploying on Render free (512 MB RAM)

This build is memory-lean: embeddings run on ONNX Runtime (no PyTorch), vectors are stored in SQLite and searched
with NumPy (no ChromaDB), and the server runs one worker. Expect roughly 250-350 MB in use.

- Build command: `pip install --no-cache-dir -r backend/requirements.txt && cd backend && python -m scripts.prefetch_model`
- Start command: `cd backend && uvicorn app.main:get_app --factory --host 0.0.0.0 --port $PORT --proxy-headers --workers 1`
- Env vars: `PYTHON_VERSION=3.11.9`, `OMP_NUM_THREADS=1`, `MALLOC_ARENA_MAX=2`, `LLM_API_KEY`, `LLM_MODEL`,
  `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `COOKIE_SECURE=true` (`render.yaml` sets all of this).
- Still too tight? Set `EMBEDDING_PROVIDER=api` (plus `EMBEDDING_API_KEY`, `EMBEDDING_MODEL`, `EMBEDDING_BASE_URL`) to
  move embeddings to a hosted API; local memory then drops to ~150 MB. Re-upload documents after switching models.
- **Free instances have an ephemeral disk**: uploads, the database, vectors and chats are wiped on every redeploy and
  after restarts. A paid persistent disk (mounted at `DATA_DIR`) keeps them.

## How it works

**Admin** (username + password from `.env`): upload PDF/DOCX/TXT/MD or paste a note → the file is saved, then parsed,
chunked, embedded and indexed in the background (status: queued → processing → ready/failed with a reason). Delete a
document and its vectors and file go too. Identical files are rejected. Max size `MAX_UPLOAD_MB`.

**Student** (register number only): chat page with a history sidebar. Each chat is saved under the register number
and can be reopened later or deleted. Answers cite sources as `[1]` chips; clicking opens the exact passage shown to
the model, with document, page and section. "Course material" lists what is currently indexed.

**Persistence**: documents, vectors, accounts, sessions and every chat live in `DATA_DIR` (default `./data`) and are
never reset on restart, logout or new login. Every student queries the same knowledge base. Conversation access is
enforced on the server by the session's register number, never by anything the browser sends.

## Security: what is and isn't protected

- Register-number login has **no password**, as requested. In *open* mode anyone who knows or guesses a number can read
  that student's history. **Admin → Student access → Restricted** limits sign-in to a pasted roster (it refuses to
  enable with an empty roster). Use it for a real class.
- Admin passwords: scrypt-hashed. Sessions: random tokens, stored hashed, HttpOnly + SameSite=Strict cookie, expire after
  `SESSION_HOURS`. Set `COOKIE_SECURE=true` behind HTTPS. Login attempts and chat rate are limited per process.
- The LLM API key stays in the backend. Answers are rendered by a renderer that escapes all text (tested against script/HTML
  injection). Course text is fenced as untrusted data in the prompt, which reduces but cannot eliminate prompt injection.
- Admins see counts only, not students' chats. Run behind HTTPS (e.g. a reverse proxy) before exposing it beyond localhost.

## Tests

```powershell
cd backend ; python -m unittest discover -s tests -v      # 47 tests: persistence, isolation, auth, ingestion, chat, RAG logic
cd ..\frontend ; node --test tests/render.test.js          # 11 tests: renderer safety
```

Retrieval/answer quality: see `backend/evaluation/run_evaluation.py` (`--retrieval-only` needs no LLM key). Write your own
questions from real course material first; the example dataset targets the synthetic demo notes. For `expected_doc` use the
document's title as shown in the admin table.

## Not yet verified (be aware before deploying)

The offline test environment had no network, so FastAPI, fastembed, PyMuPDF and the LLM call were
**never executed together** (the memory-lean rewrite was likewise tested offline with a fake embedder). Business logic, database, auth, chunking and the renderer are tested; the HTTP routers, Chroma
calls and the browser UI were only syntax-checked. Expect to fix small integration issues on first run. Also: KaTeX loads from
a CDN (vendor it for offline sites), scanned PDFs need OCR, PDF equations can extract poorly, and there is no password reset
UI for admins (edit `.env` and restart, or run `python -m scripts.create_admin --username NAME`).
