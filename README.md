# 🛡️ CoC Autonomous AI Game Controller

A research prototype for an autonomous AI agent that observes Clash of Clans game state via computer vision, estimates structured state, makes prioritized strategic decisions, plans multi-phase attacks, executes simulated actions with state verification, and runs a safe, observable 9-stage autonomous loop.

---

## 🚀 System & Hardware Profile
- **Operating System**: Windows 10/11
- **Dedicated GPU**: NVIDIA GeForce RTX 3050 (6 GB Dedicated VRAM)
- **System Memory**: 16 GB RAM
- **Python**: 3.14.0 (64-bit)
- **Vision Engine**: OpenCV 5.0, Pillow 12.3, NumPy 2.5
- **Storage Backend**: Local SQLite (`data/coc_memory.db`)

---

## 🏗️ Architecture & Module Breakdown

```
coc-ai-agent/
│
├── requirements.txt                # OpenCV, Pillow, and NumPy dependencies
├── README.md                       # Comprehensive guide & documentation
├── run_dashboard.py                # Main application launcher
│
├── src/
│   ├── models.py                   # Strongly typed dataclasses for VillageState, Resources, etc.
│   ├── memory.py                   # Persistent SQLite storage (logs, tasks, snapshots)
│   ├── task_planner.py             # Strategic upgrade queuing & baseline seeding
│   ├── decision_engine.py          # Phase 3: Facts vs. assumptions separation, priority ranking
│   ├── attack_planner.py           # Phase 4: Enemy base analysis, multi-strategy planning & battle sim
│   ├── controller.py               # Master agent controller & interlock state machine
│   ├── autonomous_loop.py          # Phase 6: 9-stage autonomous decision loop runner
│   │
│   ├── vision/                     # Phase 2: Screen Vision & Perception
│   │   ├── image_processor.py      # OpenCV color segmentation, ROI extraction, defense detection
│   │   └── synthetic_generator.py  # Realistic synthetic village and enemy base generator
│   │
│   ├── simulator/                  # Phase 5: Action Simulator
│   │   └── action_interface.py     # Abstract ActionInterface & SimulatedActionExecutor with verification
│   │
│   ├── static/                     # Web Dashboard UI
│   │   ├── index.html              # Tactical command center frontend
│   │   ├── style.css               # Modern dark-mode gaming UI
│   │   └── app.js                  # Real-time state polling & controls
│   │
│   └── server.py                   # Multi-threaded HTTP server & JSON REST API
│
├── tests/
│   ├── test_phase1.py              # Phase 1 unit and integration tests
│   └── test_all_phases.py          # Phases 1–6 complete automated test suite (28 tests)
│
└── data/
    ├── coc_memory.db               # SQLite persistent database
    └── screenshots/                # Generated & uploaded screenshot cache
```

---

## 🔄 The 9-Stage Autonomous Cycle (Phase 6)

When the autonomous loop runs, each iteration follows a strict 9-stage pipeline:

```
[1. OBSERVE]            Load and preprocess screenshot via OpenCV
      ↓
[2. INTERPRET]          Extract HUD regions and separate facts from assumptions
      ↓
[3. CHECK CONFIDENCE]   Verify overall confidence >= 60% (trips safety pause if low)
      ↓
[4. EVALUATE OPTIONS]   Evaluate pending upgrades, resource overflow, builder uptime
      ↓
[5. SELECT ACTION]      Choose highest-ranked actionable candidate (checks failure cooldown)
      ↓
[6. PREREQUISITES]      Verify builder availability and exact resource costs
      ↓
[7. SIMULATE ACTION]    Execute state mutation in sandbox (or pause for Manual Approval)
      ↓
[8. VERIFY RESULT]      Validate before/after state diff (resources deducted, builder assigned)
      ↓
[9. LOG & RECORD]       Write traceable audit log entry and state snapshot to SQLite
```

---

## ⚡ Quick Start Guide (Beginner Friendly)

### 1. Run the Complete Test Suite
```powershell
python -m unittest discover -s tests -v
```
All **28 tests** across all phases run in ~3 seconds and pass with `OK`.

### 2. Launch the Application
```powershell
python run_dashboard.py
```
Open your browser and navigate to:
👉 **[http://127.0.0.1:8080](http://127.0.0.1:8080)**

---

## 🕹️ Dashboard Features

1. **Vision Perception Viewer**:
   - Inspect the current screenshot with bounding box overlays for detected HUD elements, Town Hall, and defenses.
   - Click **`🎲 Synth Village`** or **`🎯 Synth Enemy`** to generate realistic gameplay captures instantly.
   - Click **`📁 Upload Screenshot`** to load any real Clash of Clans screenshot from your computer.

2. **Autonomous Execution Controls**:
   - **`▶ Run Autonomous Loop`**: Starts continuous loop execution.
   - **`⏭ Single Step Tick`**: Executes a single 9-stage cycle.
   - **`⏸ Pause / ⏯ Resume / ⏹ Stop`**: Control loop thread execution.
   - **`🚨 EMERGENCY STOP`**: Instant safety halt engaging an interlock.
   - **Mode Switcher**: Toggle between **Autonomous Sandbox Mode** and **Manual Approval Mode**.
   - **Max Iterations & Delay Inputs**: Configure how many steps to run before auto-stopping (e.g. 10 iterations) and delay between steps (e.g. 3.5s).

3. **Attack Planner & Battle Simulator**:
   - **Strategy Selector**: Choose between *Plan A: E-Dragon Air Smash*, *Plan B: Queen Walk + Hybrid*, or *Plan C: High-Loot Resource Sniping*.
   - **Phased Deployment Timeline**: Step-by-step instructions (e.g. 0:00 - 0:15 Funneling, 0:15 - 0:30 Tanking, 0:30 - 1:15 Core Smash).
   - **`⚡ Run Battle Simulator`**: Simulates the attack, predicting destruction %, star rating, loot looted, and trophies earned.

4. **Strategic Task Planner & Activity Stream**:
   - View pending upgrades ranked by priority.
   - Click **`+ Add Upgrade`** to queue custom building upgrades.
   - Live filterable event stream (`ALL`, `ACTION`, `INFO`, `WARNING`).

---

## ⚠️ Boundaries & Limitations

- **Simulation & Sandbox Environment Only**: All actions, upgrades, and battles are executed inside the local simulator. Live game control and botting are not implemented and are strictly avoided to ensure compliance with terms of service.
- **Vision Model**: Uses color segmentation, morphological filtering, and contour heuristics. Future phases can add local YOLOv8 / PyTorch vision models utilizing the dedicated RTX 3050 GPU.
