
const DEFAULT_TEMPERATURE = 1;
const DEFAULT_MAX_TOKENS = 4096;

/** Models that 400 if temperature/top_p/top_k is set to a non-default value. */
const ANTHROPIC_NO_TEMPERATURE_PREFIXES = [
    "claude-opus-4-7",
    "claude-opus-4-8",
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-fable-5",
    "claude-mythos",
] as const;

export function anthropicRejectsTemperature(model: string): boolean {
    const id = model.replace(/^anthropic\./, "");
    return ANTHROPIC_NO_TEMPERATURE_PREFIXES.some((prefix) => id === prefix || id.startsWith(`${prefix}-`));
}

export type CacheableRequest = {
    system_prompt: string;
    user_prompt: string;
    model: string;
    temperature: number;
    max_tokens: number;
};

export type LlmPayload = {
    text: string;
    prompt_tokens: number;
    completion_tokens: number;
    model_id: string;
    finish_reason: string;
};

export type StreamDelta = {
    id: string;
    model: string;
    delta: string;
    finishReason: string | null;
    promptTokens: number;
    completionTokens: number;
};

export type LookupResponse = {
    cached: boolean;
    similarity_score: number | null;
    payload: LlmPayload | null;
};

type ChatMessage = {
    role?: string;
    content?: unknown;
};

type OpenAIChatBody = {
    model?: string;
    messages?: ChatMessage[];
    temperature?: number;
    max_tokens?: number;
};

type AnthropicMessagesBody = {
    model?: string;
    system?: string | Array<{ type?: string; text?: string }>;
    messages?: ChatMessage[];
    temperature?: number;
    max_tokens?: number;
};

type OllamaChatBody = {
    model?: string;
    messages?: ChatMessage[];
    options?: {
        temperature?: number;
        num_predict?: number;
    };
};

export function messageText(content: unknown): string {
    if (typeof content === "string") {
        return content;
    }
    if (Array.isArray(content)) {
        return content
            .map((part) => {
                if (part && typeof part === "object" && "text" in part && typeof part.text === "string") {
                    return part.text;
                }
                return "";
            })
            .filter(Boolean)
            .join("\n");
    }
    return "";
}

function lastUserPrompt(messages: ChatMessage[]): string {
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    return lastUser ? messageText(lastUser.content) : "";
}

function requireModelAndUser(model: string | undefined, user_prompt: string): asserts model is string {
    if (!model) {
        throw new Error("model is required");
    }
    if (!user_prompt) {
        throw new Error("messages must include a user message");
    }
}

export function toCacheableFromOpenAI(body: OpenAIChatBody): CacheableRequest {
    const messages = body.messages ?? [];
    const system_prompt = messages
        .filter((m) => m.role === "system")
        .map((m) => messageText(m.content))
        .join("\n");
    const user_prompt = lastUserPrompt(messages);
    requireModelAndUser(body.model, user_prompt);

    return {
        system_prompt,
        user_prompt,
        model: body.model,
        temperature: body.temperature ?? DEFAULT_TEMPERATURE,
        max_tokens: body.max_tokens ?? DEFAULT_MAX_TOKENS,
    };
}

export function toCacheableFromAnthropic(body: AnthropicMessagesBody): CacheableRequest {
    let system_prompt = "";
    if (typeof body.system === "string") {
        system_prompt = body.system;
    } else if (Array.isArray(body.system)) {
        system_prompt = body.system.map((block) => block.text ?? "").filter(Boolean).join("\n");
    }

    const user_prompt = lastUserPrompt(body.messages ?? []);
    requireModelAndUser(body.model, user_prompt);
    if (body.max_tokens === undefined) {
        throw new Error("max_tokens is required");
    }

    return {
        system_prompt,
        user_prompt,
        model: body.model,
        temperature: anthropicRejectsTemperature(body.model)
            ? DEFAULT_TEMPERATURE
            : (body.temperature ?? DEFAULT_TEMPERATURE),
        max_tokens: body.max_tokens,
    };
}

