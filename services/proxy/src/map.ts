
const DEFAULT_TEMPERATURE = 1;
const DEFAULT_MAX_TOKENS = 4096;

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

export type LookupResponse = {
    cached: boolean;
    similarity_score: number | null;
    payload: LlmPayload | null;
};

type ChatMessage = {
    role?: string;
    content?: unknown;
};

type ChatCompletionsBody = {
    model?: string;
    messages?: ChatMessage[];
    temperature?: number;
    max_tokens?: number;
};

function messageText(content: unknown): string {
    if (typeof content === "string") {
        return content;
    }
    if (Array.isArray(content)) {
        return content.map((part) => {
            if (part && typeof part === "object" && "text" in part && typeof part.text === "string") {
                return part.text;
            }
            return "";
        }).filter(Boolean).join("\n");
    }
    return "";
}

export function mapOpenAIRequest(body: ChatCompletionsBody): CacheableRequest {
    const messages = body.messages ?? [];
    const system_prompt = messages
        .filter((m) => m.role === "system")
        .map((m) => messageText(m.content))
        .join("\n");

    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    const user_prompt = lastUser ? messageText(lastUser.content) : "";

    if (!body.model) {
        throw new Error("model is required");
    }
    if (!user_prompt) {
        throw new Error("messages must include a user message");
    }

    return {
        system_prompt,
        user_prompt,
        model: body.model,
        temperature: body.temperature ?? DEFAULT_TEMPERATURE,
        max_tokens: body.max_tokens ?? DEFAULT_MAX_TOKENS,
    };
}

export function cachedPayloadToChatCompletion(payload: LlmPayload) {
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
