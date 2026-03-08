import tiktoken
from typing import List, Dict, Any

def estimate_tokens(text: str, model: str = "gpt-4o") -> int:
    """Estimates the number of tokens in a string."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        # Fallback to cl100k_base which is used by GPT-4 and most modern models
        encoding = tiktoken.get_encoding("cl100k_base")
    
    return len(encoding.encode(text))

def estimate_messages_tokens(messages: List[Dict[str, Any]], model: str = "gpt-4o") -> int:
    """Estimates the number of tokens in a list of chat messages."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    
    num_tokens = 0
    for message in messages:
        # Every message follows <im_start>{role/name}\n{content}<im_end>\n
        num_tokens += 4
        for key, value in message.items():
            if isinstance(value, str):
                num_tokens += len(encoding.encode(value))
            if key == "name":
                num_tokens += -1  # If name is present, the role is omitted and 1 token is saved
    num_tokens += 3  # Every reply is primed with <im_start>assistant<im_sep>
    return num_tokens
