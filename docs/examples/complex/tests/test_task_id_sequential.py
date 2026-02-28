import pytest
from models import Task, TaskList

def test_task_id_sequential_and_unique():
    """
    Test that multiple tasks added to a TaskList receive unique and sequential IDs.
    This verifies the mechanism managed by TaskList.last_id.
    """
    tl = TaskList()
    
    # Add multiple tasks
    task1 = tl.add_task("First task")
    task2 = tl.add_task("Second task")
    task3 = tl.add_task("Third task")
    
    # Assert unique and sequential IDs
    assert task1.id == 1
    assert task2.id == 2
    assert task3.id == 3
    
    # Assert last_id is updated correctly
    assert tl.last_id == 3
    
    # Verify IDs are unique in the collection
    ids = [t.id for t in tl.tasks]
    assert len(ids) == len(set(ids))
    assert ids == [1, 2, 3]

def test_task_id_mechanism_is_not_class_level():
    """
    Verify that Task IDs are managed at the TaskList instance level, 
    not via a class-level counter or factory.
    """
    tl1 = TaskList()
    tl2 = TaskList()
    
    t1_list1 = tl1.add_task("List 1 - Task 1")
    t1_list2 = tl2.add_task("List 2 - Task 1")
    
    # Both should start at 1 because they are in different TaskList instances
    assert t1_list1.id == 1
    assert t1_list2.id == 1
    
    t2_list1 = tl1.add_task("List 1 - Task 2")
    assert t2_list1.id == 2
    assert tl1.last_id == 2
    assert tl2.last_id == 1

def test_task_id_sequential_after_deletion():
    """
    Verify that IDs continue to increment sequentially even after a task is removed,
    ensuring uniqueness over time.
    """
    tl = TaskList()
    tl.add_task("Task 1")
    tl.add_task("Task 2")
    
    # Remove the last task
    tl.remove_task(2)
    
    # The next task should still get ID 3, not reuse ID 2
    task3 = tl.add_task("Task 3")
    assert task3.id == 3
    assert tl.last_id == 3
