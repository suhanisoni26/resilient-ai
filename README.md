# ResilientAI
## 1. Live URLs
Pending deployment; do not submit placeholders.
## 2. Run locally: with Docker and without
Copy `.env.example` to `.env` and replace both key placeholders with real keys. Confirm model availability. Run `make up` (or `docker compose up --build -d` on Windows). Open http://localhost:3000. Backend: http://localhost:8000. Without Docker, from repository root create a Python 3.11 virtual environment, install `pip install -r backend/requirements.txt`, run `uvicorn main:app --app-dir backend --port 8000`. In frontend run `npm install` then `npm run dev`. Run `cd backend && pytest` for mocked contract tests.
## 3. Design decisions: key fallback, caching, SQLite session storage
React sends only the new message and session ID. FastAPI reads history, builds the complete message list, and calls LiteLLM with ordered keys and retries disabled per key. LiteLLM local cache is shared across sessions; simulated requests bypass cache. Successful turns are written atomically to SQLite. A process-wide lock serializes chat calls; use one backend worker. Cache is in memory and does not survive restart; SQLite does. Verify LiteLLM cache metadata with real requests before submission.
## 4. Verification: how to see failover, cache hits and per-message token usage
GET /health. POST /chat with JSON `{"session_id":"a","message":"What is Paris?"}` then repeat with session b; expect identical reply and LLM_CACHE. Use a fresh message and header `X-Simulate-Failure: key_1=429` to verify key_2. Use `*=429` to verify 503 and no stored turn. GET /sessions/a/messages verifies history. Inspect metadata on each reply. Tests mock inference; real integration is pending.
Deploy backend as Docker service with persistent disk mounted at /data, set DATABASE_URL=sqlite:////data/app.db, real keys, ENABLE_FAILURE_SIMULATION=true and ALLOWED_ORIGINS to frontend origin. Deploy frontend on Vercel with root frontend, Vite preset, VITE_API_URL set to public backend URL. Verify both public URLs. Persistent disk may require a paid hosting plan.
## 5. Setup Used: your editor and AI tools
Initial code generated using ChatGPT. Record actual editor and additional tools used before submission.
## 6. Bonus features (if any): what you added beyond the requirements and why
Failure simulation selector and new chat button for easier demonstrations.
