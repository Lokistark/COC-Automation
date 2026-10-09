"""
Rule-Based Strategic Decision Engine for Clash of Clans AI.
Ranks candidate actions, checks strict prerequisites, manages resource overflow,
separates observed facts from assumptions, and handles uncertainty safely.
"""

import time
from typing import List, Dict, Any, Optional
from .models import (
    VillageState, Resources, BuilderStatus, UpgradeItem, ActionDecision,
    Priority, TaskStatus
)
from .memory import DatabaseMemory


class StrategicDecisionEngine:
    """Evaluates game state and generates prioritized, explainable action decisions."""

    def __init__(self, memory: DatabaseMemory):
        self.memory = memory
        self.stale_threshold_seconds: float = 300.0  # 5 minutes
        self.min_confidence_threshold: float = 0.60

    def separate_facts_and_assumptions(
        self,
        state: VillageState,
        observation: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Separates firmly verified game facts from heuristic assumptions."""
        facts = {
            "town_hall_level": state.town_hall_level,
            "total_builders": state.builders.total_builders,
            "free_builders": state.builders.free_builders,
            "resources": {
                "gold": state.resources.gold,
                "elixir": state.resources.elixir,
                "dark_elixir": state.resources.dark_elixir
            }
        }

        assumptions = []
        if observation:
            if observation.get("overall_confidence", 1.0) < 0.85:
                assumptions.append("Resource values partially derived from visual segmentation heuristics rather than direct OCR verification.")
            if observation.get("is_enemy_base", False):
                assumptions.append("Current view identified as enemy base based on red perimeter detection.")
            for unc in observation.get("uncertainties", []):
                assumptions.append(f"Uncertainty: {unc}")
        else:
            assumptions.append("Current state based on stored local snapshot; live visual confirmation pending.")

        # Check data freshness
        is_stale = (time.time() - state.timestamp) > self.stale_threshold_seconds
        if is_stale:
            assumptions.append("State snapshot is older than 5 minutes. Real-time builder timers may have progressed.")

        return {
            "facts": facts,
            "assumptions": assumptions,
            "is_stale": is_stale
        }

    def rank_candidate_actions(
        self,
        state: VillageState,
        observation: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Generates and ranks all feasible candidate actions based on strategic rules:
        1. Handle low confidence / stale data first
        2. Prevent resource overflow
        3. Maximize builder uptime
        4. Advance hero and defense upgrades
        5. Army training and scouting
        """
        candidates: List[Dict[str, Any]] = []
        meta = self.separate_facts_and_assumptions(state, observation)

        # RULE 1: Safety & Uncertainty Check
        if observation and observation.get("overall_confidence", 1.0) < self.min_confidence_threshold:
            candidates.append({
                "rank": 1,
                "action_type": "RE_OBSERVE",
                "target": "Capture High-Resolution Screenshot",
                "score": 100.0,
                "prerequisites_met": True,
                "confidence": observation.get("overall_confidence", 0.5),
                "rationale": f"Observation confidence ({observation.get('overall_confidence', 0):.2f}) is below safe threshold (0.60). Avoid costly upgrades until vision is verified.",
                "is_assumption": True
            })
            return candidates

        # RULE 2: Resource Overflow Prevention (Storages > 88% full)
        gold_pct = state.resources.gold / max(1, state.resources.max_gold)
        elixir_pct = state.resources.elixir / max(1, state.resources.max_elixir)
        overflow_danger = gold_pct > 0.88 or elixir_pct > 0.88

        tasks = self.memory.get_tasks()
        pending_tasks = [t for t in tasks if t.status == TaskStatus.PENDING]

        # Evaluate all pending tasks
        for task in pending_tasks:
            # Check prerequisites
            has_builder = state.builders.free_builders > 0
            res_type = task.cost_resource.lower()
            has_resources = False
            deficit = 0

            if "gold" in res_type:
                has_resources = state.resources.gold >= task.cost_amount
                deficit = max(0, task.cost_amount - state.resources.gold)
            elif "dark" in res_type:
                has_resources = state.resources.dark_elixir >= task.cost_amount
                deficit = max(0, task.cost_amount - state.resources.dark_elixir)
            elif "elixir" in res_type:
                has_resources = state.resources.elixir >= task.cost_amount
                deficit = max(0, task.cost_amount - state.resources.elixir)

            prereqs_met = has_builder and has_resources

            # Scoring algorithm
            base_score = 50.0
            if task.priority == Priority.HIGH:
                base_score += 30.0
            elif task.priority == Priority.MEDIUM:
                base_score += 15.0

            # Boost if category matches high value (Hero or key Defense)
            if task.category in ("Hero", "Defense"):
                base_score += 10.0

            # Boost if preventing overflow
            if overflow_danger and ("gold" in res_type and gold_pct > 0.88):
                base_score += 25.0
            if overflow_danger and ("elixir" in res_type and elixir_pct > 0.88):
                base_score += 25.0

            if not prereqs_met:
                base_score -= 40.0  # Penalize if currently blocked

            rationale_parts = []
            if prereqs_met:
                rationale_parts.append(f"Prerequisites satisfied. Builder free and {task.cost_amount:,} {task.cost_resource} verified.")
            else:
                if not has_builder:
                    rationale_parts.append("Blocked: All builders busy.")
                if not has_resources:
                    rationale_parts.append(f"Blocked: Need {deficit:,} more {task.cost_resource}.")

            if overflow_danger:
                rationale_parts.append("Storage near capacity! High priority to prevent loot loss.")

            candidates.append({
                "action_type": "UPGRADE_BUILDING",
                "target": f"{task.target_name} (Lvl {task.current_level} -> {task.target_level})",
                "score": max(0.0, base_score),
                "prerequisites_met": prereqs_met,
                "confidence": 0.94 if prereqs_met else 0.80,
                "rationale": " ".join(rationale_parts),
                "is_assumption": False,
                "task_id": task.id,
                "cost_resource": task.cost_resource,
                "cost_amount": task.cost_amount
            })

        # RULE 3: Army Training & Farming Option
        camp_full = state.army.housing_used >= state.army.housing_max
        if not camp_full:
            candidates.append({
                "action_type": "TRAIN_ARMY",
                "target": f"Queue Troops ({state.army.housing_max - state.army.housing_used} space idle)",
                "score": 65.0,
                "prerequisites_met": True,
                "confidence": 0.90,
                "rationale": f"Army camp has {state.army.housing_max - state.army.housing_used} open housing space. Replenish attack force.",
                "is_assumption": False
            })

        # RULE 4: Resource Raid / Scouting
        if state.builders.free_builders > 0 and any(not c["prerequisites_met"] for c in candidates):
            candidates.append({
                "action_type": "SCOUT_ATTACK",
                "target": "Multiplayer Matchmaking Raid",
                "score": 75.0,
                "prerequisites_met": camp_full,
                "confidence": 0.88,
                "rationale": "Free builders are waiting on resources. Full army ready for high-loot farming raid.",
                "is_assumption": False
            })

        # RULE 5: Wait / Observe if all builders busy
        if state.builders.free_builders == 0:
            candidates.append({
                "action_type": "WAIT",
                "target": "Await Builder Completion",
                "score": 55.0,
                "prerequisites_met": True,
                "confidence": 0.95,
                "rationale": "All builders active. No construction action can be started right now.",
                "is_assumption": False
            })

        # Sort candidates descending by score
        candidates.sort(key=lambda c: c["score"], reverse=True)
        for i, c in enumerate(candidates, 1):
            c["rank"] = i

        return candidates

    def decide_best_action(
        self,
        state: VillageState,
        observation: Optional[Dict[str, Any]] = None
    ) -> ActionDecision:
        """Selects the highest ranked actionable candidate."""
        ranked = self.rank_candidate_actions(state, observation)
        if not ranked:
            return ActionDecision(
                action_type="IDLE",
                target="Monitor Village",
                prerequisites_met=True,
                confidence=0.80,
                rationale="Village state steady. No immediate tasks in queue."
            )

        best = ranked[0]
        return ActionDecision(
            action_type=best["action_type"],
            target=best["target"],
            prerequisites_met=best["prerequisites_met"],
            confidence=best["confidence"],
            rationale=best["rationale"],
            cost_resource=best.get("cost_resource"),
            cost_amount=best.get("cost_amount", 0)
        )