export function toCacheableFromOllama(body: OllamaChatBody): CacheableRequest {
    const messages = body.messages ?? [];
    const system_prompt = messages
        .filter((m) => m.role === "system")
        .map((m) => messageText(m.content))
        .join("\n");
    const user_prompt = lastUserPrompt(messages);
    requireModelAndUser(body.model, user_prompt);

    return {
        system_prompt,
        user_prompt,
        model: body.model,
        temperature: body.options?.temperature ?? DEFAULT_TEMPERATURE,
        max_tokens: body.options?.num_predict ?? DEFAULT_MAX_TOKENS,
    };
}

export function payloadToOpenAIResponse(payload: LlmPayload) {
    return {
        id: "chatcmpl-cache",
        object: "chat.completion" as const,
        created: Math.floor(Date.now() / 1000),
        model: payload.model_id,
        choices: [
            {
                index: 0,
                message: {
                    role: "assistant" as const,
                    content: payload.text,
                },
                finish_reason: payload.finish_reason,
                logprobs: null,
            },
        ],
        usage: {
            prompt_tokens: payload.prompt_tokens,
            completion_tokens: payload.completion_tokens,
            total_tokens: payload.prompt_tokens + payload.completion_tokens,
        },
    };
}

export function payloadToAnthropicResponse(payload: LlmPayload) {
    return {
        id: "msg-cache",
        type: "message" as const,
        role: "assistant" as const,
        model: payload.model_id,
        content: [{ type: "text" as const, text: payload.text }],
        stop_reason: payload.finish_reason === "length" ? "max_tokens" : "end_turn",
        stop_sequence: null,
        usage: {
            input_tokens: payload.prompt_tokens,
            output_tokens: payload.completion_tokens,
        },
    };
}

export function payloadToOllamaResponse(payload: LlmPayload) {
    return {
        model: payload.model_id,
        message: { role: "assistant", content: payload.text },
        done: true,
        done_reason: payload.finish_reason,
        prompt_eval_count: payload.prompt_tokens,
        eval_count: payload.completion_tokens,
    };
}

export function streamEventToOpenAIChunk(event: StreamDelta) {
    const chunk = {
        id: event.id,
        object: "chat.completion.chunk" as const,
        created: Math.floor(Date.now() / 1000),
        model: event.model,
        choices: [
            {
                index: 0,
                delta: event.delta ? { content: event.delta } : {},
                finish_reason: event.finishReason,
                logprobs: null,
            },
        ],
    };
    if (event.finishReason !== null && (event.promptTokens > 0 || event.completionTokens > 0)) {
        return {
            ...chunk,
            usage: {
                prompt_tokens: event.promptTokens,
                completion_tokens: event.completionTokens,
                total_tokens: event.promptTokens + event.completionTokens,
            },
        };
    }
    return chunk;
}

export function streamEventToOllamaLine(event: StreamDelta) {
    const done = event.finishReason !== null;
    return {
        model: event.model,
        message: { role: "assistant", content: event.delta },
        done,
        ...(done ? { done_reason: event.finishReason, prompt_eval_count: event.promptTokens, eval_count: event.completionTokens } : {}),
    };
}

export async function storeChatCompletion(cacheKey: CacheableRequest, payload: LlmPayload) {
    const SIMILARITY_API_URL = process.env.SIMILARITY_API_URL;

    const storeRes = await fetch(`${SIMILARITY_API_URL}/store`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            ...cacheKey,
            llm_payload: {
                text: payload.text,
                prompt_tokens: payload.prompt_tokens,
                completion_tokens: payload.completion_tokens,
                model_id: payload.model_id,
                finish_reason: payload.finish_reason,
            },
        }),
    });
    if (!storeRes.ok) {
        console.error("Similarity store failed:", storeRes.status, await storeRes.text());
    }
}
