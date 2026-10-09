"""
Automated Unit and Integration Tests for Phase 1.
Tests data models, SQLite memory, task planner rules, controller states, and HTTP API.
"""

import unittest
import os
import tempfile
import time
import json
import threading
from urllib.request import urlopen, Request
from urllib.error import HTTPError

from src.models import (
    Resources, BuilderStatus, BuilderJob, UpgradeItem, Priority,
    TaskStatus, ControllerState, LogLevel, ActivityLogEntry
)
from src.memory import DatabaseMemory
from src.task_planner import TaskPlanner
from src.controller import AgentController
from src.server import ThreadedHTTPServer, make_handler


class TestDataModels(unittest.TestCase):

    def test_resources_serialization(self):
        res = Resources(gold=5000000, max_gold=8000000)
        d = res.to_dict()
        self.assertEqual(d["gold"], 5000000)
        self.assertEqual(d["max_gold"], 8000000)

    def test_builder_status_free_count(self):
        status = BuilderStatus(total_builders=5, busy_builders=[
            BuilderJob("j1", "Cannon", 12, 1000, 500),
            BuilderJob("j2", "Archer Tower", 13, 2000, 1500)
        ])
        self.assertEqual(status.free_builders, 3)
        self.assertEqual(len(status.busy_builders), 2)

    def test_upgrade_item_dict(self):
        item = UpgradeItem(
            id="t-1",
            target_name="Air Defense",
            category="Defense",
            current_level=7,
            target_level=8,
            cost_resource="Gold",
            cost_amount=3000000,
            duration_seconds=86400,
            priority=Priority.HIGH,
            status=TaskStatus.PENDING
        )
        d = item.to_dict()
        self.assertEqual(d["priority"], "HIGH")
        self.assertEqual(d["status"], "PENDING")


class TestDatabaseMemory(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_mem.db")
        self.memory = DatabaseMemory(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_log_insertion_and_retrieval(self):
        entry = ActivityLogEntry(
            timestamp=time.time(),
            level=LogLevel.INFO,
            category="Test",
            message="Unit test log message"
        )
        log_id = self.memory.add_log(entry)
        self.assertIsNotNone(log_id)

        logs = self.memory.get_logs(limit=10)
        self.assertTrue(any(l["message"] == "Unit test log message" for l in logs))

    def test_task_operations(self):
        task = UpgradeItem(
            id="test-task-1",
            target_name="Wizard Tower",
            category="Defense",
            current_level=5,
            target_level=6,
            cost_resource="Gold",
            cost_amount=1500000,
            duration_seconds=50000,
            priority=Priority.HIGH,
            status=TaskStatus.PENDING
        )
        self.memory.add_task(task)

        tasks = self.memory.get_tasks()
        found = next((t for t in tasks if t.id == "test-task-1"), None)
        self.assertIsNotNone(found)
        self.assertEqual(found.target_name, "Wizard Tower")

        self.memory.update_task_status("test-task-1", TaskStatus.IN_PROGRESS)
        tasks = self.memory.get_tasks()
        found = next((t for t in tasks if t.id == "test-task-1"), None)
        self.assertEqual(found.status, TaskStatus.IN_PROGRESS)

        self.memory.delete_task("test-task-1")
        tasks = self.memory.get_tasks()
        self.assertFalse(any(t.id == "test-task-1" for t in tasks))


class TestTaskPlanner(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "planner_test.db")
        self.memory = DatabaseMemory(db_path=self.db_path)
        self.planner = TaskPlanner(memory=self.memory)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_initial_state(self):
        state = self.planner.create_initial_state()
        self.assertEqual(state.town_hall_level, 11)
        self.assertEqual(state.builders.free_builders, 3)
        self.assertIsNotNone(state.next_action)

    def test_prerequisites_check(self):
        state = self.planner.create_initial_state()
        # Affordable task
        affordable_task = UpgradeItem(
            id="aff-1", target_name="Cannon", category="Defense",
            current_level=10, target_level=11, cost_resource="Gold",
            cost_amount=1000000, duration_seconds=10000, priority=Priority.MEDIUM
        )
        ok, msg = self.planner.check_prerequisites(affordable_task, state)
        self.assertTrue(ok)

        # Unaffordable task
        expensive_task = UpgradeItem(
            id="exp-1", target_name="Eagle Artillery", category="Defense",
            current_level=1, target_level=2, cost_resource="Gold",
            cost_amount=20000000, duration_seconds=10000, priority=Priority.HIGH
        )
        ok, msg = self.planner.check_prerequisites(expensive_task, state)
        self.assertFalse(ok)
        self.assertIn("Insufficient Gold", msg)


class TestControllerAndSafety(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "controller_test.db")
        self.memory = DatabaseMemory(db_path=self.db_path)
        self.planner = TaskPlanner(memory=self.memory)
        self.controller = AgentController(memory=self.memory, planner=self.planner)

    def tearDown(self):
        self.controller.stop()
        self.temp_dir.cleanup()

    def test_controller_state_transitions(self):
        self.assertEqual(self.controller.state.controller_status, ControllerState.STOPPED)

        self.controller.pause()
        self.assertEqual(self.controller.state.controller_status, ControllerState.PAUSED)

        self.controller.resume()
        self.assertEqual(self.controller.state.controller_status, ControllerState.RUNNING)

        self.controller.emergency_stop()
        self.assertEqual(self.controller.state.controller_status, ControllerState.EMERGENCY_STOPPED)

    def test_controller_step_execution(self):
        initial_gold = self.controller.state.resources.gold
        initial_free_builders = self.controller.state.builders.free_builders

        step_res = self.controller.step()
        self.assertIn("executed", step_res)
        self.assertTrue(step_res["executed"])

        # Check resource deduction and builder occupancy
        new_gold = self.controller.state.resources.gold
        new_free_builders = self.controller.state.builders.free_builders
        self.assertLess(new_gold, initial_gold)
        self.assertEqual(new_free_builders, initial_free_builders - 1)


class TestServerAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.temp_dir.name, "server_test.db")
        cls.memory = DatabaseMemory(db_path=cls.db_path)
        cls.planner = TaskPlanner(memory=cls.memory)
        cls.controller = AgentController(memory=cls.memory, planner=cls.planner)

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        static_dir = os.path.join(base_dir, "src", "static")

        cls.port = 8899
        handler = make_handler(cls.controller, cls.memory, static_dir)
        cls.server = ThreadedHTTPServer(("127.0.0.1", cls.port), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2.0)
        cls.temp_dir.cleanup()

    def test_api_state(self):
        with urlopen(f"http://127.0.0.1:{self.port}/api/state") as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["town_hall_level"], 11)
            self.assertIn("resources", data)
            self.assertIn("builders", data)

    def test_api_tasks(self):
        with urlopen(f"http://127.0.0.1:{self.port}/api/tasks") as resp:
            self.assertEqual(resp.status, 200)
            tasks = json.loads(resp.read().decode())
            self.assertIsInstance(tasks, list)
            self.assertGreater(len(tasks), 0)

    def test_api_control_step(self):
        req = Request(
            f"http://127.0.0.1:{self.port}/api/control",
            data=json.dumps({"action": "step"}).encode(),
            headers={"Content-Type": "application/json"}
        )
        with urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["status"], "step_executed")


if __name__ == "__main__":
    unittest.main()
