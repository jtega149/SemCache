import { AnthropicClient } from "./anthropic.ts";
import { OllamaClient } from "./ollama.ts";
import { OpenAIClient } from "./openai.ts";
import type { LlmProvider, ProviderName } from "./providers.ts";

const clients: Partial<Record<ProviderName, LlmProvider>> = {};

export function getProvider(name: ProviderName): LlmProvider {
    const existing = clients[name];
    if (existing) {
        return existing;
    }
    const created =
        name === "openai"
            ? new OpenAIClient()
            : name === "anthropic"
              ? new AnthropicClient()
              : new OllamaClient();
    clients[name] = created;
    return created;
}
