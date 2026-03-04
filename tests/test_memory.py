"""Tests for the memory module - persistent storage and retrieval of strategies."""

import pytest
import os
import json
from datetime import datetime
from pathlib import Path
from polyphony.memory import (
    RunMemory,
    UserPreference,
    MemoryStore,
    MemoryAugmentedPrompt,
)


@pytest.fixture
def temp_db(tmp_path):
    """Provide a temporary database path."""
    db_path = tmp_path / "test_memory.db"
    return db_path


@pytest.fixture
def memory_store(temp_db):
    """Provide a MemoryStore with a temporary database."""
    store = MemoryStore(db_path=temp_db)
    return store


class TestRunMemory:
    """Tests for the RunMemory model."""

    def test_run_memory_creation(self):
        """Test creating a RunMemory instance."""
        memory = RunMemory(
            run_id="test-run-001",
            goal="Implement feature X",
            strategy="plan-act-verify",
            outcome="success",
            lessons_learned=["Use type hints", "Add early validation"],
        )
        assert memory.run_id == "test-run-001"
        assert memory.goal == "Implement feature X"
        assert memory.strategy == "plan-act-verify"
        assert memory.outcome == "success"
        assert len(memory.lessons_learned) == 2
        assert isinstance(memory.timestamp, datetime)

    def test_run_memory_defaults(self):
        """Test RunMemory with default values."""
        memory = RunMemory(
            run_id="test-002",
            goal="Fix bug",
            strategy="simple",
            outcome="failure",
        )
        assert memory.lessons_learned == []
        assert memory.timestamp is not None


class TestUserPreference:
    """Tests for the UserPreference model."""

    def test_preference_creation(self):
        """Test creating a UserPreference instance."""
        pref = UserPreference(
            category="naming_convention",
            preference="snake_case",
            confidence=0.85,
            evidence_count=5,
        )
        assert pref.category == "naming_convention"
        assert pref.preference == "snake_case"
        assert pref.confidence == 0.85
        assert pref.evidence_count == 5

    def test_preference_defaults(self):
        """Test UserPreference with default values."""
        pref = UserPreference(
            category="code_style",
            preference="compact",
        )
        assert pref.confidence == 1.0
        assert pref.evidence_count == 1


