/**
 * Frontend logic for CoC Autonomous AI Game Controller Dashboard
 * Supports Phases 1–6: Vision Perception, Reasoning, Attack Planning,
 * Simulation, and the Autonomous Decision Loop.
 */

let currentFilter = 'ALL';
let isDrawerOpen = false;
let cachedAttackPlans = [];

// Format numbers with commas (e.g., 4,250,000)
function formatNumber(num) {
    if (num === undefined || num === null) return '0';
    return Number(num).toLocaleString();
}

// Convert seconds into human-readable duration
function formatSeconds(secs) {
    if (!secs || secs <= 0) return '0s';
    const d = Math.floor(secs / (3600 * 24));
    const h = Math.floor((secs % (3600 * 24)) / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = Math.floor(secs % 60);
    if (d > 0) return `${d}d ${h}h`;
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
}

// Format timestamp into HH:MM:SS
function formatTime(timestamp) {
    const d = new Date(timestamp * 1000);
    return d.toTimeString().split(' ')[0];
}

// Send execution control command
async function sendControl(action) {
    try {
        const res = await fetch('/api/control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action })
        });
        await res.json();
        await refreshDashboard();
    } catch (err) {
        console.error('Failed to send control command:', err);
    }
}

// Approve pending action in Manual Approval Mode
async function approveAction() {
    try {
        const res = await fetch('/api/control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'approve' })
        });
        await res.json();
        await refreshDashboard();
    } catch (err) {
        console.error('Failed to approve action:', err);
    }
}

// Update Autonomous Loop Configuration
async function updateLoopConfig() {
    const mode = document.getElementById('loopModeSelect').value;
    const maxIter = parseInt(document.getElementById('loopMaxIter').value, 10);
    const delay = parseFloat(document.getElementById('loopDelay').value);

    try {
        await fetch('/api/loop/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                manual_approval: mode === 'manual',
                max_iterations: maxIter,
                delay_seconds: delay
            })
        });
        await refreshDashboard();
    } catch (err) {
        console.error('Failed to update loop config:', err);
    }
}

// Generate Synthetic Screenshot (village or enemy_base)
async function generateSynthetic(mode) {
    try {
        const res = await fetch('/api/vision/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode })
        });
        const data = await res.json();
        updateVisionDisplay(data.observation);
        await refreshDashboard();
        await loadAttackPlans();
    } catch (err) {
        console.error('Failed to generate synthetic screenshot:', err);
    }
}

// Upload Custom Screenshot from disk
async function uploadScreenshot(event) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = async (e) => {
        try {
            const res = await fetch('/api/vision/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ image_base64: e.target.result })
            });
            const data = await res.json();
            updateVisionDisplay(data.observation);
            await refreshDashboard();
            await loadAttackPlans();
        } catch (err) {
            console.error('Failed to upload screenshot:', err);
        }
    };
    reader.readAsDataURL(file);
}

// Update Vision display panel
function updateVisionDisplay(obs) {
    if (!obs) return;

    const imgEl = document.getElementById('annotatedImage');
    // Force cache bust to refresh preview
    imgEl.src = `/api/vision/annotated.jpg?t=${Date.now()}`;

    if (obs.resolution) {
        document.getElementById('visionResolution').innerText = `${obs.resolution.width} x ${obs.resolution.height}`;
    }

    if (obs.overall_confidence !== undefined) {
        document.getElementById('visionConfidence').innerText = `${Math.round(obs.overall_confidence * 100)}%`;
    }

    document.getElementById('visionViewType').innerText = obs.is_enemy_base ? 'Enemy Base (War/Raid)' : 'Home Village';

    // Uncertainties
    const uncBox = document.getElementById('uncertaintyBox');
    const uncList = document.getElementById('uncertaintyList');
    if (obs.uncertainties && obs.uncertainties.length > 0) {
        uncBox.style.display = 'block';
        uncList.innerHTML = obs.uncertainties.map(u => `<li>${u}</li>`).join('');
    } else {
        uncBox.style.display = 'none';
    }
}

