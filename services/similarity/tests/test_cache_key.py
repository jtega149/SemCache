from app.cache.key import build_namespace, hash_system_prompt
from hashlib import sha256

def test_hash_system_prompt():
    """Test hashing a system prompt"""

    system_prompt = "You are a helpful assistant."
    expected_hash = sha256(system_prompt.encode()).hexdigest()
    assert hash_system_prompt(system_prompt) == expected_hash

def test_same_namespace():
    """Test same system prompt and parameters result in the same namespace"""
    system_prompt = "You are a helpful assistant."
    model = "gpt-4o"
    temperature = 0.3
    max_tokens = 1000
    namespace_1 = build_namespace(system_prompt, model, temperature, max_tokens)
    namespace_2 = build_namespace(system_prompt, model, temperature, max_tokens)
    assert namespace_1 == namespace_2

def test_different_namespace_different_system_prompt():
    """Test different system prompts result in different namespaces"""
    system_prompt_1 = "You are a helpful assistant."
    system_prompt_2 = "You are a helpful assistant with a sense of humor."
    model = "gpt-4o"
    temperature = 0.3
    max_tokens = 1000
    namespace_1 = build_namespace(system_prompt_1, model, temperature, max_tokens)
    namespace_2 = build_namespace(system_prompt_2, model, temperature, max_tokens)
    assert namespace_1 != namespace_2

def test_different_namespace_different_temperature():
    """Test different temperatures result in different namespaces"""
    system_prompt = "You are a helpful assistant."
    model = "gpt-4o"
    temperature_1 = 0.3
    temperature_2 = 0.5
    max_tokens = 1000
    namespace_1 = build_namespace(system_prompt, model, temperature_1, max_tokens)
    namespace_2 = build_namespace(system_prompt, model, temperature_2, max_tokens)
    assert namespace_1 != namespace_2

def test_different_namespace_different_model():
    """Test different models result in different namespaces"""
    system_prompt = "You are a helpful assistant."
    model_1 = "gpt-4o"
    model_2 = "gpt-4o-mini"
    temperature = 0.3
    max_tokens = 1000
    namespace_1 = build_namespace(system_prompt, model_1, temperature, max_tokens)
    namespace_2 = build_namespace(system_prompt, model_2, temperature, max_tokens)
    assert namespace_1 != namespace_2

def test_different_namespace_different_max_tokens():
    """Test different max tokens result in different namespaces"""
    system_prompt = "You are a helpful assistant."
    model = "gpt-4o"
    temperature = 0.3
    max_tokens_1 = 1000
    max_tokens_2 = 2000
    namespace_1 = build_namespace(system_prompt, model, temperature, max_tokens_1)
    namespace_2 = build_namespace(system_prompt, model, temperature, max_tokens_2)
    assert namespace_1 != namespace_2

def test_different_namespace_temperature_edge_case():
    """Test if temperature gets properly quantized into same namespace"""
    system_prompt = "You are a helpful assistant."
    model = "gpt-4o"
    temperature_1 = 0.3
    temperature_2 = 0.301
    max_tokens = 1000
    namespace_1 = build_namespace(system_prompt, model, temperature_1, max_tokens)
    namespace_2 = build_namespace(system_prompt, model, temperature_2, max_tokens)
    assert namespace_1 == namespace_2