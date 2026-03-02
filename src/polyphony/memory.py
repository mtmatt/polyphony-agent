"""Persistent memory storage for agent learning and user preferences."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


class RunMemory(BaseModel):
    """Memory of a past run with outcome and strategy."""
    run_id: str
    goal: str
    strategy: str
    outcome: str  # "success", "failure", "partial"
    lessons_learned: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class UserPreference(BaseModel):
    """User preference for coding style and conventions."""
    category: str  # e.g., "naming_convention", "code_style", "test_coverage"
    preference: str
    confidence: float = 1.0  # How certain we are about this preference
    evidence_count: int = 1  # Number of times this was inferred
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class MemoryStore:
    """Persistent storage for agent memory using SQLite."""
    
    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = Path.home() / ".polyphony" / "memory.db"
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS run_memories (
                    run_id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    lessons_learned TEXT,  -- JSON list
                    timestamp TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    preference TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    evidence_count INTEGER DEFAULT 1,
                    last_updated TEXT NOT NULL,
                    UNIQUE(category, preference)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_run_memories_goal 
                ON run_memories(goal)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_preferences_category 
                ON user_preferences(category)
            """)
            conn.commit()
    
    def save_run_memory(self, memory: RunMemory) -> None:
        """Save a run memory to the database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO run_memories 
                (run_id, goal, strategy, outcome, lessons_learned, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    memory.run_id,
                    memory.goal,
                    memory.strategy,
                    memory.outcome,
                    json.dumps(memory.lessons_learned),
                    memory.timestamp.isoformat()
                )
            )
            conn.commit()
    
    def get_run_memories(self, goal_pattern: Optional[str] = None, 
                         limit: int = 10) -> list[RunMemory]:
        """Retrieve past run memories, optionally filtered by goal pattern."""
        with sqlite3.connect(self.db_path) as conn:
            if goal_pattern:
                cursor = conn.execute(
                    """
                    SELECT run_id, goal, strategy, outcome, lessons_learned, timestamp
                    FROM run_memories
                    WHERE goal LIKE ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (f"%{goal_pattern}%", limit)
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT run_id, goal, strategy, outcome, lessons_learned, timestamp
                    FROM run_memories
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (limit,)
                )
            
            memories = []
            for row in cursor.fetchall():
                memories.append(RunMemory(
                    run_id=row[0],
                    goal=row[1],
                    strategy=row[2],
                    outcome=row[3],
                    lessons_learned=json.loads(row[4]) if row[4] else [],
                    timestamp=datetime.fromisoformat(row[5])
                ))
            return memories
    
    def save_user_preference(self, pref: UserPreference) -> None:
        """Save or update a user preference."""
        with sqlite3.connect(self.db_path) as conn:
            # Check if preference exists
            cursor = conn.execute(
                "SELECT confidence, evidence_count FROM user_preferences WHERE category = ? AND preference = ?",
                (pref.category, pref.preference)
            )
            existing = cursor.fetchone()
            
            if existing:
                # Update with exponential moving average for confidence
                old_confidence, old_count = existing
                new_count = old_count + 1
                new_confidence = (old_confidence * old_count + pref.confidence) / new_count
                conn.execute(
                    """
                    UPDATE user_preferences 
                    SET confidence = ?, evidence_count = ?, last_updated = ?
                    WHERE category = ? AND preference = ?
                    """,
                    (new_confidence, new_count, datetime.utcnow().isoformat(),
                     pref.category, pref.preference)
                )
            else:
                conn.execute(
                    """
                    INSERT INTO user_preferences (category, preference, confidence, evidence_count, last_updated)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (pref.category, pref.preference, pref.confidence, 
                     pref.evidence_count, datetime.utcnow().isoformat())
                )
            conn.commit()
    
    def get_user_preferences(self, category: Optional[str] = None,
                              min_confidence: float = 0.5) -> list[UserPreference]:
        """Retrieve user preferences, optionally filtered by category."""
        with sqlite3.connect(self.db_path) as conn:
            if category:
                cursor = conn.execute(
                    """
                    SELECT category, preference, confidence, evidence_count, last_updated
                    FROM user_preferences
                    WHERE category = ? AND confidence >= ?
                    ORDER BY confidence DESC, evidence_count DESC
                    """,
                    (category, min_confidence)
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT category, preference, confidence, evidence_count, last_updated
                    FROM user_preferences
                    WHERE confidence >= ?
                    ORDER BY confidence DESC, evidence_count DESC
                    """,
                    (min_confidence,)
                )
            
            prefs = []
            for row in cursor.fetchall():
                prefs.append(UserPreference(
                    category=row[0],
                    preference=row[1],
                    confidence=row[2],
                    evidence_count=row[3],
                    last_updated=datetime.fromisoformat(row[4])
                ))
            return prefs
    
    def learn_from_run(self, run_id: str, goal: str, strategy: str,
                       outcome: str, lessons: list[str]) -> None:
        """Record a completed run with its outcome and lessons."""
        memory = RunMemory(
            run_id=run_id,
            goal=goal,
            strategy=strategy,
            outcome=outcome,
            lessons_learned=lessons
        )
        self.save_run_memory(memory)
    
    def get_similar_successful_strategies(self, goal: str, 
                                          limit: int = 3) -> list[dict[str, Any]]:
        """Find successful strategies from similar past goals."""
        # Simple keyword matching - could be enhanced with embeddings
        keywords = [w.lower() for w in goal.split() if len(w) > 3]
        if not keywords:
            return []
        
        memories = self.get_run_memories(limit=50)
        scored = []
        
        for mem in memories:
            if mem.outcome != "success":
                continue
            score = sum(1 for kw in keywords if kw in mem.goal.lower())
            if score > 0:
                scored.append((score, mem))
        
        scored.sort(reverse=True, key=lambda x: x[0])
        return [
            {
                "goal": mem.goal,
                "strategy": mem.strategy,
                "lessons": mem.lessons_learned
            }
            for _, mem in scored[:limit]
        ]
    
    def infer_preferences_from_actions(self, actions: list[dict[str, Any]]) -> None:
        """Infer user preferences from a series of actions."""
        # Look for patterns in coding style
        naming_patterns = {}
        test_patterns = {}
        
        for action in actions:
            content = action.get("content", "")
            
            # Detect naming conventions
            if "snake_case" in content.lower() or "_" in content:
                naming_patterns["snake_case"] = naming_patterns.get("snake_case", 0) + 1
            if "camelCase" in content.lower():
                naming_patterns["camelCase"] = naming_patterns.get("camelCase", 0) + 1
            if "PascalCase" in content.lower():
                naming_patterns["PascalCase"] = naming_patterns.get("PascalCase", 0) + 1
            
            # Detect test preferences
            if "pytest" in content.lower():
                test_patterns["pytest"] = test_patterns.get("pytest", 0) + 1
            if "unittest" in content.lower():
                test_patterns["unittest"] = test_patterns.get("unittest", 0) + 1
        
        # Save inferred preferences
        if naming_patterns:
            top_style = max(naming_patterns, key=naming_patterns.get)
            self.save_user_preference(UserPreference(
                category="naming_convention",
                preference=top_style,
                confidence=min(0.9, 0.5 + naming_patterns[top_style] * 0.1)
            ))
        
        if test_patterns:
            top_framework = max(test_patterns, key=test_patterns.get)
            self.save_user_preference(UserPreference(
                category="testing_framework",
                preference=top_framework,
                confidence=min(0.9, 0.5 + test_patterns[top_framework] * 0.1)
            ))


