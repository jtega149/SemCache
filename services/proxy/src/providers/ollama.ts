import type { LlmPayload } from "../map.ts";
import {
    messageContentToText,
    type LlmProvider,
    type ProviderChatMessage,
    type ProviderRequest,
    type ProviderStreamEvent,
} from "./providers.ts";

type OllamaChatMessage = {
    role: string;
    content: string;
};

type OllamaChatResponse = {
    model?: string;
    message?: { role?: string; content?: string };
    done?: boolean;
    done_reason?: string;
    prompt_eval_count?: number;
    eval_count?: number;
};

function toOllamaMessages(messages: ProviderChatMessage[]): OllamaChatMessage[] {
    return messages
        .filter((m) => m.role === "system" || m.role === "user" || m.role === "assistant")
        .map((m) => ({
            role: m.role as string,
            content: messageContentToText(m.content),
        }));
}

function mapDoneReason(reason: string | undefined): string {
    if (reason === "length") {
        return "length";
    }
    return "stop";
}

export class OllamaClient implements LlmProvider {
    private baseUrl: string;

    constructor(baseUrl?: string) {
        this.baseUrl = (baseUrl ?? process.env.OLLAMA_BASE_URL ?? "http://127.0.0.1:11434").replace(
            /\/$/,
            "",
        );
    }

    private async postChat(req: ProviderRequest, stream: boolean): Promise<Response> {
        const response = await fetch(`${this.baseUrl}/api/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                model: req.model,
                messages: toOllamaMessages(req.messages),
                stream,
                options: {
                    temperature: req.temperature,
                    num_predict: req.max_tokens,
                },
            }),
        });
        if (!response.ok) {
            const detail = await response.text();
            throw new Error(`Ollama request failed: ${response.status} ${detail}`);
        }
        return response;
    }

    async complete(req: ProviderRequest): Promise<LlmPayload> {
        const response = await this.postChat(req, false);
        const data = (await response.json()) as OllamaChatResponse;
        return {
            text: data.message?.content ?? "",
            prompt_tokens: data.prompt_eval_count ?? 0,
            completion_tokens: data.eval_count ?? 0,
            model_id: data.model ?? req.model,
            finish_reason: mapDoneReason(data.done_reason),
        };
    }

    async *stream(req: ProviderRequest): AsyncGenerator<ProviderStreamEvent> {
        const response = await this.postChat(req, true);
        if (!response.body) {
            throw new Error("Ollama stream had no body");
        }

        const id = `ollama-${Date.now()}`;
        let model = req.model;
        let promptTokens = 0;
        let completionTokens = 0;
        let finishReason: string | null = null;
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) {
                break;
            }
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() ?? "";

            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed) {
                    continue;
                }
                const data = JSON.parse(trimmed) as OllamaChatResponse;
                if (data.model) {
                    model = data.model;
                }
                if (data.prompt_eval_count) {
                    promptTokens = data.prompt_eval_count;
                }
                if (data.eval_count) {
                    completionTokens = data.eval_count;
                }
                const delta = data.message?.content ?? "";
                if (data.done) {
                    finishReason = mapDoneReason(data.done_reason);
                }
                yield {
                    id,
                    model,
                    delta,
                    finishReason: data.done ? finishReason : null,
                    promptTokens,
                    completionTokens,
                };
            }
        }

        if (buffer.trim()) {
            const data = JSON.parse(buffer) as OllamaChatResponse;
            if (data.model) {
                model = data.model;
            }
            yield {
                id,
                model,
                delta: data.message?.content ?? "",
                finishReason: data.done ? mapDoneReason(data.done_reason) : finishReason,
                promptTokens: data.prompt_eval_count ?? promptTokens,
                completionTokens: data.eval_count ?? completionTokens,
            };
        }
    }
}
