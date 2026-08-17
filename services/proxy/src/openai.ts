import OpenAI from "openai";

let client: OpenAI | undefined;

export function getOpenAI(): OpenAI {
    const apiKey = process.env.OPENAI_API_KEY;
    if (!apiKey) {
        throw new Error("OPENAI_API_KEY is not set");
    }
    if (!client) {
        client = new OpenAI({ apiKey });
    }
    return client;
}

export async function createChatCompletion(args: {
    model: string;
    messages: OpenAI.Chat.ChatCompletionMessageParam[];
    temperature: number;
    max_tokens: number;
}) {
    return getOpenAI().chat.completions.create({
        model: args.model,
        messages: args.messages,
        temperature: args.temperature,
        max_tokens: args.max_tokens,
        stream: false,
    });
}
