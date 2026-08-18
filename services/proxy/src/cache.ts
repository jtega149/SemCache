import type { CacheableRequest, LookupResponse } from "./map.ts";

export const CACHEABLE_FINISH_REASONS = new Set(["stop", "length"]);

export async function lookupCache(cacheKey: CacheableRequest): Promise<LookupResponse> {
    const SIMILARITY_API_URL = process.env.SIMILARITY_API_URL;
    if (!SIMILARITY_API_URL) {
        throw new Error("SIMILARITY_API_URL is not set");
    }

    const lookupRes = await fetch(`${SIMILARITY_API_URL}/lookup`, {
        method: "POST",
        body: JSON.stringify(cacheKey),
        headers: { "Content-Type": "application/json" },
    });
    if (!lookupRes.ok) {
        const detail = await lookupRes.text();
        throw new Error(`Similarity lookup failed: ${lookupRes.status} ${detail}`);
    }
    return (await lookupRes.json()) as LookupResponse;
}

export function isMapperError(error: unknown): error is Error {
    return (
        error instanceof Error &&
        (error.message === "model is required" ||
            error.message === "messages must include a user message" ||
            error.message === "max_tokens is required")
    );
}
