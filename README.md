# SemCache

SemCache is a semantic caching layer for LLM APIs. It sits between your application and the provider, reuses answers for prompts that mean the same thing, and returns them without another model call.

## Built for OpenAI, Anthropic, and Ollama clients

Point your OpenAI, Anthropic, or Ollama client at the proxy instead of their respective endpoints, we handle that for you. Semantically similar chat completions can be served from cache, everything else is forwarded to their respective endpoints that you would have initially tried to call.

```
App  -->   Node proxy (:8001)     -->       FastAPI similarity API (:8000)   -->    Redis Stack
             │                                                  │
             └─ on miss: OpenAI / Anthropic / Ollama API call ──┘  embed + vector lookup
```



## How it works

1. The proxy accepts OpenAI-style `POST /v1/chat/completions`.
2. It asks the similarity service to embed the **user** prompt and search Redis for a nearby vector.
3. Entries are partitioned by **system prompt**, **model**, **temperature**, and **max_tokens**, so those cannot leak across use cases.
4. If cosine similarity is at or above the threshold (default `0.95`) and the entry has not expired, the proxy returns the cached completion with `X-Cache: HIT`.
5. On a miss, it calls the vendor, returns the live response with `X-Cache: MISS`, and stores the completion when the finish reason is `stop` or `length`. If Redis found a neighbor that sat under the cutoff, that lookup is still a miss and the cached answer is not returned. The similarity response includes the neighbor’s score, the cutoff, and the gap between them.

## API

Your app talks to the **proxy** (`:8001`) using each vendor’s normal path. The proxy talks to the **similarity** service (`:8000`) to look up and save cache entries. On a miss it also calls the real OpenAI, Anthropic, or Ollama API.

**You → proxy**

| Method | URL | Same shape as |
|---|---|---|
| `POST` | `http://127.0.0.1:8001/openai/v1/chat/completions` | OpenAI chat completions |
| `POST` | `http://127.0.0.1:8001/anthropic/v1/messages` | Anthropic Messages (`max_tokens` required) |
| `POST` | `http://127.0.0.1:8001/ollama/api/chat` | Ollama chat |

Responses include `X-Cache: HIT` or `X-Cache: MISS`.

**Proxy → similarity** (you do not call these from the OpenAI/Anthropic/Ollama SDK)

| Method | URL | When |
|---|---|---|
| `POST` | `http://127.0.0.1:8000/lookup` | Every request, before the vendor |
| `POST` | `http://127.0.0.1:8000/store` | After a miss, if the answer finished with `stop` or `length` (and TTL is not 0) |

**You → similarity** (optional: wipe cache)

| Method | URL |
|---|---|
| `DELETE` | `http://127.0.0.1:8000/delete/namespace` |
| `DELETE` | `http://127.0.0.1:8000/delete/system-prompt` |
| `DELETE` | `http://127.0.0.1:8000/delete/model` |
| `DELETE` | `http://127.0.0.1:8000/delete/prefix` |

## Tech stack

| Layer | Choice | Role |
|---|---|---|
| Proxy | Node.js, Express, TypeScript | OpenAI-compatible HTTP surface; hit/miss routing |
| Similarity | Python, FastAPI | Embeddings, namespace, hit policy |
| Embeddings | OpenAI `text-embedding-3-small` (384 dims) | Semantic match on the user prompt |
| Vector store | Redis Stack + RedisVL | JSON index, cosine KNN, TTL metadata |
| Provider (today) | OpenAI Chat Completions | Fills the cache on miss |
| Monitoring | Prometheus, Grafana | Lookup and store counts, drawn on a dashboard |

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

In `services/proxy/.env`:

```bash
# At least one api key or ollama base url is needed to run
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
SIMILARITY_API_URL=http://127.0.0.1:8000
OLLAMA_BASE_URL=http://127.0.0.1:11434
```

`services/similarity/.env` defaults (from `.env.example`):

```bash
OPEN_API_KEY=your-api-key
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

For example, from an OpenAI SDK, only the base URL needs to change:

```ts
import OpenAI from "openai";

const client = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
  baseURL: "http://127.0.0.1:8001/v1/chat/completions",
});

