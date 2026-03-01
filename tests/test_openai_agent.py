import pytest
from unittest.mock import MagicMock, patch
from polyphony.openai_agent import OpenAIAgent
from polyphony.agent import AgentResult

@patch("polyphony.openai_agent.OpenAI")
def test_openai_agent_generate_commit_message(mock_openai_class):
    # Setup mock
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content="feat: implemented commit message generation"))
    ]
    mock_client.chat.completions.create.return_value = mock_response
    
    # Initialize agent
    agent = OpenAIAgent(api_key="fake-key")
    
    # Setup result
    result = AgentResult(
        task_id="task1",
        success=True,
        output="Implemented the feature and verified it works.",
        verification_output="All tests passed."
    )
    
    # Call method
    commit_msg = agent.generate_commit_message(result)
    
    # Assertions
    assert commit_msg == "feat: implemented commit message generation"
    mock_client.chat.completions.create.assert_called_once()
    
    # Verify prompt content
    args, kwargs = mock_client.chat.completions.create.call_args
    prompt = kwargs["messages"][0]["content"]
    assert "Implemented the feature and verified it works." in prompt
    assert "All tests passed." in prompt

@patch("polyphony.openai_agent.OpenAI")
def test_openai_agent_generate_commit_message_failure(mock_openai_class):
    # Setup mock to fail
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.side_effect = Exception("API error")
    
    # Initialize agent
    agent = OpenAIAgent(api_key="fake-key")
    
    # Setup result
    result = AgentResult(
        task_id="task1",
        success=True,
        output="Some output"
    )
    
    # Call method
    commit_msg = agent.generate_commit_message(result)
    
    # Assertions: should fallback to base implementation
    assert commit_msg == "Task task1 completed"
