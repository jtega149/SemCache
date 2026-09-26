# Move the proxy into the FastAPI service

SemCache currently runs five containers: the Node proxy, the FastAPI similarity service, Redis, Prometheus, and Grafana. The proxy is a pass-through. It accepts vendor-shaped chat requests, asks FastAPI whether a similar prompt is already cached, and on a miss calls OpenAI, Anthropic, or Ollama. That work can live in the FastAPI process. After this migration, clients talk to FastAPI directly and the proxy container goes away. The stack becomes four containers: FastAPI, Redis, Prometheus, and Grafana.

Do this as an add-then-remove. Ship the vendor routes on FastAPI while the proxy is still running, point clients at FastAPI, then delete the proxy. Do not start by ripping out `services/proxy`.

## Architecture today

```
Client
  │  vendor-shaped chat request
  ▼
Node proxy (:8001)
  │  POST /lookup, POST /store
  ▼
FastAPI similarity (:8000)  ──►  Redis Stack (vectors, TTL)
  ▲
  └── Prometheus scrapes GET /metrics
        └── Grafana
```

On a cache miss the proxy also calls the real provider. FastAPI never talks to OpenAI Chat, Anthropic Messages, or Ollama chat. It only embeds the user prompt and reads or writes Redis.

| Container | What it owns |
|---|---|
| `proxy` | Public chat API, request mapping, provider SDKs, streaming, `X-Cache` |
| `similarity` | Embeddings, namespace, hit policy, TTL, Redis, delete API, Prometheus metrics |
| `redis` | Vector index and cached completions |
| `prometheus` | Scrapes `similarity:8000/metrics` |
| `grafana` | Dashboard over those metrics |

`docker-compose.yml` wires `proxy` to `SIMILARITY_API_URL=http://similarity:8000`. Every lookup is an HTTP hop from one container to another on the same machine.

## Why the proxy is redundant

The proxy does not own cache policy. `POST /lookup` and `POST /store` already decide hits, thresholds, TTL skips, and what gets written to Redis. The Node process is there to:

1. Speak each vendor’s HTTP shape.
2. Turn that body into the cache key FastAPI already understands.
3. Call the vendor when FastAPI says miss.
4. Turn the stored payload back into that vendor’s JSON.

Those four steps are request handlers. They do not need their own container, runtime, or network hop. After the move, a request stays inside FastAPI: parse the vendor body, call the existing lookup code, and either return the cached payload or call the provider and then the existing store code.

Prometheus already scrapes FastAPI. Grafana does not need a change for this move.

## What stays where it is

Leave these alone. The new routes should call them, not reimplement them.

| Piece | Where |
|---|---|
| `POST /lookup`, `POST /store` | `services/similarity/app/main.py` |
| Embeddings | `app/embeddings/openai.py` |
| Redis search and upsert | `app/store/vector.py` |
| Namespace (`system_prompt`, `model`, `temperature`, `max_tokens`) | `app/cache/key.py` |
| Hit / near-miss policy | `app/cache/policy.py` |
| TTL (including “do not store”) | `app/cache/ttl.py` |
| `DELETE /delete/...` | `app/api/routes/delete_route.py` |
| `GET /metrics` | `app/main.py`, `app/metrics.py` |
| Request and payload models | `app/models/schemas.py` |

`LookupRequest` is already the cache key: `system_prompt`, `user_prompt`, `model`, `temperature`, `max_tokens`. `LlmPayload` is already the stored answer: `text`, `prompt_tokens`, `completion_tokens`, `model_id`, `finish_reason`.

## What the proxy does

Source of truth is `services/proxy/src`. Entry point is `index.ts`: Express on port **8001**, CORS, JSON body, three mounts.

| Client calls | Handler |
|---|---|
| `POST /openai/v1/chat/completions` | `controllers/openai_controller.ts` |
| `POST /anthropic/v1/messages` | `controllers/anthropic_controller.ts` |
| `POST /ollama/api/chat` | `controllers/ollama_controller.ts` |

Each handler does the same thing:

1. Map the vendor body to a cache key (`map.ts`).
2. `POST {SIMILARITY_API_URL}/lookup` (`cache.ts`).
3. If `cached` and `payload` are set, reshape that payload into the vendor’s JSON, set `X-Cache: HIT`, and return. Do not call the provider. A hit is a single JSON body even when the client sent `"stream": true`.
4. Otherwise set `X-Cache: MISS` and call the provider (`providers/`).
5. If the client asked to stream, write the vendor’s stream format as tokens arrive. After the stream ends, store once.
6. If not streaming, complete, store, then return the reshaped JSON.
7. Store only when the answer text is non-empty and `finish_reason` is `stop` or `length` (`CACHEABLE_FINISH_REASONS` in `cache.ts`). `POST /store` may still skip the write when TTL is 0. That decision stays in FastAPI.

Mapper failures return **400** with `{ "error": "<message>" }`:

- `model is required`
- `messages must include a user message`
- `max_tokens is required` (Anthropic only)

A failed lookup returns **502** `{ "error": "Similarity lookup failed" }`. Anything else returns **500** `{ "error": "Internal server error" }`.

