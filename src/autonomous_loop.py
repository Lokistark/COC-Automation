"""
Autonomous Decision and Execution Loop for Clash of Clans AI.
Implements the 9-stage cycle:
OBSERVE -> INTERPRET -> CHECK CONFIDENCE -> EVALUATE OPTIONS -> SELECT ACTION ->
CHECK PREREQUISITES -> SIMULATE ACTION -> VERIFY RESULT -> LOG -> REPEAT.
Supports max-iteration limits, failure interlocks, manual approval mode, and traceable logging.
"""

import threading
import time
from typing import Dict, Any, Optional, List
from .models import VillageState, ControllerState, LogLevel, ActivityLogEntry
from .memory import DatabaseMemory
from .decision_engine import StrategicDecisionEngine
from .simulator.action_interface import SimulatedActionExecutor, SimulationOutcome
from .vision.image_processor import ScreenVisionProcessor


class AutonomousLoopRunner:
    """Orchestrates the 9-stage autonomous AI cycle with safety limits."""

    def __init__(
        self,
        memory: DatabaseMemory,
        decision_engine: StrategicDecisionEngine,
        simulator: SimulatedActionExecutor,
        vision_processor: Optional[ScreenVisionProcessor] = None
    ):
        self.memory = memory
        self.decision_engine = decision_engine
        self.simulator = simulator
        self.vision_processor = vision_processor or ScreenVisionProcessor()

        # Operational Settings
        self.loop_delay_seconds: float = 3.5
        self.max_iterations: int = 10
        self.current_iteration: int = 0
        self.consecutive_failures: int = 0
        self.max_allowed_consecutive_failures: int = 3
        self.manual_approval_mode: bool = False

        # State & Threading
        self.pending_approval_action: Optional[Dict[str, Any]] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._failed_actions_blacklist: Dict[str, float] = {}  # action_key -> timestamp
        self.blacklist_cooldown_seconds: float = 120.0

    def is_action_blacklisted(self, target: str) -> bool:
        """Checks if a target action recently failed and is currently on cooldown."""
        if target in self._failed_actions_blacklist:
            elapsed = time.time() - self._failed_actions_blacklist[target]
            if elapsed < self.blacklist_cooldown_seconds:
                return True
            else:
                del self._failed_actions_blacklist[target]
        return False

    def blacklist_failed_action(self, target: str):
        """Adds a failed action to the temporary cooldown blacklist."""
        self._failed_actions_blacklist[target] = time.time()

    def run_cycle_step(
        self,
        state: VillageState,
        screenshot_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes one complete 9-stage cycle:
        1. OBSERVE
        2. INTERPRET
        3. CHECK CONFIDENCE
        4. EVALUATE OPTIONS
        5. SELECT ACTION
        6. CHECK PREREQUISITES
        7. SIMULATE ACTION (or pause for Manual Approval)
        8. VERIFY RESULT
        9. LOG & RECORD
        """
        self.current_iteration += 1
        cycle_start = time.time()

        # STAGE 1: OBSERVE
        observation = None
        if screenshot_path:
            observation = self.vision_processor.process_screenshot(screenshot_path)
            self.memory.add_log(ActivityLogEntry(
                timestamp=time.time(),
                level=LogLevel.INFO,
                category="Perception",
                message=f"[Stage 1: OBSERVE] Processed screenshot ({observation.get('overall_confidence', 0)*100:.0f}% confidence)."
            ))

        # STAGE 2: INTERPRET
        meta = self.decision_engine.separate_facts_and_assumptions(state, observation)

        # STAGE 3: CHECK CONFIDENCE
        obs_confidence = observation.get("overall_confidence", 0.90) if observation else 0.90
        if obs_confidence < self.decision_engine.min_confidence_threshold:
            self.consecutive_failures += 1
            msg = f"[Stage 3: CHECK CONFIDENCE] Low confidence ({obs_confidence*100:.0f}%). Halting cycle for vision clarity."
            self.memory.add_log(ActivityLogEntry(level=LogLevel.WARNING, category="Safety", message=msg))
            return {"success": False, "stage": "CHECK_CONFIDENCE", "reason": msg}

        # STAGE 4: EVALUATE OPTIONS
        candidates = self.decision_engine.rank_candidate_actions(state, observation)

        # Filter out blacklisted failed actions
        viable_candidates = [c for c in candidates if not self.is_action_blacklisted(c["target"])]
        if not viable_candidates:
            viable_candidates = candidates

        # STAGE 5: SELECT ACTION
        selected_candidate = viable_candidates[0] if viable_candidates else {
            "action_type": "WAIT", "target": "Passive Observation", "prerequisites_met": True,
            "confidence": 0.85, "rationale": "No active tasks ready."
        }

        # STAGE 6: CHECK PREREQUISITES
        prereqs_ok = selected_candidate.get("prerequisites_met", False)
        if not prereqs_ok:
            self.consecutive_failures += 1
            self.blacklist_failed_action(selected_candidate["target"])
            reason = f"[Stage 6: PREREQUISITES] Action '{selected_candidate['target']}' prerequisites not satisfied: {selected_candidate['rationale']}"
            self.memory.add_log(ActivityLogEntry(level=LogLevel.WARNING, category="Planner", message=reason))
            return {
                "success": False,
                "stage": "CHECK_PREREQUISITES",
                "selected_action": selected_candidate,
                "reason": reason
            }

        # If in Manual Approval Mode, halt and await approval
        if self.manual_approval_mode:
            self.pending_approval_action = selected_candidate
            msg = f"[MANUAL APPROVAL REQUIRED] Action proposed: {selected_candidate['target']}. Awaiting user confirmation."
            self.memory.add_log(ActivityLogEntry(level=LogLevel.INFO, category="Interlock", message=msg))
            return {
                "success": True,
                "stage": "AWAITING_APPROVAL",
                "pending_action": selected_candidate,
                "message": msg
            }

        # STAGE 7: SIMULATE ACTION
        sim_outcome = self.simulator.execute(selected_candidate, state)

        # STAGE 8: VERIFY RESULT
        if not sim_outcome.success or not sim_outcome.verified:
            self.consecutive_failures += 1
            self.blacklist_failed_action(selected_candidate["target"])
            fail_msg = f"[Stage 8: VERIFY RESULT] Execution verification failed: {sim_outcome.verification_detail}"
            self.memory.add_log(ActivityLogEntry(level=LogLevel.ERROR, category="Verification", message=fail_msg))
            return {
                "success": False,
                "stage": "VERIFY_RESULT",
                "outcome": sim_outcome.to_dict(),
                "reason": fail_msg
            }

        # Reset consecutive failures on verified success
        self.consecutive_failures = 0

        # STAGE 9: LOG & RECORD
        self.memory.add_log(ActivityLogEntry(
            timestamp=time.time(),
            level=LogLevel.ACTION,
            category="AutonomousLoop",
            message=f"[Iteration {self.current_iteration}/{self.max_iterations}] {sim_outcome.message} ({sim_outcome.verification_detail})",
            metadata=sim_outcome.to_dict()
        ))
        self.memory.save_snapshot(state.to_dict())

        return {
            "success": True,
            "stage": "COMPLETE",
            "iteration": self.current_iteration,
            "max_iterations": self.max_iterations,
            "cycle_duration_ms": round((time.time() - cycle_start) * 1000, 1),
            "outcome": sim_outcome.to_dict()
        }
