import pytest
from polyphony.engine import Orchestrator
from polyphony.agent import AgentTask, AgentResult, BaseAgent

class MockAgent(BaseAgent):
    def __init__(self):
        self._model_name = "mock"
    @property
    def model_name(self): return self._model_name
    @model_name.setter
    def model_name(self, v): self._model_name = v
    @property
    def pro_model_name(self): return "mock-pro"
    @property
    def flash_model_name(self): return "mock-flash"
    def execute_task(self, task, progress=None): return AgentResult(task_id=task.id, success=True)
    def receive_context(self, context): pass
    def decompose_goal(self, goal): return []
    def classify_goal(self, goal): return "simple"
    def generate_commit_message(self, result): return "commit"

def test_generate_reflection_prompt_syntax_error():
    agent = MockAgent()
    orchestrator = Orchestrator(planner=agent)
    task = AgentTask(id="test_task", description="Fix code", verification_command="python test.py")
    result = AgentResult(task_id="test_task", success=False)
    result.verification_output = """  File "test.py", line 1
    def foo(
           ^
SyntaxError: unexpected EOF while parsing"""
    
    prompt = orchestrator._generate_reflection_prompt(task, result)
    
    assert "--- REFLECTION ---" in prompt
    assert "Error Category: SYNTAX_ERROR" in prompt
    assert "Fix the syntax or indentation errors" in prompt

def test_generate_reflection_prompt_test_failure():
    agent = MockAgent()
    orchestrator = Orchestrator(planner=agent)
    task = AgentTask(id="test_task", description="Fix code", verification_command="pytest")
    result = AgentResult(task_id="test_task", success=False)
    result.verification_output = "E       AssertionError: assert 1 == 2"
    
    prompt = orchestrator._generate_reflection_prompt(task, result)
    
    assert "Error Category: TEST_FAILURE" in prompt
    assert "Review the test assertions" in prompt

def test_generate_reflection_prompt_import_error():
    agent = MockAgent()
    orchestrator = Orchestrator(planner=agent)
    task = AgentTask(id="test_task", description="Fix code", verification_command="python test.py")
    result = AgentResult(task_id="test_task", success=False)
    result.verification_output = "ModuleNotFoundError: No module named 'nonexistent'"
    
    prompt = orchestrator._generate_reflection_prompt(task, result)
    
    assert "Error Category: IMPORT_ERROR" in prompt
    assert "Check your imports" in prompt

def test_generate_reflection_prompt_disk_full():
    agent = MockAgent()
    orchestrator = Orchestrator(planner=agent)
    task = AgentTask(id="test_task", description="Save file", verification_command="python test.py")
    result = AgentResult(task_id="test_task", success=False)
    result.verification_output = "OSError: [Errno 28] No space left on device" # ENOSPC
    # Add ENOSPC or Disk full to trigger the category
    result.verification_output += " ENOSPC"
    
    prompt = orchestrator._generate_reflection_prompt(task, result)
    
    assert "Error Category: DISK_FULL" in prompt
    assert "The disk is full" in prompt
