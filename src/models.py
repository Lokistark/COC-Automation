"""
Data models for CoC Autonomous AI Game Controller.
Defines strongly-typed representations for village state, resources,
builders, upgrades, army compositions, decisions, and activity logs.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional, Any
import time


class ControllerState(str, Enum):
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    EMERGENCY_STOPPED = "EMERGENCY_STOPPED"


class LogLevel(str, Enum):
    INFO = "INFO"
    ACTION = "ACTION"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Priority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class Resources:
    gold: int = 4500000
    max_gold: int = 8000000
    elixir: int = 3800000
    max_elixir: int = 8000000
    dark_elixir: int = 95000
    max_dark_elixir: int = 150000
    gems: int = 1420

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BuilderJob:
    job_id: str
    target_name: str
    target_level: int
    duration_total_seconds: int
    seconds_remaining: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BuilderStatus:
    total_builders: int = 5
    busy_builders: List[BuilderJob] = field(default_factory=list)

    @property
    def free_builders(self) -> int:
        return max(0, self.total_builders - len(self.busy_builders))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_builders": self.total_builders,
            "free_builders": self.free_builders,
            "busy_builders": [b.to_dict() for b in self.busy_builders]
        }


@dataclass
class UpgradeItem:
    id: str
    target_name: str
    category: str  # Defense, Resource, Army, Hero
    current_level: int
    target_level: int
    cost_resource: str  # Gold, Elixir, Dark Elixir
    cost_amount: int
    duration_seconds: int
    priority: Priority = Priority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["priority"] = self.priority.value
        res["status"] = self.status.value
        return res


@dataclass
class ArmyComposition:
    housing_used: int = 240
    housing_max: int = 260
    troops: Dict[str, int] = field(default_factory=lambda: {
        "Electro Dragon": 4,
        "Balloon": 10,
        "Baby Dragon": 2,
        "Archer": 4
    })
    spells: Dict[str, int] = field(default_factory=lambda: {
        "Rage Spell": 3,
        "Freeze Spell": 3,
        "Poison Spell": 1
    })
    heroes_available: List[str] = field(default_factory=lambda: [
        "Barbarian King (Lvl 42)",
        "Archer Queen (Lvl 45)",
        "Grand Warden (Lvl 15)"
    ])
    training_status: str = "Ready for Battle"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AIObjective:
    title: str = "Defense Fortification & Town Hall 11 Optimization"
    description: str = "Upgrade air defenses and inferno towers before offensive camp expansions to guard storages."
    priority_rank: int = 1
    target_date: str = "Phase 1 Baseline"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ActionDecision:
    action_type: str  # UPGRADE_BUILDING, COLLECT_RESOURCES, TRAIN_ARMY, SCOUT_ATTACK, WAIT
    target: str
    prerequisites_met: bool
    confidence: float
    rationale: str
    cost_resource: Optional[str] = None
    cost_amount: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ActivityLogEntry:
    id: Optional[int] = None
    timestamp: float = field(default_factory=time.time)
    level: LogLevel = LogLevel.INFO
    category: str = "System"
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["level"] = self.level.value
        return res


@dataclass
class VillageState:
    town_hall_level: int = 11
    resources: Resources = field(default_factory=Resources)
    builders: BuilderStatus = field(default_factory=BuilderStatus)
    army: ArmyComposition = field(default_factory=ArmyComposition)
    objective: AIObjective = field(default_factory=AIObjective)
    next_action: Optional[ActionDecision] = None
    controller_status: ControllerState = ControllerState.STOPPED
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "town_hall_level": self.town_hall_level,
            "resources": self.resources.to_dict(),
            "builders": self.builders.to_dict(),
            "army": self.army.to_dict(),
            "objective": self.objective.to_dict(),
            "next_action": self.next_action.to_dict() if self.next_action else None,
            "controller_status": self.controller_status.value,
            "timestamp": self.timestamp
        }