// Load Attack Plans
async function loadAttackPlans() {
    try {
        const res = await fetch('/api/attack/plans');
        if (!res.ok) return;
        const data = await res.json();
        cachedAttackPlans = data.plans || [];

        const threatBadge = document.getElementById('attackThreatBadge');
        if (data.base_analysis && data.base_analysis.threat_level) {
            threatBadge.innerText = `Threat: ${data.base_analysis.threat_level}`;
        }

        renderSelectedPlan();
    } catch (err) {
        console.error('Failed to load attack plans:', err);
    }
}

// Render selected attack plan details
function renderSelectedPlan() {
    const planId = document.getElementById('attackPlanSelect').value;
    const plan = cachedAttackPlans.find(p => p.plan_id === planId) || cachedAttackPlans[0];
    if (!plan) return;

    const container = document.getElementById('planDetailsBox');
    container.innerHTML = `
        <div class="plan-meta-row">
            <span style="color: #fff;">${plan.name}</span>
            <span class="badge badge-accent">Confidence: ${Math.round(plan.confidence * 100)}%</span>
        </div>
        <div style="color: var(--text-secondary); font-size: 11px;">
            <strong>Approach Sector:</strong> ${plan.approach_sector} | <strong>Target:</strong> ${plan.target_destruction}
        </div>
        <div style="color: #cbd5e1; font-size: 12px; margin-top: 2px;">
            ${plan.tactical_rationale}
        </div>
        <div class="timeline-strip">
            ${plan.deployment_timeline.map(step => `
                <div class="deployment-step">
                    <div class="step-phase">${step.phase}: ${step.action}</div>
                    <div class="step-instruction">${step.instructions}</div>
                </div>
            `).join('')}
        </div>
    `;
}

// Simulate hypothetical battle outcome
async function simulateCurrentBattle() {
    const planId = document.getElementById('attackPlanSelect').value;
    try {
        const res = await fetch('/api/attack/simulate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ plan_id: planId })
        });
        const data = await res.json();
        const outcome = data.battle_simulation;

        const box = document.getElementById('battleOutcomeBox');
        box.style.display = 'block';

        const starStars = '★'.repeat(outcome.stars) + '☆'.repeat(3 - outcome.stars);

        box.innerHTML = `
            <div class="outcome-header">
                <div>
                    <h4 style="color: #fff; font-size: 14px;">Battle Simulation Outcome</h4>
                    <span style="color: var(--text-muted); font-size: 11px;">${outcome.plan_name}</span>
                </div>
                <div class="stars-display">${starStars} (${outcome.destruction_pct}% Destruction)</div>
            </div>
            <p style="color: #4ade80; font-weight: 500; font-size: 12px; margin-bottom: 8px;">
                ${outcome.summary}
            </p>
            <div style="font-family: var(--font-mono); font-size: 11px; display: flex; gap: 14px; color: var(--text-secondary);">
                <span>🟡 +${formatNumber(outcome.loot_collected.gold)} Gold</span>
                <span>🟣 +${formatNumber(outcome.loot_collected.elixir)} Elixir</span>
                <span>⚫ +${formatNumber(outcome.loot_collected.dark_elixir)} DE</span>
                <span>🏆 +${outcome.trophies_gained} Trophies</span>
            </div>
        `;

        await refreshDashboard();
    } catch (err) {
        console.error('Failed to simulate battle:', err);
    }
}

