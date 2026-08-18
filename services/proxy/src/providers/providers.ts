import type { LlmPayload, StreamDelta } from "../map.ts";

export type ProviderName = "openai" | "anthropic" | "ollama";

export type ProviderChatMessage = {
    role?: string;
    content?: unknown;
};

export type ProviderRequest = {
    model: string;
    messages: ProviderChatMessage[];
    temperature: number;
    max_tokens: number;
    system?: string;
};

export type ProviderStreamEvent = StreamDelta;

export interface LlmProvider {
    complete(req: ProviderRequest): Promise<LlmPayload>;
    stream(req: ProviderRequest): AsyncIterable<ProviderStreamEvent>;
}

export function messageContentToText(content: unknown): string {
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
