"""
Autonomous Action Controller for CoC AI Game Controller.
Coordinates ScreenVisionProcessor, StrategicDecisionEngine, StrategicAttackPlanner,
SimulatedActionExecutor, and AutonomousLoopRunner in a unified, safe architecture.
"""

import threading
import time
from typing import Dict, Any, Optional, List
from .models import (
    VillageState, ControllerState, LogLevel, ActivityLogEntry
)
from .memory import DatabaseMemory
from .task_planner import TaskPlanner
from .decision_engine import StrategicDecisionEngine
from .attack_planner import StrategicAttackPlanner
from .simulator.action_interface import SimulatedActionExecutor
from .autonomous_loop import AutonomousLoopRunner
from .vision.image_processor import ScreenVisionProcessor


class AgentController:
    """Master controller managing vision, reasoning, planning, simulation, and loop safety."""

    def __init__(self, memory: DatabaseMemory, planner: TaskPlanner):
        self.memory = memory
        self.planner = planner
        self.vision = ScreenVisionProcessor()
        self.decision_engine = StrategicDecisionEngine(memory=memory)
        self.attack_planner = StrategicAttackPlanner(memory=memory, vision_processor=self.vision)
        self.simulator = SimulatedActionExecutor()
        self.loop_runner = AutonomousLoopRunner(
            memory=memory,
            decision_engine=self.decision_engine,
            simulator=self.simulator,
            vision_processor=self.vision
        )

        self.state: VillageState = self.planner.create_initial_state()
        self.state.controller_status = ControllerState.STOPPED
        self._lock = threading.Lock()
        self._loop_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self.latest_screenshot_path: Optional[str] = None
        self.latest_observation: Optional[Dict[str, Any]] = None

    def get_state(self) -> Dict[str, Any]:
        """Thread-safe snapshot of village state, controller status, and loop telemetry."""
        with self._lock:
            # Re-evaluate next action using decision engine
            self.state.next_action = self.decision_engine.decide_best_action(self.state, self.latest_observation)
            state_dict = self.state.to_dict()

            state_dict["loop_telemetry"] = {
                "iteration": self.loop_runner.current_iteration,
                "max_iterations": self.loop_runner.max_iterations,
                "consecutive_failures": self.loop_runner.consecutive_failures,
                "manual_approval_mode": self.loop_runner.manual_approval_mode,
                "pending_approval": self.loop_runner.pending_approval_action,
                "delay_seconds": self.loop_runner.loop_delay_seconds
            }
            state_dict["latest_observation"] = self.latest_observation
            return state_dict

    def set_status(self, new_status: ControllerState):
        """Updates controller status and logs change."""
        with self._lock:
            old_status = self.state.controller_status
            self.state.controller_status = new_status

        self.memory.add_log(ActivityLogEntry(
            timestamp=time.time(),
            level=LogLevel.WARNING if new_status == ControllerState.EMERGENCY_STOPPED else LogLevel.INFO,
            category="Controller",
            message=f"Controller status transitioned from {old_status.value} to {new_status.value}."
        ))

    def start(self):
        """Starts the autonomous simulation loop thread."""
        with self._lock:
            if self.state.controller_status == ControllerState.RUNNING:
                return
            self.state.controller_status = ControllerState.RUNNING
            self._stop_event.clear()
            self._pause_event.clear()
            self.loop_runner.current_iteration = 0
            self.loop_runner.consecutive_failures = 0

        self.memory.add_log(ActivityLogEntry(
            timestamp=time.time(),
            level=LogLevel.INFO,
            category="Controller",
            message=f"Autonomous loop started (Max Iterations: {self.loop_runner.max_iterations}, Mode: {'Manual Approval' if self.loop_runner.manual_approval_mode else 'Autonomous Sandbox'})."
        ))

        if self._loop_thread is None or not self._loop_thread.is_alive():
            self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
            self._loop_thread.start()

    def pause(self):
        """Pauses the autonomous execution loop."""
        self._pause_event.set()
        self.set_status(ControllerState.PAUSED)

    def resume(self):
        """Resumes the autonomous execution loop."""
        self._pause_event.clear()
        self.set_status(ControllerState.RUNNING)

    def stop(self):
        """Stops the autonomous loop cleanly."""
        self._stop_event.set()
        self.set_status(ControllerState.STOPPED)

    def emergency_stop(self):
        """Halts all processing immediately and triggers safety interlock."""
        self._stop_event.set()
        self._pause_event.set()
        with self._lock:
            self.state.controller_status = ControllerState.EMERGENCY_STOPPED
            self.loop_runner.pending_approval_action = None

        self.memory.add_log(ActivityLogEntry(
            timestamp=time.time(),
            level=LogLevel.ERROR,
            category="Safety",
            message="EMERGENCY STOP TRIGGERED: All actions halted immediately. Interlock engaged."
        ))

    def reset_state(self):
        """Resets the state back to baseline defaults."""
        with self._lock:
            self.state = self.planner.create_initial_state()
            self.state.controller_status = ControllerState.STOPPED
            self.loop_runner.current_iteration = 0
            self.loop_runner.consecutive_failures = 0
            self.loop_runner.pending_approval_action = None

        self.memory.add_log(ActivityLogEntry(
            timestamp=time.time(),
            level=LogLevel.INFO,
            category="Controller",
            message="Village state and task planner reset to baseline sample data."
        ))

    def set_loop_mode(self, manual_approval: bool, max_iterations: int = 10, delay_seconds: float = 3.5):
        """Configures loop operational parameters."""
        self.loop_runner.manual_approval_mode = manual_approval
        self.loop_runner.max_iterations = max(1, max_iterations)
        self.loop_runner.loop_delay_seconds = max(1.0, delay_seconds)

    def approve_pending_action(self) -> Dict[str, Any]:
        """User confirms execution of proposed action in Manual Approval Mode."""
        with self._lock:
            pending = self.loop_runner.pending_approval_action
            if not pending:
                return {"success": False, "message": "No pending action to approve."}

            # Execute via simulator
            sim_outcome = self.simulator.execute(pending, self.state)
            self.loop_runner.pending_approval_action = None

        self.memory.add_log(ActivityLogEntry(
            timestamp=time.time(),
            level=LogLevel.ACTION,
            category="ManualApproval",
            message=f"USER APPROVED: {sim_outcome.message} ({sim_outcome.verification_detail})"
        ))
        return sim_outcome.to_dict()

    def process_screenshot(self, image_path: str) -> Dict[str, Any]:
        """Runs vision processor on a screenshot file and caches observation."""
        obs = self.vision.process_screenshot(image_path)
        with self._lock:
            self.latest_screenshot_path = image_path
            self.latest_observation = obs
        return obs

    def step(self, screenshot_path: Optional[str] = None) -> Dict[str, Any]:
        """Executes a single 9-stage cycle tick."""
        with self._lock:
            img_path = screenshot_path or self.latest_screenshot_path
            cycle_result = self.loop_runner.run_cycle_step(self.state, img_path)
            # Re-evaluate next action
            self.state.next_action = self.decision_engine.decide_best_action(self.state, self.latest_observation)
            # Backwards compatibility with Phase 1
            cycle_result["executed"] = cycle_result.get("success", False)
            if "outcome" in cycle_result:
                cycle_result["message"] = cycle_result["outcome"].get("message", "")
            return cycle_result

    def _run_loop(self):
        """Background thread executing autonomous steps continuously when RUNNING."""
        while not self._stop_event.is_set():
            if self._pause_event.is_set():
                time.sleep(0.5)
                continue

            with self._lock:
                status = self.state.controller_status
                iteration = self.loop_runner.current_iteration
                max_iter = self.loop_runner.max_iterations
                failures = self.loop_runner.consecutive_failures

            if status != ControllerState.RUNNING:
                time.sleep(0.5)
                continue

            # Check Safety Limits
            if iteration >= max_iter:
                self.memory.add_log(ActivityLogEntry(
                    level=LogLevel.INFO,
                    category="AutonomousLoop",
                    message=f"Loop reached configured maximum iterations ({max_iter}). Stopping safely."
                ))
                self.stop()
                break

            if failures >= self.loop_runner.max_allowed_consecutive_failures:
                self.memory.add_log(ActivityLogEntry(
                    level=LogLevel.ERROR,
                    category="Safety",
                    message=f"Interlock tripped: {failures} consecutive cycle failures. Halting loop to prevent invalid operations."
                ))
                self.emergency_stop()
                break

            # If waiting for manual approval, do not auto-step
            if self.loop_runner.manual_approval_mode and self.loop_runner.pending_approval_action:
                time.sleep(1.0)
                continue

            self.step()
            time.sleep(self.loop_runner.loop_delay_seconds)
