from polyphony.token_estimation import estimate_tokens, estimate_messages_tokens

def test_estimate_tokens():
    text = "Hello, world!"
    tokens = estimate_tokens(text)
    assert tokens > 0
    # "Hello, world!" is 4 tokens in cl100k_base
    assert tokens == 4

def test_estimate_messages_tokens():
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"}
    ]
    tokens = estimate_messages_tokens(messages)
    assert tokens > 0
    # system: 4 + len("system") + len("You are a helpful assistant.")
    # user: 4 + len("user") + len("Hello!")
    # + 2 for prime
    # roughly 10-20 tokens
    assert 10 < tokens < 30
