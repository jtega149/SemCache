import type { Request, Response } from "express";
import { CACHEABLE_FINISH_REASONS, isMapperError, lookupCache } from "../cache.ts";
import { payloadToAnthropicResponse, storeChatCompletion, toCacheableFromAnthropic } from "../map.ts";
import { getProvider } from "../providers/get_provider.ts";
import type { ProviderRequest } from "../providers/providers.ts";

function writeSse(res: Response, event: string, data: unknown) {
    res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
}

const anthropicMessages = async (req: Request, res: Response) => {
    try {
        const cacheKey = toCacheableFromAnthropic(req.body);
        const lookup = await lookupCache(cacheKey);
        if (lookup.cached && lookup.payload) {
            res.setHeader("X-Cache", "HIT");
            return res.json(payloadToAnthropicResponse(lookup.payload));
        }

        const provider = getProvider("anthropic");
        const providerReq: ProviderRequest = {
            model: cacheKey.model,
            messages: req.body.messages ?? [],
            temperature: cacheKey.temperature,
            max_tokens: cacheKey.max_tokens,
        };
        if (cacheKey.system_prompt) {
            providerReq.system = cacheKey.system_prompt;
        }

        res.setHeader("X-Cache", "MISS");
        if (req.body.stream) {
            res.setHeader("Content-Type", "text/event-stream");
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

                if (event.delta) {
                    writeSse(res, "content_block_delta", {
                        type: "content_block_delta",
                        delta: { type: "text_delta", text: event.delta },
                    });
                }
                if (event.finishReason) {
                    writeSse(res, "message_delta", {
                        type: "message_delta",
                        delta: {
                            stop_reason: event.finishReason === "length" ? "max_tokens" : "end_turn",
                        },
                        usage: { output_tokens: event.completionTokens },
                    });
                }
            }

            writeSse(res, "message_stop", { type: "message_stop" });
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
        return res.json(payloadToAnthropicResponse(payload));
    } catch (error) {
        if (isMapperError(error)) {
            return res.status(400).json({ error: error.message });
        }
        console.error("Error in Anthropic messages:", error);
        if (error instanceof Error && error.message.startsWith("Similarity lookup failed")) {
            return res.status(502).json({ error: "Similarity lookup failed" });
        }
        return res.status(500).json({ error: "Internal server error" });
    }
};

export default anthropicMessages;
