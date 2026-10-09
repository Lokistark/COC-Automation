"""
Embedded HTTP Server and REST API for CoC Autonomous AI Game Controller.
Zero external dependencies, uses Python's standard http.server and socketserver.
Includes routes for Vision, Attack Planning, Simulation, and Autonomous Loop controls.
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import json
import os
import sys
import platform
import base64
import urllib.parse
from typing import Dict, Any

from .controller import AgentController
from .memory import DatabaseMemory
from .models import UpgradeItem, Priority, TaskStatus, ControllerState
from .vision.synthetic_generator import create_synthetic_screenshot


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTP server handling concurrent web dashboard requests."""
    daemon_threads = True


def make_handler(controller: AgentController, memory: DatabaseMemory, static_dir: str):
    """Factory creating an HTTP Request Handler with references to controller and memory."""

    class CoCDashboardHandler(BaseHTTPRequestHandler):

        def log_message(self, format, *args):
            # Suppress noisy console logs
            pass

        def _send_json(self, status_code: int, data: Any):
            body = json.dumps(data, indent=2).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, DELETE")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, DELETE")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            query = urllib.parse.parse_qs(parsed.query)

            # API Routes
            if path == "/api/state":
                state = controller.get_state()
                self._send_json(200, state)
                return

            if path == "/api/tasks":
                tasks = [t.to_dict() for t in memory.get_tasks()]
                self._send_json(200, tasks)
                return

            if path == "/api/logs":
                level = query.get("level", [None])[0]
                limit = int(query.get("limit", [50])[0])
                logs = memory.get_logs(limit=limit, level=level)
                self._send_json(200, logs)
                return

            if path == "/api/system":
                info = {
                    "python_version": sys.version,
                    "os": platform.platform(),
                    "gpu": "NVIDIA GeForce RTX 3050 (6 GB VRAM)",
                    "ram": "16 GB RAM",
                    "mode": "Phases 1-6 Integrated Autonomous Sandbox",
                    "status": controller.state.controller_status.value
                }
                self._send_json(200, info)
                return

            # Vision & Attack Planning Routes
            if path == "/api/vision/latest":
                self._send_json(200, {
                    "observation": controller.latest_observation,
                    "has_screenshot": controller.latest_screenshot_path is not None
                })
                return

            if path == "/api/vision/annotated.jpg":
                ann_path = os.path.join("data", "screenshots", "annotated_latest.jpg")
                if os.path.exists(ann_path):
                    with open(ann_path, "rb") as f:
                        img_data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(img_data)))
                    self.end_headers()
                    self.wfile.write(img_data)
                else:
                    self._send_json(404, {"error": "Annotated image not generated yet."})
                return

            if path == "/api/attack/plans":
                base_analysis = controller.attack_planner.analyze_enemy_base(
                    image_path=controller.latest_screenshot_path
                )
                plans = controller.attack_planner.generate_attack_plans(base_analysis)
                self._send_json(200, {
                    "base_analysis": base_analysis,
                    "plans": plans
                })
                return

            # Static File Serving
            if path == "/" or path == "/index.html":
                file_path = os.path.join(static_dir, "index.html")
                content_type = "text/html; charset=utf-8"
            elif path.endswith(".css"):
                file_path = os.path.join(static_dir, os.path.basename(path))
                content_type = "text/css; charset=utf-8"
            elif path.endswith(".js"):
                file_path = os.path.join(static_dir, os.path.basename(path))
                content_type = "application/javascript; charset=utf-8"
            else:
                file_path = os.path.join(static_dir, path.lstrip("/"))
                content_type = "text/plain"

            if os.path.exists(file_path) and os.path.isfile(file_path):
                try:
                    with open(file_path, "rb") as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except Exception as e:
                    self._send_json(500, {"error": str(e)})
            else:
                self._send_json(404, {"error": f"Path not found: {path}"})

        def do_POST(self):
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            content_length = int(self.headers.get("Content-Length", 0))
            post_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                data = json.loads(post_body.decode("utf-8")) if post_body else {}
            except Exception:
                data = {}

            # Execution Controls
            if path == "/api/control":
                action = data.get("action", "").lower()
                if action == "start":
                    controller.start()
                    self._send_json(200, {"status": "started", "state": controller.get_state()})
                elif action == "pause":
                    controller.pause()
                    self._send_json(200, {"status": "paused", "state": controller.get_state()})
                elif action == "resume":
                    controller.resume()
                    self._send_json(200, {"status": "resumed", "state": controller.get_state()})
                elif action == "stop":
                    controller.stop()
                    self._send_json(200, {"status": "stopped", "state": controller.get_state()})
                elif action == "emergency_stop":
                    controller.emergency_stop()
                    self._send_json(200, {"status": "emergency_stopped", "state": controller.get_state()})
                elif action == "step":
                    step_result = controller.step()
                    self._send_json(200, {"status": "step_executed", "result": step_result, "state": controller.get_state()})
                elif action == "reset":
                    controller.reset_state()
                    self._send_json(200, {"status": "reset", "state": controller.get_state()})
                elif action == "approve":
                    approval_res = controller.approve_pending_action()
                    self._send_json(200, {"status": "approved", "result": approval_res, "state": controller.get_state()})
                else:
                    self._send_json(400, {"error": f"Unknown action: {action}"})
                return

            # Vision: Generate Synthetic Screenshot
            if path == "/api/vision/generate":
                mode = data.get("mode", "village")
                file_name = f"sample_{mode}.jpg"
                output_path = os.path.join("data", "screenshots", file_name)
                create_synthetic_screenshot(output_path, mode=mode)
                obs = controller.process_screenshot(output_path)
                self._send_json(200, {
                    "message": f"Synthetic {mode} generated and processed.",
                    "observation": obs
                })
                return

            # Vision: Custom Screenshot Analysis (from path or base64)
            if path == "/api/vision/analyze":
                image_path = data.get("image_path")
                base64_data = data.get("image_base64")

                if base64_data:
                    # Save base64 image to disk
                    output_path = os.path.join("data", "screenshots", "uploaded_custom.jpg")
                    try:
                        header_sep = base64_data.find(",")
                        raw_base64 = base64_data[header_sep + 1:] if header_sep != -1 else base64_data
                        with open(output_path, "wb") as f:
                            f.write(base64.b64decode(raw_base64))
                        image_path = output_path
                    except Exception as e:
                        self._send_json(400, {"error": f"Failed to decode base64: {str(e)}"})
                        return

                if not image_path or not os.path.exists(image_path):
                    self._send_json(400, {"error": "Valid image_path or image_base64 required."})
                    return

                obs = controller.process_screenshot(image_path)
                self._send_json(200, {"observation": obs})
                return

            # Attack Planner: Simulate Battle
            if path == "/api/attack/simulate":
                plan_id = data.get("plan_id", "PLAN-AIR-SMASH")
                base_analysis = controller.attack_planner.analyze_enemy_base(
                    image_path=controller.latest_screenshot_path
                )
                battle_res = controller.attack_planner.simulate_battle_outcome(plan_id, base_analysis)
                self._send_json(200, {"battle_simulation": battle_res})
                return

            # Autonomous Loop Configuration
            if path == "/api/loop/config":
                manual_approval = bool(data.get("manual_approval", False))
                max_iterations = int(data.get("max_iterations", 10))
                delay_seconds = float(data.get("delay_seconds", 3.5))
                controller.set_loop_mode(manual_approval, max_iterations, delay_seconds)
                self._send_json(200, {
                    "status": "config_updated",
                    "manual_approval": manual_approval,
                    "max_iterations": max_iterations,
                    "delay_seconds": delay_seconds
                })
                return

            # Task management
            if path == "/api/tasks":
                try:
                    task = UpgradeItem(
                        id=data.get("id", f"task-{int(os.times()[4]*1000)}"),
                        target_name=data.get("target_name", "Unknown Building"),
                        category=data.get("category", "Defense"),
                        current_level=int(data.get("current_level", 1)),
                        target_level=int(data.get("target_level", 2)),
                        cost_resource=data.get("cost_resource", "Gold"),
                        cost_amount=int(data.get("cost_amount", 1000000)),
                        duration_seconds=int(data.get("duration_seconds", 86400)),
                        priority=Priority(data.get("priority", "MEDIUM")),
                        status=TaskStatus.PENDING
                    )
                    memory.add_task(task)
                    self._send_json(201, {"message": "Task added successfully", "task": task.to_dict()})
                except Exception as e:
                    self._send_json(400, {"error": f"Failed to add task: {str(e)}"})
                return

            if path == "/api/logs/clear":
                memory.clear_logs()
                self._send_json(200, {"message": "Logs cleared."})
                return

            self._send_json(404, {"error": f"Unknown POST endpoint: {path}"})

    return CoCDashboardHandler