### Cache key rules (`map.ts`)

Defaults when the client omits them: `temperature = 1`, `max_tokens = 4096`.

| Vendor | System prompt | User prompt | Temperature | Max tokens |
|---|---|---|---|---|
| OpenAI | All `system` messages, joined with newlines | Last `user` message | `temperature` or 1 | `max_tokens` or 4096 |
| Anthropic | Top-level `system` string, or text blocks joined with newlines | Last `user` message | `temperature` or 1 | Required. No default |
| Ollama | All `system` messages, joined with newlines | Last `user` message | `options.temperature` or 1 | `options.num_predict` or 4096 |

Message `content` may be a string or an array of `{ "text": "..." }` parts. Join the text parts with newlines.

Some Anthropic models reject a non-default temperature. `anthropicRejectsTemperature` in `map.ts` matches these id prefixes (after stripping a leading `anthropic.`): `claude-opus-4-7`, `claude-opus-4-8`, `claude-opus-5`, `claude-sonnet-5`, `claude-fable-5`, `claude-mythos`. For those models the cache key uses temperature `1`, and the provider call omits `temperature`.

### Providers (`providers/`)

`get_provider.ts` builds one client per vendor and reuses it.

| Provider | Client | Env |
|---|---|---|
| OpenAI | `openai` SDK, `chat.completions.create` | `OPENAI_API_KEY` |
| Anthropic | `@anthropic-ai/sdk`, `messages.create` / `messages.stream` | `ANTHROPIC_API_KEY` |
| Ollama | `POST {OLLAMA_BASE_URL}/api/chat` | `OLLAMA_BASE_URL`, default `http://127.0.0.1:11434` |

Normalize every provider result into `LlmPayload` before storing or reshaping:

- OpenAI `finish_reason` is used as-is (`stop`, `length`, …).
- Anthropic `stop_reason: "max_tokens"` becomes `finish_reason: "length"`. Anything else becomes `"stop"`.
- Ollama `done_reason: "length"` stays `"length"`. Anything else becomes `"stop"`.

Streaming yields a small internal event (`id`, `model`, `delta`, `finishReason`, `promptTokens`, `completionTokens`). The controller accumulates text and writes vendor-specific frames:

| Vendor | Response header | Frame |
|---|---|---|
| OpenAI | `Content-Type: text/event-stream` | `data: <chunk>\n\n`, then `data: [DONE]\n\n`. Usage is attached on the chunk that has a finish reason and token counts. |
| Anthropic | `Content-Type: text/event-stream` | SSE `content_block_delta` for text, `message_delta` when finished (`max_tokens` vs `end_turn`), then `message_stop`. |
| Ollama | `Content-Type: application/x-ndjson` | One JSON object per line. |

`map.ts` already has the hit-body builders: `payloadToOpenAIResponse`, `payloadToAnthropicResponse`, `payloadToOllamaResponse`. Port those shapes. Cached ids are fixed strings (`chatcmpl-cache`, `msg-cache`). Anthropic `finish_reason: "length"` goes back out as `stop_reason: "max_tokens"`; otherwise `end_turn`.

### Proxy env

From `services/proxy/.env.example`:

```bash
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
SIMILARITY_API_URL=http://127.0.0.1:8000
OLLAMA_BASE_URL=http://127.0.0.1:11434
```

FastAPI already has `OPENAI_API_KEY` because embeddings use it. `SIMILARITY_API_URL` exists only so the proxy can call FastAPI. In-process calls do not need it.

Inside Compose, the proxy sets `extra_hosts: host.docker.internal:host-gateway` so a container can reach Ollama on the host. The FastAPI service will need that same host entry once it owns the Ollama client.

## Target

```
Client
  │  same vendor paths, port 8000
  ▼
FastAPI (:8000)
  ├── vendor routes (ported from the proxy)
  ├── existing lookup / store / delete / metrics
  └── Redis Stack
        ▲
        └── Prometheus → Grafana
```

Public paths stay the same, on the FastAPI port:

- `POST /openai/v1/chat/completions`
- `POST /anthropic/v1/messages`
- `POST /ollama/api/chat`

`/lookup`, `/store`, `/delete/*`, and `/metrics` stay. Tests and the dashboard keep working. The vendor routes should call the Python lookup and store functions directly. They should not `POST` to `localhost:8000`.

Suggested layout under `services/similarity/app/`:

```
gateway/
  map.py            # cache key + vendor JSON + stream frames
  cache_flow.py     # hit / miss / store-if-cacheable
  providers/
    base.py
    openai.py
    anthropic.py
    ollama.py
  routes.py         # the three POST routes
```

Names can differ. Keep provider clients behind one interface with `complete` and `stream`, matching `providers/providers.ts`.

## Migration steps

### 1. Extract lookup and store so routes can share them

`lookup` and `store` in `app/main.py` inline the embed, namespace, search, policy, and upsert work. Pull that into functions the existing HTTP handlers and the new vendor routes both call. Behavior of `POST /lookup` and `POST /store` stays the same, including metrics labels (`hit`, `empty`, `not_a_hit`, `stored`, `ttl_skip`) and `lookup_seconds`.