const completion = await client.chat.completions.create({
  model: "gpt-4o-mini",
  messages: [{ role: "user", content: "What is semantic caching?" }],
});
```

Also test out streaming (only works on cache miss)
```bash
curl -sN -D - -X POST http://127.0.0.1:8001/openai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"What is the capital of France?"}],"temperature":0.3,"max_tokens":100,"stream":true}'
```

Anthropic Tests:
```bash
# Non-stream
curl -sD - -X POST http://127.0.0.1:8001/anthropic/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-5","max_tokens":100,"temperature":0.3,"messages":[{"role":"user","content":"What is the capital of France?"}]}'
```

```bash
# Stream
curl -sN -D - -X POST http://127.0.0.1:8001/anthropic/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-5","max_tokens":100,"temperature":0.3,"messages":[{"role":"user","content":"What is the capital of France?"}],"stream":true}'
```

Ollama tests (switch out llama3.2:latest for your local model)
```bash
# Non - Streaming
curl -sD - -X POST http://127.0.0.1:8001/ollama/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2:latest","messages":[{"role":"user","content":"What is the capital of France?"}],"options":{"temperature":0.3,"num_predict":100}}'
```

```bash
# Stream
curl -sD - -X POST http://127.0.0.1:8001/ollama/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2:latest","messages":[{"role":"user","content":"What is the capital of France?"}],"options":{"temperature":0.3,"num_predict":100}}'
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

## Cache policy

These four pieces sit on the similarity service. You do not need them to try a basic HIT/MISS; they decide **what we keep**, **how picky a match is**, and **how to wipe Redis** without restarting.

**Invalidation.** Deleting cache on purpose. HTTP `DELETE` on the similarity API (`:8000`) can drop entries for one exact cache “room” (same system prompt + model + temperature + max tokens), everything for a system prompt, everything for a model name, or Redis keys that share a prefix. A delete that matches nothing is still success (`deleted: 0`). That is how you forget stale answers without dropping the whole index.

**TTL classifier.** TTL means “time to live” — how many seconds Redis should keep an answer. We look at the **user’s words** (simple keyword rules, not another LLM). Live or “right now” questions get **0** and are **not stored**. News-ish prompts get a short life (1 hour). Stable facts (“capital of France”) get a week. Everything else uses `DEFAULT_TTL_SECONDS` (one day). Skipping store still returns the live model answer; we just do not cache it.

**Threshold tuner.** The similarity **threshold** is the minimum “how close is close enough” score (0 to 1) to reuse a cached answer. The tuner is a **homework assignment**, not live traffic. We keep a small list of prompt pairs labeled “same question” vs “different question,” pretend the cutoff is 0.90, 0.95, and 0.98, and print hit rate vs mistakes. Run it from `services/similarity` with `python -m app.cache.tuner`. It does **not** change production by itself.

**Adaptive thresholds.** Live lookup no longer uses only 0.95. The same word-buckets as TTL pick a cutoff: stable facts are looser (`THRESHOLD_LOOSE`, 0.90) so paraphrases can hit; news-ish prompts are stricter (`THRESHOLD_STRICT`, 0.98) so we are less likely to serve the wrong cached answer; everything else stays `SIMILARITY_THRESHOLD` (0.95).

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

## Monitoring

`docker compose up --build` from the repo root starts Prometheus and Grafana with the rest of the stack.

The similarity service counts each lookup and store, and prints those counts at `GET http://127.0.0.1:8000/metrics`. Prometheus copies that page every few seconds. Grafana draws them at `http://127.0.0.1:3000`. You can view the SemCache dashboard without logging in.

For whatever time range is selected on the dashboard:

| Panel | What it shows |
|---|---|
| Hit rate | Hits divided by all lookups, with the raw hit and miss counts beside it |
| Near-miss gap | How far a found-but-rejected neighbor sat under the cutoff |
| Lookup speed | A typical lookup and a slow one |
| Stores | Answers saved, and prompts skipped because they were too time-sensitive |

A miss on that dashboard is any lookup that was not a hit: nothing similar was stored, or a neighbor was found and rejected.
