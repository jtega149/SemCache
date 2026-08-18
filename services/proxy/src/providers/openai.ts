import OpenAI from "openai";
import type { LlmPayload } from "../map.ts";
import {
    messageContentToText,
    type LlmProvider,
    type ProviderChatMessage,
    type ProviderRequest,
    type ProviderStreamEvent,
} from "./providers.ts";

function toOpenAIMessages(
    messages: ProviderChatMessage[],
): OpenAI.Chat.ChatCompletionMessageParam[] {
    return messages
        .filter((m) => m.role === "system" || m.role === "user" || m.role === "assistant")
        .map((m) => ({
            role: m.role as "system" | "user" | "assistant",
            content: messageContentToText(m.content),
        }));
}

export class OpenAIClient implements LlmProvider {
    private client: OpenAI;

    constructor(apiKey?: string) {
        const key = apiKey ?? process.env.OPENAI_API_KEY;
        if (!key) {
            throw new Error("OPENAI_API_KEY is not set");
        }
        this.client = new OpenAI({ apiKey: key });
    }

    async complete(req: ProviderRequest): Promise<LlmPayload> {
        const response = await this.client.chat.completions.create({
            model: req.model,
            messages: toOpenAIMessages(req.messages),
            temperature: req.temperature,
            max_tokens: req.max_tokens,
            stream: false,
        });
        const choice = response.choices[0];
        return {
            text: choice?.message.content ?? "",
            prompt_tokens: response.usage?.prompt_tokens ?? 0,
            completion_tokens: response.usage?.completion_tokens ?? 0,
            model_id: response.model,
            finish_reason: choice?.finish_reason ?? "stop",
        };
    }

    async *stream(req: ProviderRequest): AsyncGenerator<ProviderStreamEvent> {
        const stream = await this.client.chat.completions.create({
            model: req.model,
            messages: toOpenAIMessages(req.messages),
            temperature: req.temperature,
            max_tokens: req.max_tokens,
            stream: true,
            stream_options: { include_usage: true },
        });

        let id = `chatcmpl-${Date.now()}`;
        let model = req.model;
        let promptTokens = 0;
        let completionTokens = 0;
        let finishReason: string | null = null;

        for await (const chunk of stream) {
            id = chunk.id || id;
            if (chunk.model) {
                model = chunk.model;
            }
            const delta = chunk.choices[0]?.delta?.content ?? "";
            const chunkFinish = chunk.choices[0]?.finish_reason ?? null;
            if (chunkFinish) {
                finishReason = chunkFinish;
            }
            if (chunk.usage?.prompt_tokens) {
                promptTokens = chunk.usage.prompt_tokens;
            }
            if (chunk.usage?.completion_tokens) {
                completionTokens = chunk.usage.completion_tokens;
            }

            yield {
                id,
                model,
                delta,
                finishReason: chunkFinish,
                promptTokens,
                completionTokens,
            };
        }

        if (finishReason === null) {
            yield {
                id,
                model,
                delta: "",
                finishReason: "stop",
                promptTokens,
                completionTokens,
            };
        }
    }
}