### 2. Port the mappers

Translate `map.ts` and the small helpers in `cache.ts` into Python. Cover:

- The three `toCacheableFrom*` functions and the 400 errors above.
- `anthropicRejectsTemperature` and the prefix list. Keep the list identical.
- `messageText` / last-user-prompt extraction.
- The three payload-to-vendor response builders.
- The OpenAI and Ollama stream-frame builders. Anthropic’s SSE writes can live next to them.
- `CACHEABLE_FINISH_REASONS = {"stop", "length"}`.

Add pytest cases next to `services/similarity/tests/` for the mapper: missing model, missing user message, Anthropic missing `max_tokens`, content arrays, joined system prompts, and the temperature override for those Claude prefixes. This is the easiest part to get wrong and the easiest to lock down without API keys.

### 3. Port the three providers

Add `anthropic` to `services/similarity/requirements.txt`. `openai` and `httpx` are already installed; embeddings already use the OpenAI SDK, so reuse that package for chat completions too.

Match the current calls:

- OpenAI: non-stream `chat.completions.create`, and stream with `stream_options: { include_usage: true }`. If the stream ends with no finish reason, yield a final event with `finish_reason: "stop"`, as `providers/openai.ts` does.
- Anthropic: drop `temperature` when `anthropicRejectsTemperature` is true. Map `max_tokens` stop reasons to `length`. System prompt goes in the top-level `system` field, not as a message.
- Ollama: `POST {base}/api/chat` with `options.temperature` and `options.num_predict`. Parse the newline-delimited JSON stream the same way `providers/ollama.ts` does.

Read keys from the environment. Extend `app/config.py` with `ANTHROPIC_API_KEY` and `OLLAMA_BASE_URL` (default `http://127.0.0.1:11434`). `OPENAI_API_KEY` is already there.

Build each client once and reuse it, same as `get_provider.ts`.

### 4. Add the three routes on the FastAPI app

One handler shape, taken from the controllers:

1. Build the cache key. On a mapper error, return 400.
2. Call the extracted lookup. On failure, return 502 with `Similarity lookup failed`.
3. On hit, set header `X-Cache: HIT` and return the vendor JSON.
4. On miss, set `X-Cache: MISS`.
5. Non-stream: `complete`, store when the finish reason is cacheable and text is non-empty, return vendor JSON.
6. Stream: return a `StreamingResponse` with the content type in the table above. Write frames as events arrive. After the generator finishes, store under the same rule. Store failures are logged and do not change the status code, matching `storeChatCompletion` in `map.ts`.

Include the router from `app/main.py`. A lookup failure on the vendor route is the provider’s problem only after a successful miss; do not call the provider if lookup throws.

### 5. Move env and Compose wiring

Add `ANTHROPIC_API_KEY` and `OLLAMA_BASE_URL` to `services/similarity/.env` and `.env.example`.

On the `similarity` service in `docker-compose.yml`, add the host gateway the proxy uses today:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

If Ollama runs on the host, set `OLLAMA_BASE_URL=http://host.docker.internal:11434` for the container. Local uvicorn (not in Docker) keeps `http://127.0.0.1:11434`.

Leave the `proxy` service in Compose until the checks below pass.

### 6. Prove the FastAPI routes match the proxy

With Redis and FastAPI up, repeat the README curls against port **8000** instead of **8001**. Same body, same path, `X-Cache: MISS` then `X-Cache: HIT` on the second identical call.

Check at least:

- OpenAI non-stream hit and miss.
- OpenAI stream miss (`text/event-stream`, `data: [DONE]`), then a second non-stream call hits.
- Anthropic non-stream, including a request that omits `max_tokens` (400).
- Anthropic stream miss.
- Ollama non-stream and stream, if a local model is available.
- A hit while `"stream": true` still returns one JSON body, not a stream.
- A prompt the TTL classifier treats as live (`ttl_for_prompt` returns 0) comes back as a miss and does not become a later hit.
- `GET /metrics` still moves on lookup and store. Grafana at `:3000` still shows the SemCache dashboard.

`services/similarity/tests/call_api.py` is a manual caller for the old `/lookup` and `/store` endpoints. Add a similar manual check, or pytest with `httpx.ASGITransport`, for one vendor route with the provider mocked so CI does not need API keys.

### 7. Point clients at FastAPI and remove the proxy

Update the README examples from `127.0.0.1:8001` to `127.0.0.1:8000`. SDK users only change `baseURL`.

Then delete the proxy:

- Remove the `proxy` service from `docker-compose.yml`.
- Remove `services/proxy/` (Express app, Dockerfile, `package.json`).
- Drop `SIMILARITY_API_URL` from docs and examples.
- From the repo root, `docker compose up --build` should start redis, similarity, prometheus, and grafana only.

Nothing in Prometheus (`prometheus/prometheus.yml`) or the Grafana dashboard references the proxy. Those files stay.

## Done when

- A client can send the three vendor paths to port 8000 and get the same hit, miss, stream, and error behavior described above.
- `POST /lookup`, `POST /store`, the delete routes, and `/metrics` still behave as they do now.
- `docker compose up` no longer starts a proxy container.
