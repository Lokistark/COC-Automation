"""
Task Planner and Decision Logic for CoC Autonomous AI Game Controller.
Evaluates village state, checks resource/builder prerequisites, ranks tasks,
and computes optimal next actions with transparent reasoning.
"""

from typing import List, Optional, Tuple
from .models import (
    VillageState, Resources, BuilderStatus, BuilderJob, ArmyComposition,
    AIObjective, ActionDecision, UpgradeItem, Priority, TaskStatus
)
from .memory import DatabaseMemory


class TaskPlanner:
    """Evaluates prerequisites and prioritizes village development tasks."""

    def __init__(self, memory: DatabaseMemory):
        self.memory = memory

    def create_initial_state(self) -> VillageState:
        """Constructs an initial realistic baseline state for Town Hall 11."""
        resources = Resources(
            gold=4250000,
            max_gold=8000000,
            elixir=3600000,
            max_elixir=8000000,
            dark_elixir=98000,
            max_dark_elixir=150000,
            gems=1450
        )
        builders = BuilderStatus(
            total_builders=5,
            busy_builders=[
                BuilderJob(
                    job_id="job-1",
                    target_name="Inferno Tower #1",
                    target_level=5,
                    duration_total_seconds=604800,
                    seconds_remaining=86400  # 1 day remaining
                ),
                BuilderJob(
                    job_id="job-2",
                    target_name="Wizard Tower #3",
                    target_level=9,
                    duration_total_seconds=345600,
                    seconds_remaining=14400  # 4 hours remaining
                )
            ]
        )
        army = ArmyComposition(
            housing_used=240,
            housing_max=260,
            troops={
                "Electro Dragon": 4,
                "Balloon": 10,
                "Baby Dragon": 2,
                "Archer": 4
            },
            spells={
                "Rage Spell": 3,
                "Freeze Spell": 3,
                "Poison Spell": 1
            },
            heroes_available=[
                "Barbarian King (Lvl 42)",
                "Archer Queen (Lvl 45)",
                "Grand Warden (Lvl 15)"
            ],
            training_status="Ready (20 Camp Space Idle)"
        )
        objective = AIObjective(
            title="Max Town Hall 11 Air Defenses & Hero Progression",
            description="Prioritize Air Defense upgrades to withstand dragon attacks and level Archer Queen to 50.",
            priority_rank=1,
            target_date="Strategic Milestone 1"
        )

        state = VillageState(
            town_hall_level=11,
            resources=resources,
            builders=builders,
            army=army,
            objective=objective
        )
        state.next_action = self.evaluate_next_action(state)
        return state

    def check_prerequisites(self, task: UpgradeItem, state: VillageState) -> Tuple[bool, str]:
        """Verifies if builders and required resources are available for a given task."""
        if state.builders.free_builders <= 0:
            return False, "No free builders available (all builders busy)."

        resource_type = task.cost_resource.lower().strip()
        cost = task.cost_amount

        if "dark" in resource_type:
            if state.resources.dark_elixir < cost:
                diff = cost - state.resources.dark_elixir
                return False, f"Insufficient Dark Elixir: need {cost:,}, have {state.resources.dark_elixir:,} (short by {diff:,})."
        elif "gold" in resource_type:
            if state.resources.gold < cost:
                diff = cost - state.resources.gold
                return False, f"Insufficient Gold: need {cost:,}, have {state.resources.gold:,} (short by {diff:,})."
        elif "elixir" in resource_type:
            if state.resources.elixir < cost:
                diff = cost - state.resources.elixir
                return False, f"Insufficient Elixir: need {cost:,}, have {state.resources.elixir:,} (short by {diff:,})."

        return True, "Prerequisites satisfied (Builder and resources ready)."

    def evaluate_next_action(self, state: VillageState) -> ActionDecision:
        """Determines the best next action by analyzing tasks and village state."""
        tasks = self.memory.get_tasks()
        pending_tasks = [t for t in tasks if t.status == TaskStatus.PENDING]

        if not pending_tasks:
            return ActionDecision(
                action_type="SCOUT_ATTACK",
                target="Multiplayer Matchmaking",
                prerequisites_met=True,
                confidence=0.88,
                rationale="No pending building upgrades queued. Recommend scouting enemy villages for resource farming."
            )

        # 1. Check if any pending tasks can be executed right now
        for task in pending_tasks:
            can_execute, reason = self.check_prerequisites(task, state)
            if can_execute:
                return ActionDecision(
                    action_type="UPGRADE_BUILDING",
                    target=f"{task.target_name} (Lvl {task.current_level} -> {task.target_level})",
                    prerequisites_met=True,
                    confidence=0.96,
                    rationale=f"High priority target '{task.target_name}' satisfies all constraints. Cost: {task.cost_amount:,} {task.cost_resource}.",
                    cost_resource=task.cost_resource,
                    cost_amount=task.cost_amount
                )

        # 2. If builders are available but resources are low, recommend farming attack
        if state.builders.free_builders > 0 and pending_tasks:
            top_task = pending_tasks[0]
            _, prereq_msg = self.check_prerequisites(top_task, state)
            return ActionDecision(
                action_type="FARM_RESOURCES",
                target=f"Raid for {top_task.cost_resource}",
                prerequisites_met=True,
                confidence=0.91,
                rationale=f"Free builders are waiting on resources for '{top_task.target_name}'. {prereq_msg}",
                cost_resource=None,
                cost_amount=0
            )

        # 3. If builders are full, recommend waiting or troop training
        earliest_builder = min(state.builders.busy_builders, key=lambda b: b.seconds_remaining) if state.builders.busy_builders else None
        time_msg = f"next builder frees up in {earliest_builder.seconds_remaining // 3600}h { (earliest_builder.seconds_remaining % 3600) // 60 }m" if earliest_builder else "no timers"

        return ActionDecision(
            action_type="WAIT",
            target=f"Wait for Builder ({time_msg})",
            prerequisites_met=False,
            confidence=0.85,
            rationale=f"All {state.builders.total_builders} builders are active. Maintain defense shield and await completion of {earliest_builder.target_name if earliest_builder else 'current job'}."
        )