// Fetch and update overall game state & telemetry
async function updateState() {
    try {
        const res = await fetch('/api/state');
        if (!res.ok) throw new Error('Network error');
        const state = await res.json();

        // 1. Controller Status & Navigation
        const stateText = document.getElementById('controllerStateText');
        const pill = document.getElementById('controllerPill');
        stateText.innerText = state.controller_status;

        pill.className = 'controller-pill';
        if (state.controller_status === 'RUNNING') {
            pill.style.borderColor = '#22c55e';
            stateText.style.color = '#22c55e';
        } else if (state.controller_status === 'EMERGENCY_STOPPED') {
            pill.style.borderColor = '#ef4444';
            stateText.style.color = '#ef4444';
        } else if (state.controller_status === 'PAUSED') {
            pill.style.borderColor = '#f59e0b';
            stateText.style.color = '#f59e0b';
        } else {
            pill.style.borderColor = 'var(--border-color)';
            stateText.style.color = 'var(--accent-cyan)';
        }

        // 2. Loop Telemetry
        if (state.loop_telemetry) {
            const tel = state.loop_telemetry;
            document.getElementById('loopProgressText').innerText = `Iteration ${tel.iteration} / ${tel.max_iterations}`;
            const failBadge = document.getElementById('failureCounter');
            failBadge.innerText = `${tel.consecutive_failures} Failures`;

            // Manual Approval Banner
            const approvalBanner = document.getElementById('manualApprovalBanner');
            if (tel.pending_approval) {
                approvalBanner.style.display = 'flex';
                document.getElementById('approvalActionText').innerText = `Proposed Action: ${tel.pending_approval.target} (${tel.pending_approval.rationale})`;
            } else {
                approvalBanner.style.display = 'none';
            }
        }

        // 3. AI Decision Engine
        if (state.objective) {
            document.getElementById('objectiveTitle').innerText = state.objective.title;
            document.getElementById('objectiveDesc').innerText = state.objective.description;
        }

        if (state.next_action) {
            document.getElementById('actionTypeTag').innerText = state.next_action.action_type;
            document.getElementById('actionTargetDisplay').innerText = state.next_action.target;
            document.getElementById('actionRationale').innerText = state.next_action.rationale;
            document.getElementById('confidenceBadge').innerText = `Confidence: ${Math.round(state.next_action.confidence * 100)}%`;

            const prereqEl = document.getElementById('prereqStatus');
            if (state.next_action.prerequisites_met) {
                prereqEl.className = 'prereq-status';
                prereqEl.innerHTML = '<span class="check-icon">✓</span> Prerequisites Satisfied (Builder & Resources Verified)';
            } else {
                prereqEl.className = 'prereq-status failed';
                prereqEl.innerHTML = '<span class="check-icon">✕</span> Prerequisites Pending (Waiting on constraints)';
            }
        }

        // 4. Resources
        const resData = state.resources;
        if (resData) {
            document.getElementById('goldVal').innerText = `${formatNumber(resData.gold)} / ${formatNumber(resData.max_gold)}`;
            document.getElementById('goldBar').style.width = `${Math.min(100, Math.round((resData.gold / resData.max_gold) * 100))}%`;

            document.getElementById('elixirVal').innerText = `${formatNumber(resData.elixir)} / ${formatNumber(resData.max_elixir)}`;
            document.getElementById('elixirBar').style.width = `${Math.min(100, Math.round((resData.elixir / resData.max_elixir) * 100))}%`;

            document.getElementById('darkElixirVal').innerText = `${formatNumber(resData.dark_elixir)} / ${formatNumber(resData.max_dark_elixir)}`;
            document.getElementById('darkElixirBar').style.width = `${Math.min(100, Math.round((resData.dark_elixir / resData.max_dark_elixir) * 100))}%`;

            document.getElementById('gemsVal').innerText = formatNumber(resData.gems);
        }

        // 5. Builders
        const b = state.builders;
        if (b) {
            document.getElementById('builderPill').innerText = `${b.free_builders} / ${b.total_builders} Free`;
            const busyList = document.getElementById('busyBuildersList');
            if (b.busy_builders && b.busy_builders.length > 0) {
                busyList.innerHTML = b.busy_builders.map(job => `
                    <div class="builder-job-row">
                        <div>
                            <span class="builder-target">${job.target_name}</span>
                            <span style="color: var(--text-muted); font-size: 11px;"> (Lvl ${job.target_level})</span>
                        </div>
                        <div class="builder-timer">⏳ ${formatSeconds(job.seconds_remaining)}</div>
                    </div>
                `).join('');
            } else {
                busyList.innerHTML = `<div style="color: var(--text-muted); font-size: 12px; padding: 6px 0;">All builders idle and ready.</div>`;
            }
        }

        // 6. Vision Observation Cache
        if (state.latest_observation) {
            updateVisionDisplay(state.latest_observation);
        }

        document.getElementById('connStatus').innerText = 'ONLINE';
    } catch (err) {
        document.getElementById('connStatus').innerText = 'OFFLINE';
        console.error('State sync error:', err);
    }
}

