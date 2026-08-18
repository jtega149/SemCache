import type { Request, Response } from "express";
import { CACHEABLE_FINISH_REASONS, isMapperError, lookupCache } from "../cache.ts";
import {
    payloadToOllamaResponse,
    storeChatCompletion,
    streamEventToOllamaLine,
    toCacheableFromOllama,
} from "../map.ts";
import { getProvider } from "../providers/get_provider.ts";

const ollamaChat = async (req: Request, res: Response) => {
    try {
        const cacheKey = toCacheableFromOllama(req.body);
        const lookup = await lookupCache(cacheKey);
        if (lookup.cached && lookup.payload) {
            res.setHeader("X-Cache", "HIT");
            return res.json(payloadToOllamaResponse(lookup.payload));
        }

        const provider = getProvider("ollama");
        const providerReq = {
            model: cacheKey.model,
            messages: req.body.messages ?? [],
            temperature: cacheKey.temperature,
            max_tokens: cacheKey.max_tokens,
        };

        res.setHeader("X-Cache", "MISS");
        if (req.body.stream) {
            res.setHeader("Content-Type", "application/x-ndjson");
            let fullText = "";
            let finishReason = "";
            let modelId = cacheKey.model;
            let promptTokens = 0;
            let completionTokens = 0;

            for await (const event of provider.stream(providerReq)) {
                fullText += event.delta;
                if (event.finishReason) {
                    finishReason = event.finishReason;
                }
                modelId = event.model;
                promptTokens = event.promptTokens;
                completionTokens = event.completionTokens;
                res.write(`${JSON.stringify(streamEventToOllamaLine(event))}\n`);
            }

            res.end();

            if (fullText && CACHEABLE_FINISH_REASONS.has(finishReason)) {
                await storeChatCompletion(cacheKey, {
                    text: fullText,
                    prompt_tokens: promptTokens,
                    completion_tokens: completionTokens,
                    model_id: modelId,
                    finish_reason: finishReason,
                });
            }
            return;
        }

        const payload = await provider.complete(providerReq);
        if (payload.text && CACHEABLE_FINISH_REASONS.has(payload.finish_reason)) {
            await storeChatCompletion(cacheKey, payload);
        }
        return res.json(payloadToOllamaResponse(payload));
    } catch (error) {
        if (isMapperError(error)) {
            return res.status(400).json({ error: error.message });
        }
        console.error("Error in Ollama chat:", error);
        if (error instanceof Error && error.message.startsWith("Similarity lookup failed")) {
            return res.status(502).json({ error: "Similarity lookup failed" });
        }
        return res.status(500).json({ error: "Internal server error" });
    }
};

export default ollamaChat;
