# LLM Chatbot with Key Failover and Response Caching

## 1. Live URLs
- **Frontend**: https://lyftr-ai-frontend.vercel.app (replace with actual URL after deployment)
- **Backend**: https://lyftr-ai-backend.onrender.com (replace with actual URL after deployment)

## 2. Run locally: with Docker and without

### With Docker
```bash
cp .env.example .env
# Edit .env with your API keys
make up
# Backend: http://localhost:8000
# Frontend: http://localhost:3000
make down
```

### Without Docker
```bash
# Backend
cd backend
pip install -r requirements.txt
export LLM_API_KEYS="key1,key2"
export DATABASE_URL="sqlite:///./app.db"
export ALLOWED_ORIGINS="http://localhost:3000"
export ENABLE_FAILURE_SIMULATION="true"
uvicorn main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
echo "VITE_BACKEND_URL=http://localhost:8000" > .env
npm run dev
```

## 3. Design decisions: key fallback, caching, SQLite session storage

### Key Fallback
LiteLLM Router is configured with a model_list containing all API keys as separate model entries. When a key returns HTTP 429 (rate limit), quota error, or 5xx, LiteLLM automatically retries with the next available key. The `fallback_attempts` counter tracks how many keys were tried before success.

The `X-Simulate-Failure` header (enabled via `ENABLE_FAILURE_SIMULATION=true`) allows testing failover without exhausting real keys — the backend intercepts the simulated failure before making any real API call.

### Caching
LiteLLM's built-in `InMemoryCache` is used. The cache key is derived from the full message list (system prompt + history + new message) sent to the LLM, ensuring identical conversation contexts produce cache hits. When a cache hit occurs:
- `resolution_source` = `LLM_CACHE`
- `key_id` = null
- `fallback_attempts` = 0
- `latency_ms` is significantly lower

### SQLite Session Storage
Session history is stored in SQLite with aiosqlite for async access. The database file location is controlled by `DATABASE_URL` and mounted as a Docker named volume (`/data/app.db`), ensuring history persists across container restarts.

## 4. Verification: how to see failover, cache hits and per-message token usage

### Cache hit
1. Send: "What is the capital of France?"
2. Wait for response (LIVE_INFERENCE)
3. Open a new session (refresh page)
4. Send the same message
5. Response should show LLM_CACHE and much lower latency

### Failover with X-Simulate-Failure
```bash
# Simulate key_1 failing — should still succeed with key_2
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Simulate-Failure: key_1=429" \
  -d '{"session_id": "test-123", "message": "Hello"}'

# Simulate all keys failing — should return 503
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Simulate-Failure: *=429" \
  -d '{"session_id": "test-456", "message": "Hello"}'
```

### Token usage
Each response includes `input_tokens` and `output_tokens` in the metadata. The UI displays these next to each AI reply.

## 5. Setup Used
- **Editor**: Google Antigravity (AI-powered IDE)
- **AI Tools**: Claude Sonnet 4.6 (Thinking) via Antigravity swarm
- **Backend**: FastAPI + LiteLLM + aiosqlite + SQLite
- **Frontend**: React + TypeScript + Vite

## 6. Bonus features
- **System prompt override**: A system prompt field in the UI allows setting a custom system prompt per session
- **Failure simulation UI**: The UI includes an X-Simulate-Failure header input for testing failover directly from the browser
- **Health status indicator**: The app shows backend health status on load
