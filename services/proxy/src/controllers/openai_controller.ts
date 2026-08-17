import type { Request, Response } from "express";
import type OpenAI from "openai";
import { cachedPayloadToChatCompletion, mapOpenAIRequest, type LookupResponse } from "../map.ts";
import { createChatCompletion } from "../openai.ts";

const CACHEABLE_FINISH_REASONS = new Set(["stop", "length"]);

const chatCompletions = async (req: Request, res: Response) => {
    try {
        const SIMILARITY_API_URL = process.env.SIMILARITY_API_URL;
        if (!SIMILARITY_API_URL) {
            throw new Error("SIMILARITY_API_URL is not set");
        }

        const cacheKey = mapOpenAIRequest(req.body);

        const lookupRes = await fetch(`${SIMILARITY_API_URL}/lookup`, {
            method: "POST",
            body: JSON.stringify(cacheKey),
            headers: {
                "Content-Type": "application/json",
            },
        });
        if (!lookupRes.ok) {
            const detail = await lookupRes.text();
            console.error("Similarity lookup failed:", lookupRes.status, detail);
            return res.status(502).json({ error: "Similarity lookup failed" });
        }

        const lookup = (await lookupRes.json()) as LookupResponse;
        if (lookup.cached && lookup.payload) {
            res.setHeader("X-Cache", "HIT");
            return res.json(cachedPayloadToChatCompletion(lookup.payload));
        }

        const openaiResponse = await createChatCompletion({
            model: cacheKey.model,
            messages: req.body.messages as OpenAI.Chat.ChatCompletionMessageParam[],
            temperature: cacheKey.temperature,
            max_tokens: cacheKey.max_tokens,
        });

        const choice = openaiResponse.choices[0];
        const finishReason = choice?.finish_reason ?? "";
        if (choice?.message.content && CACHEABLE_FINISH_REASONS.has(finishReason)) {
            const storeRes = await fetch(`${SIMILARITY_API_URL}/store`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    ...cacheKey,
                    llm_payload: {
                        text: choice.message.content,
                        prompt_tokens: openaiResponse.usage?.prompt_tokens ?? 0,
                        completion_tokens: openaiResponse.usage?.completion_tokens ?? 0,
                        model_id: openaiResponse.model,
                        finish_reason: finishReason,
                    },
                }),
            });
            if (!storeRes.ok) {
                console.error("Similarity store failed:", storeRes.status, await storeRes.text());
            }
        }

        res.setHeader("X-Cache", "MISS");
        return res.json(openaiResponse);
    } catch (error) {
        if (
            error instanceof Error &&
            (error.message === "model is required" ||
                error.message === "messages must include a user message")
        ) {
            return res.status(400).json({ error: error.message });
        }
        console.error("Error in chat completions:", error);
        return res.status(500).json({ error: "Internal server error" });
    }
};

export default chatCompletions;
