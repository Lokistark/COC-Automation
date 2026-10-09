"""
Comprehensive Unit and Integration Tests for Phases 1 through 6.
Tests:
- Vision Perception & Synthetic Screenshot Generation
- Strategic Decision Engine & Uncertainty Fallbacks
- Attack Planner & Battle Outcome Simulation
- Action Simulator Interface & Transition Verification
- Autonomous Loop Runner with Max-Iteration & Safety Interlocks
"""

import unittest
import os
import tempfile
import time
from unittest.mock import MagicMock

from src.models import (
    VillageState, Resources, BuilderStatus, UpgradeItem, Priority, TaskStatus, ControllerState
)
from src.memory import DatabaseMemory
from src.task_planner import TaskPlanner
from src.vision.synthetic_generator import create_synthetic_screenshot
from src.vision.image_processor import ScreenVisionProcessor
from src.decision_engine import StrategicDecisionEngine
from src.attack_planner import StrategicAttackPlanner
from src.simulator.action_interface import SimulatedActionExecutor, SimulationOutcome
from src.autonomous_loop import AutonomousLoopRunner


class TestVisionPerception(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.village_img = os.path.join(self.temp_dir.name, "test_village.jpg")
        self.enemy_img = os.path.join(self.temp_dir.name, "test_enemy.jpg")
        self.processor = ScreenVisionProcessor(debug_output_dir=self.temp_dir.name)

        create_synthetic_screenshot(self.village_img, width=1280, height=720, mode="village")
        create_synthetic_screenshot(self.enemy_img, width=1280, height=720, mode="enemy_base")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_synthetic_image_generation(self):
        self.assertTrue(os.path.exists(self.village_img))
        self.assertTrue(os.path.exists(self.enemy_img))

    def test_village_screenshot_processing(self):
        obs = self.processor.process_screenshot(self.village_img)
        self.assertTrue(obs["success"])
        self.assertEqual(obs["resolution"]["width"], 1280)
        self.assertEqual(obs["resolution"]["height"], 720)
        self.assertFalse(obs["is_enemy_base"])
        self.assertGreater(obs["overall_confidence"], 0.70)
        self.assertGreater(len(obs["candidate_buildings"]), 0)

    def test_enemy_base_detection(self):
        obs = self.processor.process_screenshot(self.enemy_img)
        self.assertTrue(obs["success"])
        self.assertTrue(obs["is_enemy_base"])

    def test_invalid_image_path_handling(self):
        obs = self.processor.process_screenshot("non_existent_file.jpg")
        self.assertFalse(obs["success"])
        self.assertEqual(obs["confidence"], 0.0)
        self.assertIn("could not be read", obs["uncertainties"][0])


class TestDecisionEngine(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_decisions.db")
        self.memory = DatabaseMemory(db_path=self.db_path)
        self.planner = TaskPlanner(memory=self.memory)
        self.engine = StrategicDecisionEngine(memory=self.memory)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_separate_facts_and_assumptions(self):
        state = self.planner.create_initial_state()
        result = self.engine.separate_facts_and_assumptions(state)
        self.assertIn("facts", result)
        self.assertIn("assumptions", result)
        self.assertEqual(result["facts"]["town_hall_level"], 11)

    def test_low_confidence_uncertainty_fallback(self):
        state = self.planner.create_initial_state()
        low_conf_obs = {
            "overall_confidence": 0.45,
            "uncertainties": ["Severe motion blur in HUD region."]
        }
        candidates = self.engine.rank_candidate_actions(state, low_conf_obs)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["action_type"], "RE_OBSERVE")
        self.assertTrue(candidates[0]["is_assumption"])

    def test_action_ranking_and_prerequisites(self):
        state = self.planner.create_initial_state()
        candidates = self.engine.rank_candidate_actions(state)
        self.assertGreater(len(candidates), 0)
        top_action = candidates[0]
        self.assertIn("score", top_action)
        self.assertIn("rationale", top_action)
        self.assertEqual(top_action["rank"], 1)


class TestAttackPlanner(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_attack.db")
        self.memory = DatabaseMemory(db_path=self.db_path)
        self.planner = StrategicAttackPlanner(memory=self.memory)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_manual_base_analysis(self):
        analysis = self.planner.analyze_enemy_base(manual_params={"th_level": 11, "inferno_count": 2})
        self.assertEqual(analysis["town_hall_level"], 11)
        self.assertEqual(analysis["threat_level"], "HIGH")

    def test_attack_plans_generation(self):
        analysis = self.planner.analyze_enemy_base(manual_params={"th_level": 11})
        plans = self.planner.generate_attack_plans(analysis)
        self.assertEqual(len(plans), 3)
        self.assertEqual(plans[0]["plan_id"], "PLAN-AIR-SMASH")
        self.assertIn("deployment_timeline", plans[0])
        self.assertGreater(len(plans[0]["deployment_timeline"]), 3)

    def test_battle_outcome_simulation(self):
        analysis = self.planner.analyze_enemy_base(manual_params={"th_level": 11})
        outcome = self.planner.simulate_battle_outcome("PLAN-AIR-SMASH", analysis)
        self.assertEqual(outcome["stars"], 3)
        self.assertGreater(outcome["destruction_pct"], 80)
        self.assertIn("gold", outcome["loot_collected"])
        self.assertTrue("HYPOTHETICAL RESULT" in outcome["simulation_note"])


class TestSimulatedActionExecutor(unittest.TestCase):

    def setUp(self):
        self.executor = SimulatedActionExecutor()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_sim.db")
        self.memory = DatabaseMemory(db_path=self.db_path)
        self.planner = TaskPlanner(memory=self.memory)
        self.state = self.planner.create_initial_state()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_simulated_upgrade_success_and_verification(self):
        initial_gold = self.state.resources.gold
        initial_free_builders = self.state.builders.free_builders

        action = {
            "action_type": "UPGRADE_BUILDING",
            "target": "Cannon #1",
            "cost_resource": "Gold",
            "cost_amount": 1000000
        }
        outcome = self.executor.execute(action, self.state)
        self.assertTrue(outcome.success)
        self.assertTrue(outcome.verified)
        self.assertEqual(self.state.resources.gold, initial_gold - 1000000)
        self.assertEqual(self.state.builders.free_builders, initial_free_builders - 1)
        self.assertTrue(outcome.is_simulated)

    def test_simulated_upgrade_insufficient_resources_failure(self):
        action = {
            "action_type": "UPGRADE_BUILDING",
            "target": "Eagle Artillery",
            "cost_resource": "Gold",
            "cost_amount": 50000000  # Way above storage max
        }
        outcome = self.executor.execute(action, self.state)
        self.assertFalse(outcome.success)
        self.assertIn("Insufficient Gold", outcome.message)

    def test_simulated_army_training(self):
        self.state.army.housing_used = 180
        action = {"action_type": "TRAIN_ARMY", "target": "Army Camps"}
        outcome = self.executor.execute(action, self.state)
        self.assertTrue(outcome.success)
        self.assertTrue(outcome.verified)
        self.assertEqual(self.state.army.housing_used, self.state.army.housing_max)


class TestAutonomousLoopRunner(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_loop.db")
        self.memory = DatabaseMemory(db_path=self.db_path)
        self.planner = TaskPlanner(memory=self.memory)
        self.state = self.planner.create_initial_state()
        self.decision_engine = StrategicDecisionEngine(memory=self.memory)
        self.simulator = SimulatedActionExecutor()
        self.loop = AutonomousLoopRunner(
            memory=self.memory,
            decision_engine=self.decision_engine,
            simulator=self.simulator
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_run_cycle_step_autonomous_mode(self):
        self.loop.manual_approval_mode = False
        res = self.loop.run_cycle_step(self.state)
        self.assertTrue(res["success"])
        self.assertEqual(self.loop.current_iteration, 1)

    def test_run_cycle_step_manual_approval_mode(self):
        self.loop.manual_approval_mode = True
        res = self.loop.run_cycle_step(self.state)
        self.assertTrue(res["success"])
        self.assertEqual(res["stage"], "AWAITING_APPROVAL")
        self.assertIsNotNone(self.loop.pending_approval_action)

    def test_action_blacklist_cooldown(self):
        target = "Failed Target X"
        self.assertFalse(self.loop.is_action_blacklisted(target))
        self.loop.blacklist_failed_action(target)
        self.assertTrue(self.loop.is_action_blacklisted(target))


if __name__ == "__main__":
    unittest.main()
