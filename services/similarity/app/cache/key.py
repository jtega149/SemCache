# system-prompt hash + params → cache namespace
from hashlib import sha256

def hash_system_prompt(system_prompt: str) -> str:
    return sha256(system_prompt.encode()).hexdigest()

def build_namespace(system_prompt: str, model: str, temperature: float, max_tokens: int) -> str:
    return f"system_prompt={hash_system_prompt(system_prompt)}:model={model}:temperature={temperature:.2f}:max_tokens={max_tokens}"