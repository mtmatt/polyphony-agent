import pytest
from polyphony.agent import AgentTask
from polyphony.engine import DependencyResolver

def test_dependency_resolver_simple():
    tasks = [
        AgentTask(id="task1", description="t1"),
        AgentTask(id="task2", description="t2", depends_on=["task1"]),
        AgentTask(id="task3", description="t3", depends_on=["task1"]),
        AgentTask(id="task4", description="t4", depends_on=["task2", "task3"]),
    ]
    
    batches = DependencyResolver.resolve(tasks)
    
    assert len(batches) == 3
    assert [t.id for t in batches[0]] == ["task1"]
    assert set(t.id for t in batches[1]) == {"task2", "task3"}
    assert [t.id for t in batches[2]] == ["task4"]

def test_dependency_resolver_no_deps():
    tasks = [
        AgentTask(id="task1", description="t1"),
        AgentTask(id="task2", description="t2"),
    ]
    
    batches = DependencyResolver.resolve(tasks)
    
    assert len(batches) == 1
    assert set(t.id for t in batches[0]) == {"task1", "task2"}

def test_dependency_resolver_circular():
    tasks = [
        AgentTask(id="task1", description="t1", depends_on=["task2"]),
        AgentTask(id="task2", description="t2", depends_on=["task1"]),
    ]
    
    with pytest.raises(ValueError, match="Circular dependency detected"):
        DependencyResolver.resolve(tasks)

def test_dependency_resolver_alias():
    # Test that 'dependencies' field also works via synchronization
    tasks = [
        AgentTask(id="task1", description="t1"),
        AgentTask(id="task2", description="t2", dependencies=["task1"]),
    ]
    
    batches = DependencyResolver.resolve(tasks)
    assert len(batches) == 2
    assert [t.id for t in batches[0]] == ["task1"]
    assert [t.id for t in batches[1]] == ["task2"]
