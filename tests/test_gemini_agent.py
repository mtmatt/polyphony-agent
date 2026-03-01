import pytest
import json
import subprocess
from unittest.mock import MagicMock, patch
from polyphony.gemini_agent import GeminiAgent
from polyphony.agent import AgentResult

@patch("subprocess.run")
def test_gemini_agent_generate_commit_message(mock_run):
    # Setup mock
    mock_sub_result = MagicMock()
    mock_sub_result.stdout = json.dumps({"response": "feat: implemented commit message generation via gemini"})
    mock_run.return_value = mock_sub_result
    
    # Initialize agent
    agent = GeminiAgent(model_name="gemini-3-flash")
    
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
    assert commit_msg == "feat: implemented commit message generation via gemini"
    mock_run.assert_called_once()
    
    # Verify prompt content
    args, kwargs = mock_run.call_args
    prompt = args[0][-1] # Prompt is the last element in args[0] which is the command list
    assert "Implemented the feature and verified it works." in prompt
    assert "All tests passed." in prompt

@patch("subprocess.run")
def test_gemini_agent_generate_commit_message_failure(mock_run):
    # Setup mock to fail
    mock_run.side_effect = Exception("CLI error")
    
    # Initialize agent
    agent = GeminiAgent()
    
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