class TestMemoryStore:
    """Tests for the MemoryStore class."""

    def test_database_initialization(self, temp_db):
        """Test that database is initialized with correct schema."""
        store = MemoryStore(db_path=temp_db)
        assert temp_db.exists()

        # Verify tables exist
        import sqlite3
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = [row[0] for row in cursor.fetchall()]
            assert "run_memories" in tables
            assert "user_preferences" in tables

    def test_save_and_retrieve_run_memory(self, memory_store):
        """Test saving and retrieving a run memory."""
        memory = RunMemory(
            run_id="run-001",
            goal="Add authentication",
            strategy="plan-act-verify",
            outcome="success",
            lessons_learned=["Use JWT tokens", "Hash passwords"],
        )
        memory_store.save_run_memory(memory)

        memories = memory_store.get_run_memories()
        assert len(memories) == 1
        retrieved = memories[0]
        assert retrieved.run_id == "run-001"
        assert retrieved.goal == "Add authentication"
        assert retrieved.outcome == "success"
        assert len(retrieved.lessons_learned) == 2

    def test_get_memories_by_goal_pattern(self, memory_store):
        """Test filtering memories by goal pattern."""
        # Create memories with different goals
        for i, goal in enumerate([
            "Add user authentication",
            "Fix login bug",
            "Implement auth system",
        ]):
            memory = RunMemory(
                run_id=f"run-{i}",
                goal=goal,
                strategy="test",
                outcome="success" if i < 2 else "failure",
            )
            memory_store.save_run_memory(memory)

        # Filter by pattern
        memories = memory_store.get_run_memories(goal_pattern="auth")
        assert len(memories) == 2
        for mem in memories:
            assert "auth" in mem.goal.lower()

    def test_memory_limit(self, memory_store):
        """Test that limit parameter works correctly."""
        for i in range(10):
            memory = RunMemory(
                run_id=f"run-{i}",
                goal=f"Goal {i}",
                strategy="test",
                outcome="success",
            )
            memory_store.save_run_memory(memory)

        memories = memory_store.get_run_memories(limit=5)
        assert len(memories) == 5

    def test_update_existing_memory(self, memory_store):
        """Test that saving same run_id updates existing record."""
        memory = RunMemory(
            run_id="same-run",
            goal="Original goal",
            strategy="original",
            outcome="failure",
        )
        memory_store.save_run_memory(memory)

        # Update with same run_id
        updated = RunMemory(
            run_id="same-run",
            goal="Updated goal",
            strategy="updated",
            outcome="success",
        )
        memory_store.save_run_memory(updated)

        memories = memory_store.get_run_memories()
        assert len(memories) == 1
        assert memories[0].goal == "Updated goal"
        assert memories[0].outcome == "success"

    def test_save_and_retrieve_user_preference(self, memory_store):
        """Test saving and retrieving user preferences."""
        pref = UserPreference(
            category="naming_convention",
            preference="snake_case",
            confidence=0.9,
        )
        memory_store.save_user_preference(pref)

        prefs = memory_store.get_user_preferences()
        assert len(prefs) == 1
        assert prefs[0].category == "naming_convention"
        assert prefs[0].preference == "snake_case"

    def test_preference_confidence_averaging(self, memory_store):
        """Test that confidence is updated with multiple saves."""
        pref1 = UserPreference(
            category="code_style",
            preference="verbose",
            confidence=0.5,
        )
        pref2 = UserPreference(
            category="code_style",
            preference="verbose",
            confidence=0.7,
        )
        memory_store.save_user_preference(pref1)
        memory_store.save_user_preference(pref2)

        prefs = memory_store.get_user_preferences()
        assert len(prefs) == 1
        # Confidence should be averaged: (0.5 + 0.7) / 2 = 0.6
        assert abs(prefs[0].confidence - 0.6) < 0.01
        assert prefs[0].evidence_count == 2

    def test_get_preferences_by_category(self, memory_store):
        """Test filtering preferences by category."""
        prefs = [
            UserPreference(category="naming", preference="snake_case"),
            UserPreference(category="naming", preference="camelCase"),
            UserPreference(category="testing", preference="pytest"),
        ]
        for pref in prefs:
            memory_store.save_user_preference(pref)

        naming_prefs = memory_store.get_user_preferences(category="naming")
        assert len(naming_prefs) == 2
        for p in naming_prefs:
            assert p.category == "naming"

    def test_min_confidence_filter(self, memory_store):
        """Test filtering by minimum confidence."""
        prefs = [
            UserPreference(category="style", preference="A", confidence=0.9),
            UserPreference(category="style", preference="B", confidence=0.6),
            UserPreference(category="style", preference="C", confidence=0.3),
        ]
        for pref in prefs:
            memory_store.save_user_preference(pref)

        high_conf = memory_store.get_user_preferences(min_confidence=0.7)
        assert len(high_conf) == 1
        assert high_conf[0].preference == "A"

    def test_learn_from_run(self, memory_store):
        """Test the learn_from_run convenience method."""
        memory_store.learn_from_run(
            run_id="run-learn",
            goal="Learn from this",
            strategy="incremental",
            outcome="success",
            lessons=["Lesson 1", "Lesson 2"],
        )

        memories = memory_store.get_run_memories()
        assert len(memories) == 1
        assert memories[0].run_id == "run-learn"
        assert memories[0].lessons_learned == ["Lesson 1", "Lesson 2"]

    def test_get_similar_successful_strategies(self, memory_store):
        """Test finding similar successful strategies."""
        # Create successful runs
        memory_store.learn_from_run(
            "s1", "Add authentication to API", "pattern1", "success",
            ["Use JWT"]
        )
        memory_store.learn_from_run(
            "s2", "Fix authentication bug", "pattern2", "success",
            ["Check tokens"]
        )
        memory_store.learn_from_run(
            "s3", "Add user profile", "pattern3", "success",
            []
        )
        memory_store.learn_from_run(
            "f1", "Add authentication", "fail-pattern", "failure",
            []
        )
        memory_store.learn_from_run(
            "s4", "Add database auth layer", "pattern4", "success",
            ["Use ORM"]
        )

        similar = memory_store.get_similar_successful_strategies(
            "Add authentication to service"
        )
        assert len(similar) > 0
        # Should find the auth-related strategies
        for strat in similar:
            assert "auth" in strat["goal"].lower()
            assert strat["strategy"].startswith("pattern")

    def test_infer_preferences_from_actions(self, memory_store):
        """Test inferring preferences from action patterns."""
        actions = [
            {"content": "def my_function using snake_case"},
            {"content": "def another_function"},
            {"content": "class MyClass using PascalCase"},
            {"content": "write tests with pytest"},
        ]
        memory_store.infer_preferences_from_actions(actions)

        prefs = memory_store.get_user_preferences()
        categories = [p.category for p in prefs]
        assert "naming_convention" in categories

    def test_infer_snake_case_preference(self, memory_store):
        """Test inferring snake_case naming preference."""
        actions = [
            {"content": "def my_function():"},
            {"content": "my_variable = 5"},
            {"content": "class_helper_function()"},
        ]
        memory_store.infer_preferences_from_actions(actions)

        naming_prefs = memory_store.get_user_preferences(category="naming_convention")
        assert len(naming_prefs) > 0
        assert naming_prefs[0].preference == "snake_case"


