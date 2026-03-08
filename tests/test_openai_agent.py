import pytest
import json
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

@patch("polyphony.openai_agent.OpenAI")
def test_openai_agent_sandbox_parameter(mock_openai_class):
    # Setup mock
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    
    # Initialize agent with sandbox=True
    agent = OpenAIAgent(api_key="fake-key", sandbox=True)
    assert agent.sandbox is True
    
    # Initialize agent with sandbox=False (default)
    agent_default = OpenAIAgent(api_key="fake-key")
    assert agent_default.sandbox is False

@patch("polyphony.tool_executor.run_command")
@patch("polyphony.openai_agent.OpenAI")
def test_openai_agent_execute_task_passes_sandbox(mock_openai_class, mock_run_command):
    # Setup mock
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    
    # Mock tool call
    mock_tool_call = MagicMock()
    mock_tool_call.function.name = "run_command"
    mock_tool_call.function.arguments = json.dumps({"command": "ls"})
    
    mock_response = MagicMock()
    # First response gives a tool call
    mock_msg1 = MagicMock(tool_calls=[mock_tool_call], content="Thinking...")
    # Second response gives no tool call (to end the loop)
    mock_msg2 = MagicMock(tool_calls=None, content="Finished")
    
    mock_response1 = MagicMock(choices=[MagicMock(message=mock_msg1)], usage=MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15))
    mock_response2 = MagicMock(choices=[MagicMock(message=mock_msg2)], usage=MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15))
    
    mock_client.chat.completions.create.side_effect = [mock_response1, mock_response2]
    mock_run_command.return_value = "Success"
    
    # Initialize agent with sandbox=True
    agent = OpenAIAgent(api_key="fake-key", sandbox=True)
    
    # Execute task
    from polyphony.agent import AgentTask
    task = AgentTask(id="task1", description="test task")
    agent.execute_task(task)
    
    # Verify run_command was called with sandbox=True
    mock_run_command.assert_called_once_with(command="ls", sandbox=True)