class MemoryAugmentedPrompt:
    """Helper class to augment prompts with memory context."""
    
    def __init__(self, memory_store: MemoryStore):
        self.memory = memory_store
    
    def build_context(self, goal: str) -> str:
        """Build memory context to prepend to prompts."""
        sections = []
        
        # Add similar successful strategies
        similar = self.memory.get_similar_successful_strategies(goal)
        if similar:
            sections.append("## Past Similar Successes\n")
            for i, strat in enumerate(similar, 1):
                sections.append(f"{i}. Goal: {strat['goal']}")
                sections.append(f"   Strategy: {strat['strategy']}")
                if strat['lessons']:
                    sections.append(f"   Lessons: {', '.join(strat['lessons'])}")
                sections.append("")
        
        # Add user preferences
        prefs = self.memory.get_user_preferences()
        if prefs:
            sections.append("## User Preferences\n")
            for pref in prefs[:5]:  # Top 5 preferences
                sections.append(f"- {pref.category}: {pref.preference} "
                              f"(confidence: {pref.confidence:.2f})")
            sections.append("")
        
        return "\n".join(sections)
    
    def augment_prompt(self, base_prompt: str, goal: str) -> str:
        """Augment a base prompt with memory context."""
        context = self.build_context(goal)
        if not context:
            return base_prompt
        return f"{context}\n---\n{base_prompt}"
