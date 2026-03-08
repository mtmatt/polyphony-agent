import json
import pytest
from unittest.mock import MagicMock, patch
from polyphony.ollama_agent import OllamaAgent
from polyphony.agent import AgentTask, CollaborativePlan, AgentRole, AgentResult, AgentAction

@pytest.fixture
def mock_httpx():
    with patch("httpx.Client") as mock:
        client = mock.return_value.__enter__.return_value
        yield client

@pytest.fixture
def ollama_agent():
    return OllamaAgent(model_name="llama3.1", base_url="http://localhost:11434")

def test_ollama_agent_classify_goal(ollama_agent, mock_httpx):
    mock_httpx.post.return_value.json.return_value = {
        "message": {"content": json.dumps({"classification": "complex"})},
        "prompt_eval_count": 10,
        "eval_count": 5
    }
    
    classification = ollama_agent.classify_goal("Build a compiler")
    assert classification == "complex"
    assert ollama_agent.usage_by_model["llama3.1"].prompt_tokens == 10
    assert ollama_agent.usage_by_model["llama3.1"].completion_tokens == 5

def test_ollama_agent_decompose_goal(ollama_agent, mock_httpx):
    mock_httpx.post.return_value.json.return_value = {
        "message": {
            "content": json.dumps({
                "tasks": [
                    {"id": "t1", "description": "task 1", "agent_type": "executor"}
                ]
            })
        },
        "prompt_eval_count": 20,
        "eval_count": 30
    }
    
    tasks = ollama_agent.decompose_goal("Do something")
    assert len(tasks) == 1
    assert tasks[0].id == "t1"
    assert tasks[0].description == "task 1"
    assert ollama_agent.usage_by_model["llama3.1"].prompt_tokens == 20
    assert ollama_agent.usage_by_model["llama3.1"].completion_tokens == 30

def test_ollama_agent_execute_task(ollama_agent, mock_httpx):
    # Mocking first response with a tool call
    mock_httpx.post.return_value.json.side_effect = [
        {
            "message": {
                "content": "I will use a tool",
                "tool_calls": [
                    {
                        "function": {
                            "name": "ls",
                            "arguments": {"path": "."}
                        }
                    }
                ]
            },
            "prompt_eval_count": 10,
            "eval_count": 15
        },
        {
            "message": {
                "content": "I finished the task"
            },
            "prompt_eval_count": 20,
            "eval_count": 25
        }
    ]
    
    # Mock tool result
    ollama_agent.tool_executor.execute = MagicMock(return_value=("file1.txt\nfile2.txt", True, AgentAction(action_type="tool_call", content="ls")))
    
    task = AgentTask(id="t1", description="List files")
    result = ollama_agent.execute_task(task)
    
    assert result.success is True
    assert result.output == "I finished the task"
    assert len(result.history) >= 2
    # prompt: 10 + 20 = 30, completion: 15 + 25 = 40
    assert result.usage.prompt_tokens == 30
    assert result.usage.completion_tokens == 40

def test_ollama_agent_review_plan(ollama_agent, mock_httpx):
    mock_httpx.post.return_value.json.return_value = {
        "message": {
            "content": json.dumps({
                "approved": True,
                "confidence_score": 0.9,
                "comments": [{"comment": "Looks good", "severity": "info"}]
            })
        },
        "prompt_eval_count": 15,
        "eval_count": 20
    }
    
    plan = CollaborativePlan(goal="Test goal", tasks=[AgentTask(id="t1", description="task 1")])
    review = ollama_agent.review_plan(plan, AgentRole.QA_SPECIALIST)
    
    assert review.approved is True
    assert review.confidence_score == 0.9
    assert len(review.comments) == 1
    assert review.comments[0].comment == "Looks good"


def test_ollama_agent_token_estimation(ollama_agent, mock_httpx):
    # Mocking response with missing usage
    mock_httpx.post.return_value.json.return_value = {
        "message": {
            "content": "Estimated completion."
        },
        # No usage counts provided
    }
    
    # Clear previous usage
    ollama_agent.usage_by_model = {}
    
    # Simple goal classification to trigger _chat_with_tools
    # We use a mocked JSON response that classify_goal expects
    mock_httpx.post.return_value.json.return_value = {
        "message": {
            "content": '{"classification": "simple"}'
        },
    }
    
    ollama_agent.classify_goal("Simple goal")
    
    usage = ollama_agent.usage_by_model["llama3.1"]
    # Should have estimated something > 0
    assert usage.prompt_tokens > 0
    assert usage.completion_tokens > 0
    assert usage.total_tokens == usage.prompt_tokens + usage.completion_tokens
