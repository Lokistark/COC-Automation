"""
Memory module for CoC Autonomous AI Game Controller.
Provides SQLite-based persistence for activity logs, task lists, and game state snapshots.
"""

import sqlite3
import json
import time
import os
from contextlib import contextmanager
from typing import List, Dict, Optional, Any
from .models import ActivityLogEntry, UpgradeItem, LogLevel, Priority, TaskStatus


class DatabaseMemory:
    """Manages persistent SQLite storage for logs, planned tasks, and state history."""

    def __init__(self, db_path: str = "data/coc_memory.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._init_db()

    @contextmanager
    def _connection(self):
        """Context manager that ensures the SQLite connection is committed and closed."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        """Initializes tables for logs, tasks, and snapshots."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS activity_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    level TEXT NOT NULL,
                    category TEXT NOT NULL,
                    message TEXT NOT NULL,
                    metadata_json TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    target_name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    current_level INTEGER NOT NULL,
                    target_level INTEGER NOT NULL,
                    cost_resource TEXT NOT NULL,
                    cost_amount INTEGER NOT NULL,
                    duration_seconds INTEGER NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS state_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    snapshot_json TEXT NOT NULL
                )
            """)
            conn.commit()

        # Seed sample data if tasks table is empty
        self._seed_default_data_if_needed()

    def _seed_default_data_if_needed(self):
        """Seeds initial realistic sample tasks and log events if empty."""
        tasks = self.get_tasks()
        if not tasks:
            sample_tasks = [
                UpgradeItem(
                    id="task-1",
                    target_name="Air Defense #3",
                    category="Defense",
                    current_level=8,
                    target_level=9,
                    cost_resource="Gold",
                    cost_amount=4000000,
                    duration_seconds=432000,
                    priority=Priority.HIGH,
                    status=TaskStatus.PENDING
                ),
                UpgradeItem(
                    id="task-2",
                    target_name="Elixir Storage #2",
                    category="Resource",
                    current_level=11,
                    target_level=12,
                    cost_resource="Gold",
                    cost_amount=2500000,
                    duration_seconds=259200,
                    priority=Priority.MEDIUM,
                    status=TaskStatus.PENDING
                ),
                UpgradeItem(
                    id="task-3",
                    target_name="Archer Queen",
                    category="Hero",
                    current_level=45,
                    target_level=46,
                    cost_resource="Dark Elixir",
                    cost_amount=92000,
                    duration_seconds=518400,
                    priority=Priority.HIGH,
                    status=TaskStatus.PENDING
                ),
                UpgradeItem(
                    id="task-4",
                    target_name="Army Camp #4",
                    category="Army",
                    current_level=8,
                    target_level=9,
                    cost_resource="Elixir",
                    cost_amount=5000000,
                    duration_seconds=604800,
                    priority=Priority.LOW,
                    status=TaskStatus.PENDING
                ),
                UpgradeItem(
                    id="task-5",
                    target_name="Hidden Tesla #1",
                    category="Defense",
                    current_level=8,
                    target_level=9,
                    cost_resource="Gold",
                    cost_amount=3500000,
                    duration_seconds=345600,
                    priority=Priority.MEDIUM,
                    status=TaskStatus.PENDING
                )
            ]
            for task in sample_tasks:
                self.add_task(task)

            self.add_log(ActivityLogEntry(
                timestamp=time.time() - 3600,
                level=LogLevel.INFO,
                category="System",
                message="Memory subsystem initialized with SQLite persistence."
            ))
            self.add_log(ActivityLogEntry(
                timestamp=time.time() - 1800,
                level=LogLevel.INFO,
                category="Perception",
                message="Village baseline loaded: Town Hall 11 detected with 5 Builders."
            ))
            self.add_log(ActivityLogEntry(
                timestamp=time.time() - 600,
                level=LogLevel.ACTION,
                category="Planner",
                message="Evaluated upgrade priorities. Air Defense #3 tagged as top priority."
            ))

    def add_log(self, entry: ActivityLogEntry) -> int:
        """Appends a new activity log entry."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO activity_logs (timestamp, level, category, message, metadata_json)
                VALUES (?, ?, ?, ?, ?)
            """, (
                entry.timestamp,
                entry.level.value if isinstance(entry.level, LogLevel) else entry.level,
                entry.category,
                entry.message,
                json.dumps(entry.metadata)
            ))
            conn.commit()
            return cursor.lastrowid

    def get_logs(self, limit: int = 50, level: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves recent activity logs ordered by timestamp descending."""
        with self._connection() as conn:
            cursor = conn.cursor()
            if level and level != "ALL":
                cursor.execute("""
                    SELECT id, timestamp, level, category, message, metadata_json
                    FROM activity_logs
                    WHERE level = ?
                    ORDER BY id DESC LIMIT ?
                """, (level, limit))
            else:
                cursor.execute("""
                    SELECT id, timestamp, level, category, message, metadata_json
                    FROM activity_logs
                    ORDER BY id DESC LIMIT ?
                """, (limit,))
            rows = cursor.fetchall()

        logs = []
        for r in rows:
            logs.append({
                "id": r["id"],
                "timestamp": r["timestamp"],
                "level": r["level"],
                "category": r["category"],
                "message": r["message"],
                "metadata": json.loads(r["metadata_json"] or "{}")
            })
        return logs

    def clear_logs(self):
        """Clears all activity logs."""
        with self._connection() as conn:
            conn.execute("DELETE FROM activity_logs")
            conn.commit()

    def add_task(self, task: UpgradeItem):
        """Inserts or updates a task in the planner queue."""
        with self._connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO tasks 
                (id, target_name, category, current_level, target_level, cost_resource, cost_amount, duration_seconds, priority, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.id,
                task.target_name,
                task.category,
                task.current_level,
                task.target_level,
                task.cost_resource,
                task.cost_amount,
                task.duration_seconds,
                task.priority.value if isinstance(task.priority, Priority) else task.priority,
                task.status.value if isinstance(task.status, TaskStatus) else task.status,
                time.time()
            ))
            conn.commit()

    def get_tasks(self) -> List[UpgradeItem]:
        """Returns all tasks sorted by priority and created_at."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, target_name, category, current_level, target_level, cost_resource, cost_amount, duration_seconds, priority, status
                FROM tasks
                ORDER BY CASE priority 
                    WHEN 'HIGH' THEN 1 
                    WHEN 'MEDIUM' THEN 2 
                    ELSE 3 END, created_at ASC
            """)
            rows = cursor.fetchall()

        tasks = []
        for r in rows:
            tasks.append(UpgradeItem(
                id=r["id"],
                target_name=r["target_name"],
                category=r["category"],
                current_level=r["current_level"],
                target_level=r["target_level"],
                cost_resource=r["cost_resource"],
                cost_amount=r["cost_amount"],
                duration_seconds=r["duration_seconds"],
                priority=Priority(r["priority"]),
                status=TaskStatus(r["status"])
            ))
        return tasks

    def update_task_status(self, task_id: str, status: TaskStatus):
        """Updates task execution status."""
        with self._connection() as conn:
            conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (
                status.value if isinstance(status, TaskStatus) else status,
                task_id
            ))
            conn.commit()

    def delete_task(self, task_id: str):
        """Removes a task from the planner."""
        with self._connection() as conn:
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()

    def save_snapshot(self, state_dict: Dict[str, Any]):
        """Saves a point-in-time snapshot of the game state."""
        with self._connection() as conn:
            conn.execute("""
                INSERT INTO state_snapshots (timestamp, snapshot_json)
                VALUES (?, ?)
            """, (time.time(), json.dumps(state_dict)))
            conn.commit()
