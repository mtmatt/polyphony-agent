import pytest
from polyphony.cost import count_tokens

def test_count_tokens_openai_model():
    text = "Hello world!"
    # OpenAI model gpt-4o should be handled by tiktoken
    tokens = count_tokens(text, "gpt-4o")
    # "Hello world!" is usually 3 tokens
    assert tokens == 3

def test_count_tokens_llama_model():
    text = "Hello world!"
    # Llama 3 should fallback to cl100k_base or something similar
    tokens = count_tokens(text, "llama3.1")
    # For "Hello world!", cl100k_base also gives 3 tokens
    assert tokens == 3

def test_count_tokens_fallback():
    text = "A very long sentence with many words to test the fallback estimation if tiktoken fails."
    # If we somehow force a failure or use an unknown model, it might use the character-based fallback
    # but currently we fallback to cl100k_base first.
    tokens = count_tokens(text, "unknown_model")
    assert tokens > 0

def test_count_tokens_empty():
    assert count_tokens("") == 0