class TestMemoryAugmentedPrompt:
    """Tests for the MemoryAugmentedPrompt class."""

    def test_build_context_with_memories(self, memory_store):
        """Test building context with stored memories."""
        # Store some memories
        memory_store.learn_from_run(
            "r1", "Authentication task", "strategy-auth", "success",
            ["Use secure tokens"]
        )
        memory_store.save_user_preference(
            UserPreference(category="naming_convention", preference="snake_case", confidence=0.9)
        )

        # Create prompt builder
        builder = MemoryAugmentedPrompt(memory_store)
        context = builder.build_context("Authentication implementation")

        assert "Past Similar Successes" in context
        assert "User Preferences" in context

    def test_build_context_empty(self, memory_store):
        """Test building context with no memories."""
        builder = MemoryAugmentedPrompt(memory_store)
        context = builder.build_context("Unknown task")
        assert context == ""

    def test_augment_prompt(self, memory_store):
        """Test augmenting a base prompt with memory context."""
        memory_store.learn_from_run(
            "r1", "Similar task", "strategy1", "success", []
        )
        memory_store.save_user_preference(
            UserPreference(category="style", preference="detailed", confidence=0.8)
        )

        builder = MemoryAugmentedPrompt(memory_store)
        base = "Do this task"
        augmented = builder.augment_prompt(base, "Similar goal")

        assert "##" in augmented
        assert "---" in augmented
        assert "Do this task" in augmented

    def test_augment_prompt_no_context(self, memory_store):
        """Test that base prompt is returned unchanged when no context."""
        builder = MemoryAugmentedPrompt(memory_store)
        base = "Simple task"
        result = builder.augment_prompt(base, "Unique goal")

        assert result == base


class TestMemoryIntegration:
    """Integration tests combining multiple memory features."""

    def test_full_workflow(self, temp_db):
        """Test a full workflow of learning and retrieval."""
        store = MemoryStore(db_path=temp_db)
        prompt_builder = MemoryAugmentedPrompt(store)

        # Execute a "run"
        store.learn_from_run(
            run_id="workflow-001",
            goal="Implement user login",
            strategy="plan-act-verify with JWT",
            outcome="success",
            lessons=["Use oauth2 for login", "Validate tokens early"],
        )

        # Infer preferences from actions
        actions = [
            {"content": "def validate_user_token using snake_case"},
            {"content": "def get_user_profile using snake_case"},
        ]
        store.infer_preferences_from_actions(actions)

        # Build augmented prompt for similar task
        context = prompt_builder.build_context("Add OAuth login functionality")

        assert "plan-act-verify with JWT" in context
        assert "snake_case" in context
        assert "Past Similar Successes" in context
        assert "User Preferences" in context

        # Test serialization/deserialization
        memories = store.get_run_memories()
        assert len(memories) == 1
        assert memories[0].run_id == "workflow-001"

        prefs = store.get_user_preferences()
        assert len(prefs) >= 1
