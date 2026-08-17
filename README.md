# SemCache

SemCache is a semantic caching layer for LLM APIs. It sits between your application and the provider, reuses answers for prompts that mean the same thing, and returns them without another model call.

Point your OpenAI client at the proxy instead of `api.openai.com`. Semantically similar chat completions can be served from cache; everything else is forwarded to OpenAI and stored for next time.

```
App  →  Node proxy (:8001)  →  Python similarity API (:8000)  →  Redis Stack
                │                         │
                └─ on miss: OpenAI chat ──┘  embed + vector lookup
```

## How it works

1. The proxy accepts OpenAI-style `POST /v1/chat/completions`.
2. It asks the similarity service to embed the **user** prompt and search Redis for a nearby vector.
3. Entries are partitioned by **system prompt**, **model**, **temperature**, and **max_tokens**, so those cannot leak across use cases.
4. If cosine similarity is at or above the threshold (default `0.95`) and the entry has not expired, the proxy returns the cached completion with `X-Cache: HIT`.
5. On a miss, it calls OpenAI, returns the live response with `X-Cache: MISS`, and stores the completion when the finish reason is `stop` or `length`.

## Tech stack

| Layer | Choice | Role |
|---|---|---|
| Proxy | Node.js, Express, TypeScript | OpenAI-compatible HTTP surface; hit/miss routing |
| Similarity | Python, FastAPI | Embeddings, namespace, hit policy |
| Embeddings | OpenAI `text-embedding-3-small` (384 dims) | Semantic match on the user prompt |
| Vector store | Redis Stack + RedisVL | JSON index, cosine KNN, TTL metadata |
| Provider (today) | OpenAI Chat Completions | Fills the cache on miss |

Prometheus, Grafana, docker-compose, streaming, and extra providers are planned, not in this repo yet.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (Redis Stack — vanilla Redis has no RediSearch)
- Python 3.11+
- Node.js 20+
- An [OpenAI API key](https://platform.openai.com/api-keys)

## Setup

### 1. Environment files

```bash
cp services/similarity/.env.example services/similarity/.env
cp services/proxy/.env.example services/proxy/.env
```

In **both** `.env` files, set `OPENAI_API_KEY`.

In `services/proxy/.env`:

```bash
SIMILARITY_API_URL=http://127.0.0.1:8000
```

`services/similarity/.env` defaults (from `.env.example`):

```bash
REDIS_URL=redis://localhost:6379
SIMILARITY_THRESHOLD=0.95
DEFAULT_TTL_SECONDS=86400
EMBEDDING_MODEL=text-embedding-3-small
```

### 2. Redis Stack

```bash
docker run -d --name semcache-redis -p 6379:6379 redis/redis-stack-server
```

### 3. Similarity service

```bash
cd services/similarity
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

Confirm it is up: `GET http://127.0.0.1:8000/` should return a short JSON greeting.

### 4. Proxy

In a second terminal:

```bash
cd services/proxy
npm install
npx tsx src/index.ts
```

The proxy listens on **8001** unless you set `PORT`.

## Try it

Same prompt twice: first response should be `X-Cache: MISS`, second `X-Cache: HIT`.

```bash
curl -sD - http://127.0.0.1:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [
      {"role": "system", "content": "You answer briefly."},
      {"role": "user", "content": "What is semantic caching?"}
    ],
    "temperature": 0,
    "max_tokens": 128
  }'
```

From an OpenAI SDK, only the base URL needs to change:

```ts
import OpenAI from "openai";

const client = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
  baseURL: "http://127.0.0.1:8001/v1",
});

const completion = await client.chat.completions.create({
  model: "gpt-4o-mini",
  messages: [{ role: "user", content: "What is semantic caching?" }],
});
```

## Reset Redis

Use the same host port as `REDIS_URL` (default `6379`). If you mapped a different port, change `-p` to match.

**Drop the index** (and its documents). Needed after embedding-dimension changes; deleting keys alone will not rebuild the schema. The similarity service recreates `semcache` on the next request.

```bash
redis-cli -p 6379 FT.DROPINDEX semcache DD
```

**Clear cache keys** without dropping the index:

```bash
redis-cli -p 6379 --scan --pattern 'semcache:*' | xargs -r redis-cli -p 6379 DEL
```

On macOS, `xargs` has no `-r`; omit it, or run the same commands inside the container:

```bash
docker exec semcache-redis redis-cli FT.DROPINDEX semcache DD
docker exec semcache-redis sh -c "redis-cli --scan --pattern 'semcache:*' | xargs -r redis-cli DEL"
```

## Tests

From `services/similarity` with the venv active and Redis Stack running:

```bash
python -m pytest
```

Use `python -m pytest` so the venv interpreter is used, not a system `pytest`.

## Repo layout

```
services/proxy/        # Express OpenAI-compatible proxy
services/similarity/   # FastAPI embed + RedisVL lookup/store
.env.example           # Similarity service env template
```

## Notes

- Run uvicorn from `services/similarity` so `load_dotenv()` picks up that directory’s `.env`.
- Changing embedding dimensions requires dropping the Redis index; see [Reset Redis](#reset-redis).
- Cache hits are not streamed. Misses currently return the full OpenAI JSON body (no token streaming yet).
