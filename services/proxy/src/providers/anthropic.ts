import Anthropic from "@anthropic-ai/sdk";
import { anthropicRejectsTemperature, type LlmPayload } from "../map.ts";
import {
    messageContentToText,
    type LlmProvider,
    type ProviderRequest,
    type ProviderStreamEvent,
} from "./providers.ts";

function getApiKey(apiKey?: string): string {
    const key = apiKey ?? process.env.ANTHROPIC_API_KEY;
    if (!key) {
        throw new Error("ANTHROPIC_API_KEY is not set");
    }
    return key;
}

function mapStopReason(stopReason: string | null): string {
    if (stopReason === "max_tokens") {
        return "length";
    }
    return "stop";
}

function toAnthropicParams(req: ProviderRequest): Anthropic.MessageCreateParamsNonStreaming {
    const systemFromMessages = req.messages
        .filter((m) => m.role === "system")
        .map((m) => messageContentToText(m.content))
        .join("\n");
    const system = req.system || systemFromMessages;

    const messages: Anthropic.MessageParam[] = req.messages
        .filter((m) => m.role === "user" || m.role === "assistant")
        .map((m) => ({
            role: m.role as "user" | "assistant",
            content: messageContentToText(m.content),
        }));
    
    const params: Anthropic.MessageCreateParamsNonStreaming = {
        model: req.model,
        messages,
        max_tokens: req.max_tokens,
    };
    if (!anthropicRejectsTemperature(req.model)) {
        // Temperature is deprecated for models after Claude Opus 4.6
        params.temperature = req.temperature;
    }
    if (system) {
        params.system = system;
    }
    return params;
}

function textFromAnthropicMessage(message: Anthropic.Message): string {
    return message.content
        .filter((block): block is Anthropic.TextBlock => block.type === "text")
        .map((block) => block.text)
        .join("");
}

export class AnthropicClient implements LlmProvider {
    private client: Anthropic;

    constructor(apiKey?: string) {
        this.client = new Anthropic({ apiKey: getApiKey(apiKey) });
    }

    async complete(req: ProviderRequest): Promise<LlmPayload> {
        const message = await this.client.messages.create(toAnthropicParams(req));
        return {
            text: textFromAnthropicMessage(message),
            prompt_tokens: message.usage.input_tokens,
            completion_tokens: message.usage.output_tokens,
            model_id: message.model,
            finish_reason: mapStopReason(message.stop_reason),
        };
    }

    async *stream(req: ProviderRequest): AsyncGenerator<ProviderStreamEvent> {
        const stream = this.client.messages.stream(toAnthropicParams(req));

        let id = `msg-${Date.now()}`;
        let model = req.model;
        let promptTokens = 0;
        let completionTokens = 0;
        let finishReason: string | null = null;

        for await (const event of stream) {
            if (event.type === "message_start") {
                id = event.message.id;
                model = event.message.model;
                promptTokens = event.message.usage.input_tokens;
            }

            if (event.type === "content_block_delta" && event.delta.type === "text_delta") {
                yield {
                    id,
                    model,
                    delta: event.delta.text,
                    finishReason: null,
                    promptTokens,
                    completionTokens,
                };
            }

            if (event.type === "message_delta") {
                finishReason = mapStopReason(event.delta.stop_reason);
                completionTokens = event.usage.output_tokens;
            }
        }

        yield {
            id,
            model,
            delta: "",
            finishReason,
            promptTokens,
            completionTokens,
        };
    }
}
