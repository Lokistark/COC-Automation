"""
Main launcher for CoC Autonomous AI Game Controller Dashboard.
Starts the background agent controller and HTTP server.
"""

import os
import sys
import socket
from src.memory import DatabaseMemory
from src.task_planner import TaskPlanner
from src.controller import AgentController
from src.server import ThreadedHTTPServer, make_handler


def find_available_port(start_port: int = 8080, max_attempts: int = 10) -> int:
    """Finds an open port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start_port


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, "data", "coc_memory.db")
    static_dir = os.path.join(base_dir, "src", "static")

    # Ensure Windows console handles UTF-8 safely
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 65)
    print("  [*] CoC Autonomous AI Game Controller - Phase 1 Dashboard")
    print("=" * 65)
    print(f"[*] Initializing SQLite Database Memory at: {db_path}")
    memory = DatabaseMemory(db_path=db_path)

    print("[*] Initializing Task Planner & Decision Engine...")
    planner = TaskPlanner(memory=memory)

    print("[*] Initializing Agent Controller (State Machine & Safety Interlock)...")
    controller = AgentController(memory=memory, planner=planner)

    port = find_available_port(8080)
    server_address = ("127.0.0.1", port)
    handler_class = make_handler(controller, memory, static_dir)
    httpd = ThreadedHTTPServer(server_address, handler_class)

    url = f"http://127.0.0.1:{port}"
    print("-" * 65)
    print(f"[+] DASHBOARD SERVER RUNNING!")
    print(f"[+] Open in your browser: {url}")
    print("-" * 65)
    print("  Controls available directly in the web dashboard:")
    print("  - [Run Loop]: Starts autonomous simulated cycles")
    print("  - [Step Action]: Runs one single decision & execution tick")
    print("  - [Pause / Resume]: Toggles active state")
    print("  - [EMERGENCY STOP]: Instant halt safety interlock")
    print("  - [Reset State]: Re-seeds baseline Town Hall 11 sample data")
    print("-" * 65)
    print("Press Ctrl+C to stop the dashboard server.\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Shutting down server and stopping controller...")
        controller.stop()
        httpd.server_close()
        print("[+] Server stopped cleanly.")


if __name__ == "__main__":
    main()
