from typing import Dict, Optional
from pydantic import BaseModel, Field
from .token_estimation import estimate_tokens as count_tokens

class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

class ModelPricing(BaseModel):
    input_1m: float  # Price per 1 million input tokens
    output_1m: float # Price per 1 million output tokens

# Prices in USD per 1M tokens (Approximate/Example prices for 2026)
PRICING = {
    "gemini-1.5-pro": ModelPricing(input_1m=3.5, output_1m=10.5),
    "gemini-1.5-flash": ModelPricing(input_1m=0.075, output_1m=0.3),
    "gemini-2.5-flash-lite": ModelPricing(input_1m=0.05, output_1m=0.2),
    "gemini-3-flash-preview": ModelPricing(input_1m=0.05, output_1m=0.2),
    "gpt-4o": ModelPricing(input_1m=5.0, output_1m=15.0),
    "gpt-4o-mini": ModelPricing(input_1m=0.15, output_1m=0.6),
}

class CostTracker(BaseModel):
    # model_name -> TokenUsage
    usage_by_model: Dict[str, TokenUsage] = Field(default_factory=dict)
    total_cost: float = 0.0

    def add_usage(self, model: str, prompt_tokens: int, completion_tokens: int):
        if model not in self.usage_by_model:
            self.usage_by_model[model] = TokenUsage()
        
        usage = self.usage_by_model[model]
        usage.prompt_tokens += prompt_tokens
        usage.completion_tokens += completion_tokens
        usage.total_tokens += (prompt_tokens + completion_tokens)
        
        # Update cost
        pricing = self.get_pricing(model)
        if pricing:
            cost = (prompt_tokens / 1_000_000.0 * pricing.input_1m) + \
                   (completion_tokens / 1_000_000.0 * pricing.output_1m)
            self.total_cost += cost

    def get_pricing(self, model: str) -> Optional[ModelPricing]:
        pricing = PRICING.get(model)
        if not pricing:
            # Fallback logic for model names with version strings or prefixes
            for k, v in PRICING.items():
                if k in model:
                    return v
        return pricing
