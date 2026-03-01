from polyphony.cost import CostTracker, TokenUsage, PRICING, ModelPricing
import pytest

def test_token_usage_model():
    usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    assert usage.prompt_tokens == 100
    assert usage.completion_tokens == 50
    assert usage.total_tokens == 150

def test_model_pricing_model():
    pricing = ModelPricing(input_1m=1.0, output_1m=2.0)
    assert pricing.input_1m == 1.0
    assert pricing.output_1m == 2.0

def test_cost_tracker_accumulation():
    tracker = CostTracker()
    
    # Add usage for gpt-4o
    tracker.add_usage("gpt-4o", 1000, 500)
    assert tracker.usage_by_model["gpt-4o"].prompt_tokens == 1000
    assert tracker.usage_by_model["gpt-4o"].completion_tokens == 500
    assert tracker.usage_by_model["gpt-4o"].total_tokens == 1500
    
    # GPT-4o pricing: $5.0 per 1M input, $15.0 per 1M output
    # Cost = (1000/1M * 5) + (500/1M * 15) = 0.005 + 0.0075 = 0.0125
    assert tracker.total_cost == pytest.approx(0.0125)
    
    # Add more usage for gpt-4o
    tracker.add_usage("gpt-4o", 2000, 1000)
    assert tracker.usage_by_model["gpt-4o"].prompt_tokens == 3000
    assert tracker.usage_by_model["gpt-4o"].completion_tokens == 1500
    assert tracker.usage_by_model["gpt-4o"].total_tokens == 4500
    assert tracker.total_cost == pytest.approx(0.0125 * 3)

def test_cost_tracker_multiple_models():
    tracker = CostTracker()
    
    tracker.add_usage("gpt-4o", 1000, 500) # 0.0125
    tracker.add_usage("gpt-4o-mini", 10000, 5000)
    # GPT-4o-mini: $0.15 per 1M input, $0.6 per 1M output
    # Cost = (10000/1M * 0.15) + (5000/1M * 0.6) = 0.0015 + 0.003 = 0.0045
    
    assert tracker.total_cost == pytest.approx(0.0125 + 0.0045)

def test_cost_tracker_fallback_pricing():
    tracker = CostTracker()
    
    # gpt-4o-2024-05-13 should match gpt-4o
    tracker.add_usage("gpt-4o-2024-05-13", 1000, 500)
    assert tracker.total_cost == pytest.approx(0.0125)
    
    # gemini-1.5-pro-latest should match gemini-1.5-pro
    tracker.add_usage("gemini-1.5-pro-latest", 1000, 1000)
    # gemini-1.5-pro: $3.5 per 1M input, $10.5 per 1M output
    # Cost = (1000/1M * 3.5) + (1000/1M * 10.5) = 0.0035 + 0.0105 = 0.014
    assert tracker.total_cost == pytest.approx(0.0125 + 0.014)

def test_cost_tracker_unknown_model():
    tracker = CostTracker()
    
    # Unknown model should track tokens but cost should remain 0
    tracker.add_usage("unknown-model", 1000, 500)
    assert tracker.usage_by_model["unknown-model"].prompt_tokens == 1000
    assert tracker.usage_by_model["unknown-model"].completion_tokens == 500
    assert tracker.total_cost == 0.0

def test_cost_tracker_zero_tokens():
    tracker = CostTracker()
    tracker.add_usage("gpt-4o", 0, 0)
    assert tracker.usage_by_model["gpt-4o"].prompt_tokens == 0
    assert tracker.usage_by_model["gpt-4o"].completion_tokens == 0
    assert tracker.total_cost == 0.0

def test_cost_tracker_large_token_counts():
    tracker = CostTracker()
    # 100 Million tokens
    tracker.add_usage("gpt-4o", 100_000_000, 100_000_000)
    # (100M / 1M * 5) + (100M / 1M * 15) = 100 * 5 + 100 * 15 = 500 + 1500 = 2000
    assert tracker.total_cost == pytest.approx(2000.0)

def test_get_pricing_direct():
    tracker = CostTracker()
    assert tracker.get_pricing("gpt-4o") == PRICING["gpt-4o"]
    assert tracker.get_pricing("gpt-4o-some-suffix") == PRICING["gpt-4o"]
    assert tracker.get_pricing("non-existent") is None
