"""Temporary smoke test for the similarity HTTP API.

Start the server first (from services/similarity):

    uvicorn app.main:app --reload

Then:

    python tests/call_api.py
"""

import json
import urllib.error
import urllib.request

BASE_URL = "http://127.0.0.1:8000"

LOOKUP_BODY = {
    "system_prompt": "You are a helpful assistant.",
    "user_prompt": "What is the capital of France?",
    "model": "gpt-4o",
    "temperature": 0.3,
    "max_tokens": 1000,
}

STORE_BODY = {
    **LOOKUP_BODY,
    "llm_payload": {
        "text": "Paris",
        "prompt_tokens": 10,
        "completion_tokens": 4,
        "model_id": "gpt-4o",
        "finish_reason": "stop",
    },
}


def post(path: str, body: dict) -> tuple[int, dict | str]:
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def get(path: str) -> tuple[int, dict | str]:
    req = urllib.request.Request(f"{BASE_URL}{path}")
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode())


def main() -> None:
    print("GET /")
    status, body = get("/")
    print(status, body)
    print()

    print("POST /lookup (expect miss if cache is empty)")
    status, body = post("/lookup", LOOKUP_BODY)
    print(status, body)
    print()

    print("POST /store")
    status, body = post("/store", STORE_BODY)
    print(status, body)
    print()

    print("POST /lookup (expect hit after a successful store)")
    status, body = post("/lookup", LOOKUP_BODY)
    print(status, body)


if __name__ == "__main__":
    main()
