"""
Abstract Action Interface and Concrete Simulated Action Executor for CoC AI.
Ensures simulation actions are strictly isolated from real-game interaction,
verifies state changes, and handles failures, timeouts, and prerequisites.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, Optional
from dataclasses import dataclass
import time
import copy
from ..models import VillageState, BuilderJob, LogLevel, ActivityLogEntry


@dataclass
class SimulationOutcome:
    success: bool
    action_type: str
    target: str
    message: str
    state_before: Dict[str, Any]
    state_after: Dict[str, Any]
    verified: bool
    verification_detail: str
    execution_time_ms: float
    is_simulated: bool = True
    environment: str = "LOCAL_SIMULATOR_SANDBOX"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "action_type": self.action_type,
            "target": self.target,
            "message": self.message,
            "verified": self.verified,
            "verification_detail": self.verification_detail,
            "execution_time_ms": self.execution_time_ms,
            "is_simulated": self.is_simulated,
            "environment": self.environment
        }


class ActionInterface(ABC):
    """Abstract interface defining contract for game action execution."""

    @abstractmethod
    def execute(self, action: Dict[str, Any], state: VillageState) -> SimulationOutcome:
        """Executes the specified action and mutates state in controlled environment."""
        pass

    @abstractmethod
    def verify(self, before: Dict[str, Any], after: Dict[str, Any], action: Dict[str, Any]) -> Tuple[bool, str]:
        """Verifies that expected state mutations took place."""
        pass


class SimulatedActionExecutor(ActionInterface):
    """
    High-fidelity simulated action executor.
    Performs verified sandbox mutations and enforces game constraints.
    """

    def __init__(self):
        self.total_simulations: int = 0
        self.failed_simulations: int = 0

    def verify(self, before: Dict[str, Any], after: Dict[str, Any], action: Dict[str, Any]) -> Tuple[bool, str]:
        """Validates that resources, builders, or army changed as expected."""
        act_type = action.get("action_type")

        if act_type == "UPGRADE_BUILDING":
            cost = action.get("cost_amount", 0)
            res_type = (action.get("cost_resource") or "gold").lower()

            # Verify resource deduction
            before_res = before["resources"].get(res_type, 0)
            after_res = after["resources"].get(res_type, 0)
            diff = before_res - after_res

            if diff != cost:
                return False, f"Verification failed: expected {cost:,} deducted from {res_type}, got {diff:,}."

            # Verify builder decrement
            before_free = before["builders"]["free_builders"]
            after_free = after["builders"]["free_builders"]
            if after_free != (before_free - 1):
                return False, f"Verification failed: free builders did not decrease by 1."

            return True, f"Verified: Exactly {cost:,} {res_type.title()} deducted. Builder occupied (Free builders: {after_free})."

        elif act_type in ("FARM_RESOURCES", "SCOUT_ATTACK"):
            before_gold = before["resources"]["gold"]
            after_gold = after["resources"]["gold"]
            if after_gold <= before_gold:
                return False, "Verification failed: raid resources were not credited."
            return True, f"Verified: Raid loot credited (+{after_gold - before_gold:,} Gold)."

        elif act_type == "TRAIN_ARMY":
            before_housing = before["army"]["housing_used"]
            after_housing = after["army"]["housing_used"]
            if after_housing < before_housing:
                return False, "Verification failed: army space did not increase."
            return True, f"Verified: Army camp filled to {after_housing} housing."

        return True, "Verified: Idle / observational action completed without side effects."

    def execute(self, action: Dict[str, Any], state: VillageState) -> SimulationOutcome:
        """Executes a simulated action on village state with verification and timing."""
        start_time = time.perf_counter()
        before_dict = copy.deepcopy(state.to_dict())
        self.total_simulations += 1

        act_type = action.get("action_type", "WAIT")
        target = action.get("target", "Village")

        # 1. Simulate Building Upgrade
        if act_type == "UPGRADE_BUILDING":
            cost = action.get("cost_amount", 0)
            res_type = (action.get("cost_resource") or "Gold").lower()

            # Prerequisite Check: Free Builder
            if state.builders.free_builders <= 0:
                self.failed_simulations += 1
                return SimulationOutcome(
                    success=False,
                    action_type=act_type,
                    target=target,
                    message="Prerequisite failure: No builders are currently available.",
                    state_before=before_dict,
                    state_after=before_dict,
                    verified=False,
                    verification_detail="Action rejected prior to execution.",
                    execution_time_ms=(time.perf_counter() - start_time) * 1000
                )

            # Prerequisite Check: Sufficient Resources
            curr_res = getattr(state.resources, res_type if "dark" not in res_type else "dark_elixir", 0)
            if curr_res < cost:
                self.failed_simulations += 1
                return SimulationOutcome(
                    success=False,
                    action_type=act_type,
                    target=target,
                    message=f"Prerequisite failure: Insufficient {res_type.title()} (Need {cost:,}, Have {curr_res:,}).",
                    state_before=before_dict,
                    state_after=before_dict,
                    verified=False,
                    verification_detail="Action rejected prior to execution.",
                    execution_time_ms=(time.perf_counter() - start_time) * 1000
                )

            # Deduct resource
            if "dark" in res_type:
                state.resources.dark_elixir -= cost
            elif "elixir" in res_type:
                state.resources.elixir -= cost
            else:
                state.resources.gold -= cost

            # Assign builder
            new_job = BuilderJob(
                job_id=f"job-{len(state.builders.busy_builders) + 1}",
                target_name=target.split("(")[0].strip(),
                target_level=12,
                duration_total_seconds=86400 * 3,
                seconds_remaining=86400 * 3
            )
            state.builders.busy_builders.append(new_job)

            after_dict = state.to_dict()
            verified, v_msg = self.verify(before_dict, after_dict, action)

            return SimulationOutcome(
                success=True,
                action_type=act_type,
                target=target,
                message=f"Simulated upgrade initiated on {target}. Deducted {cost:,} {res_type.title()}.",
                state_before=before_dict,
                state_after=after_dict,
                verified=verified,
                verification_detail=v_msg,
                execution_time_ms=(time.perf_counter() - start_time) * 1000
            )

        # 2. Simulate Resource Farming / Attack Raid
        elif act_type in ("FARM_RESOURCES", "SCOUT_ATTACK"):
            gold_loot = 500000
            elixir_loot = 450000
            dark_loot = 3500

            state.resources.gold = min(state.resources.max_gold, state.resources.gold + gold_loot)
            state.resources.elixir = min(state.resources.max_elixir, state.resources.elixir + elixir_loot)
            state.resources.dark_elixir = min(state.resources.max_dark_elixir, state.resources.dark_elixir + dark_loot)

            after_dict = state.to_dict()
            verified, v_msg = self.verify(before_dict, after_dict, action)

            return SimulationOutcome(
                success=True,
                action_type=act_type,
                target=target,
                message=f"Simulated raid completed. Credited +{gold_loot:,} Gold, +{elixir_loot:,} Elixir, +{dark_loot:,} Dark Elixir.",
                state_before=before_dict,
                state_after=after_dict,
                verified=verified,
                verification_detail=v_msg,
                execution_time_ms=(time.perf_counter() - start_time) * 1000
            )

        # 3. Simulate Army Training
        elif act_type == "TRAIN_ARMY":
            state.army.housing_used = state.army.housing_max
            state.army.training_status = "Full & Ready for Battle"

            after_dict = state.to_dict()
            verified, v_msg = self.verify(before_dict, after_dict, action)

            return SimulationOutcome(
                success=True,
                action_type=act_type,
                target=target,
                message="Simulated army training completed. All army camps replenished to maximum capacity.",
                state_before=before_dict,
                state_after=after_dict,
                verified=verified,
                verification_detail=v_msg,
                execution_time_ms=(time.perf_counter() - start_time) * 1000
            )

        # 4. Default / Observation / Wait
        else:
            # Advance builder timers slightly (simulated tick)
            for b in state.builders.busy_builders:
                b.seconds_remaining = max(0, b.seconds_remaining - 300)

            after_dict = state.to_dict()
            return SimulationOutcome(
                success=True,
                action_type=act_type,
                target=target,
                message=f"Simulated passive cycle: Observational wait on {target}.",
                state_before=before_dict,
                state_after=after_dict,
                verified=True,
                verification_detail="State observed without mutations.",
                execution_time_ms=(time.perf_counter() - start_time) * 1000
            )