// Fetch and render planned tasks
async function updateTasks() {
    try {
        const res = await fetch('/api/tasks');
        if (!res.ok) return;
        const tasks = await res.json();

        const tbody = document.getElementById('tasksTableBody');
        if (tasks.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 16px;">No queued tasks. Click "+ Add Upgrade" to schedule one.</td></tr>`;
            return;
        }

        tbody.innerHTML = tasks.map(t => {
            const priorityClass = t.priority === 'HIGH' ? 'p-high' : (t.priority === 'MEDIUM' ? 'p-med' : 'p-low');
            return `
                <tr>
                    <td><span class="priority-badge ${priorityClass}">${t.priority}</span></td>
                    <td><strong>${t.target_name}</strong> <span style="color: var(--text-muted); font-size: 11px;">(Lvl ${t.current_level} → ${t.target_level})</span></td>
                    <td><span style="color: var(--text-secondary); font-size: 11px;">${t.category}</span></td>
                    <td><span style="font-family: var(--font-mono); font-size: 11px;">${formatNumber(t.cost_amount)} ${t.cost_resource}</span></td>
                    <td><span style="font-size: 11px; font-weight: 600; color: ${t.status === 'IN_PROGRESS' ? '#38bdf8' : (t.status === 'COMPLETED' ? '#4ade80' : '#94a3b8')}">${t.status}</span></td>
                </tr>
            `;
        }).join('');
    } catch (err) {
        console.error('Failed to load tasks:', err);
    }
}

// Fetch and render activity logs
async function updateLogs() {
    try {
        const url = currentFilter === 'ALL' ? '/api/logs?limit=40' : `/api/logs?level=${currentFilter}&limit=40`;
        const res = await fetch(url);
        if (!res.ok) return;
        const logs = await res.json();

        const stream = document.getElementById('logStream');
        if (logs.length === 0) {
            stream.innerHTML = `<div style="color: var(--text-muted); padding: 10px;">No activity logs recorded.</div>`;
            return;
        }

        stream.innerHTML = logs.map(l => `
            <div class="log-line">
                <span class="log-time">${formatTime(l.timestamp)}</span>
                <span class="log-tag ${l.level}">[${l.level}]</span>
                <span class="log-msg"><strong style="color: var(--text-muted); font-size: 10px;">[${l.category}]</strong> ${l.message}</span>
            </div>
        `).join('');
    } catch (err) {
        console.error('Failed to load logs:', err);
    }
}

// Filter logs
function filterLogs(level, buttonEl) {
    currentFilter = level;
    document.querySelectorAll('.filter-pill').forEach(btn => btn.classList.remove('active'));
    if (buttonEl) buttonEl.classList.add('active');
    updateLogs();
}

// Clear logs
async function clearLogs() {
    try {
        await fetch('/api/logs/clear', { method: 'POST' });
        await updateLogs();
    } catch (err) {
        console.error('Failed to clear logs:', err);
    }
}

// Toggle Task Drawer
function toggleTaskModal() {
    const drawer = document.getElementById('addTaskForm');
    isDrawerOpen = !isDrawerOpen;
    drawer.style.display = isDrawerOpen ? 'block' : 'none';
}

// Submit custom task
async function submitCustomTask() {
    const target_name = document.getElementById('taskTargetName').value.trim();
    if (!target_name) {
        alert('Please specify a target building name.');
        return;
    }

    const payload = {
        target_name: target_name,
        category: document.getElementById('taskCategory').value,
        current_level: parseInt(document.getElementById('taskCurrentLevel').value, 10),
        target_level: parseInt(document.getElementById('taskTargetLevel').value, 10),
        cost_resource: document.getElementById('taskCostResource').value,
        cost_amount: parseInt(document.getElementById('taskCostAmount').value, 10),
        priority: document.getElementById('taskPriority').value,
        duration_seconds: 86400
    };

    try {
        const res = await fetch('/api/tasks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            document.getElementById('taskTargetName').value = '';
            toggleTaskModal();
            await refreshDashboard();
        }
    } catch (err) {
        console.error('Failed to add task:', err);
    }
}

// Refresh all dashboard components
async function refreshDashboard() {
    await Promise.all([updateState(), updateTasks(), updateLogs()]);
}

// Initial Boot
window.addEventListener('DOMContentLoaded', async () => {
    await refreshDashboard();
    await loadAttackPlans();
    // Poll every 1.5 seconds for real-time responsiveness
    setInterval(refreshDashboard, 1500);
});
