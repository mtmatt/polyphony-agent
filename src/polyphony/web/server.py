"""
FastAPI-based Web Dashboard for Polyphony Agent.

Provides real-time run monitoring, historical run comparison,
and visual task dependency graphs.
"""

import asyncio
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from ..checkpoint import RunCheckpoint
from ..run_summary import RunSummary

# Get checkpoint directory from environment or default
CHECKPOINT_DIR = Path(os.environ.get("POLYPHONY_CHECKPOINT_DIR", "./.polyphony/checkpoints"))
RUN_SUMMARY_DIR = Path(os.environ.get("POLYPHONY_RUN_DIR", "./logs"))

app = FastAPI(
    title="Polyphony Agent Dashboard",
    description="Real-time run monitoring and task visualization",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket connection manager for real-time updates
class WebSocketManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, websocket: WebSocket, run_id: str):
        await websocket.accept()
        self.active_connections[run_id].append(websocket)

    def disconnect(self, websocket: WebSocket, run_id: str):
        if websocket in self.active_connections[run_id]:
            self.active_connections[run_id].remove(websocket)
            if not self.active_connections[run_id]:
                del self.active_connections[run_id]

    async def broadcast(self, run_id: str, message: dict):
        if run_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[run_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    disconnected.append(connection)
            for conn in disconnected:
                self.active_connections[run_id].remove(conn)

manager = WebSocketManager()

@app.get("/")
async def get_ui() -> HTMLResponse:
    """Serve the main dashboard HTML."""
    html_content = Path(__file__).parent.joinpath("static", "index.html").read_text()
    return HTMLResponse(content=html_content)


@app.get("/api/runs")
async def list_runs(
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = Query(None, description="Filter by status"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date"),
) -> JSONResponse:
    """List all available runs with optional filtering."""
    runs = []

    # Load from checkpoint directory
    if CHECKPOINT_DIR.exists():
        for checkpoint_file in sorted(CHECKPOINT_DIR.glob("checkpoint-*.json"), reverse=True):
            try:
                data = json.loads(checkpoint_file.read_text())
                tasks = _flatten_tasks(data)
                completed = [t for t in tasks if t.get("completed")]
                all_task_ids = {t.get("id", t.get("task_id")) for t in tasks}
                result_ids = {r.get("task_id") for r in data.get("results", [])}
                status = "Completed" if (tasks and all_task_ids <= result_ids) else "In Progress"
                model = next(
                    (r.get("agent_model", "") for r in data.get("results", []) if r.get("agent_model")),
                    data.get("model", "Unknown")
                )
                run_info = {
                    "id": data.get("run_id", checkpoint_file.stem.removeprefix("checkpoint-")),
                    "timestamp": data.get("start_time", data.get("last_updated", "")),
                    "status": data.get("status", status),
                    "goal": (data.get("goal", "Unknown goal")[:100] + "...") if len(data.get("goal", "")) > 100 else data.get("goal", "Unknown goal"),
                    "completed_tasks": len(completed),
                    "total_tasks": len(tasks),
                    "model": model,
                    "progress_percentage": len(completed) / len(tasks) * 100 if tasks else 0,
                }

                # Apply filters
                if status and run_info["status"].lower() != status.lower():
                    continue
                if start_date and datetime.fromisoformat(run_info["timestamp"]) < start_date:
                    continue
                if end_date and datetime.fromisoformat(run_info["timestamp"]) > end_date:
                    continue

                runs.append(run_info)
            except Exception:
                continue

    # Also load from run summaries (logs/ directory)
    if RUN_SUMMARY_DIR.exists():
        for summary_file in sorted(RUN_SUMMARY_DIR.glob("*.json"), reverse=True)[:limit - len(runs)]:
            try:
                data = json.loads(summary_file.read_text())
                # Use filename stem as ID since log files have run_id=None
                run_id = data.get("run_id") or summary_file.stem
                if not any(r["id"] == run_id for r in runs):
                    tasks = _flatten_tasks(data)
                    completed = [t for t in tasks if t.get("completed") or t.get("success")]
                    runs.append({
                        "id": run_id,
                        "timestamp": data.get("start_time", data.get("timestamp", "")),
                        "status": data.get("status", "Completed"),
                        "goal": (data.get("goal", "Unknown goal")[:100] + "...") if len(data.get("goal", "")) > 100 else data.get("goal", "Unknown goal"),
                        "completed_tasks": len(completed),
                        "total_tasks": len(tasks),
                        "model": data.get("model", "Unknown"),
                        "progress_percentage": 100.0 if data.get("status") == "success" else (len(completed) / len(tasks) * 100 if tasks else 0),
                    })
            except Exception:
                continue

    return JSONResponse(content={"runs": runs[:limit], "total": len(runs)})


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> JSONResponse:
    """Get detailed information about a specific run."""
    # Try checkpoint file first (checkpoint-{run_id}.json)
    checkpoint_path = CHECKPOINT_DIR / f"checkpoint-{run_id}.json"
    # Fallback: exact match in summary dir (e.g. filename-as-id from logs/)
    summary_exact = RUN_SUMMARY_DIR / f"{run_id}.json"

    run_data = None

    if checkpoint_path.exists():
        run_data = json.loads(checkpoint_path.read_text())
    elif summary_exact.exists():
        run_data = json.loads(summary_exact.read_text())
    else:
        # Try globbing logs/ for filename match (run_id may be a full filename stem)
        if RUN_SUMMARY_DIR.exists():
            matches = list(RUN_SUMMARY_DIR.glob(f"{run_id}.json"))
            if matches:
                run_data = json.loads(matches[0].read_text())

    if run_data is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    # Build a unified flat task list regardless of data format
    tasks = _flatten_tasks(run_data)
    dependency_graph = build_dependency_graph(tasks)

    return JSONResponse(content={
        **run_data,
        "tasks": tasks,
        "dependency_graph": dependency_graph,
        "timeline": build_timeline(tasks),
        "metrics": calculate_metrics(run_data, tasks)
    })


@app.get("/api/runs/{run_id}/compare/{other_run_id}")
async def compare_runs(run_id: str, other_run_id: str) -> JSONResponse:
    """Compare two runs and show differences."""
    run1_data = await get_run_data(run_id)
    run2_data = await get_run_data(other_run_id)

    if not run1_data or not run2_data:
        raise HTTPException(status_code=404, detail="One or both runs not found")

    comparison = {
        "run1": {"id": run_id, "data": run1_data},
        "run2": {"id": other_run_id, "data": run2_data},
        "differences": calculate_differences(run1_data, run2_data),
        "metrics_comparison": compare_metrics(run1_data, run2_data)
    }

    return JSONResponse(content=comparison)


@app.websocket("/api/runs/{run_id}/stream")
async def websocket_endpoint(websocket: WebSocket, run_id: str):
    """WebSocket endpoint for real-time run updates."""
    await manager.connect(websocket, run_id)
    try:
        while True:
            # Send current run status
            try:
                run_data = await get_run_data(run_id)
                await websocket.send_json({
                    "type": "status_update",
                    "data": run_data
                })
            except Exception:
                pass

            # Wait for next update (check every 2 seconds)
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        manager.disconnect(websocket, run_id)


@app.get("/api/stats")
async def get_stats() -> JSONResponse:
    """Get overall project statistics."""
    stats = {
        "total_runs": 0,
        "successful_runs": 0,
        "failed_runs": 0,
        "in_progress": 0,
        "total_tasks": 0,
        "average_duration": 0,
        "models_used": defaultdict(int),
        "goals_by_day": defaultdict(int),
        "success_rate": 0.0
    }

    runs = await list_runs(limit=10000)
    runs_data = json.loads(runs.body)["runs"]

    stats["total_runs"] = len(runs_data)

    total_duration = timedelta()
    completed_runs = 0

    for run in runs_data:
        status = run.get("status", "").lower()
        if status == "success":
            stats["successful_runs"] += 1
        elif status in ["error", "failed"]:
            stats["failed_runs"] += 1
        else:
            stats["in_progress"] += 1

        stats["total_tasks"] += run.get("total_tasks", 0)

        if run.get("timestamp"):
            day = run["timestamp"][:10]  # YYYY-MM-DD
            stats["goals_by_day"][day] += 1

        if run.get("model"):
            stats["models_used"][run["model"]] += 1

    if stats["total_runs"] > 0:
        stats["success_rate"] = stats["successful_runs"] / stats["total_runs"] * 100

    # Remove defaultdicts for JSON serialization
    stats["models_used"] = dict(stats["models_used"])
    stats["goals_by_day"] = dict(sorted(stats["goals_by_day"].items(), reverse=True)[:30])

    return JSONResponse(content=stats)


@app.get("/api/search")
async def search_runs(
    q: str = Query(..., description="Search query"),
    limit: int = Query(20, ge=1, le=100)
) -> JSONResponse:
    """Search through runs by goal or task content."""
    results = []
    query_lower = q.lower()

    runs = await list_runs(limit=10000)
    runs_data = json.loads(runs.body)["runs"]

    for run in runs_data:
        score = 0
        matches = []

        # Search in goal
        goal = run.get("goal", "").lower()
        if query_lower in goal:
            score += 10
            matches.append("goal")

        # Get full run data to search in tasks
        try:
            full_data = await get_run_data(run["id"])
            tasks = _flatten_tasks(full_data) if full_data else []
            for task in tasks:
                task_desc = task.get("description", "").lower()
                if query_lower in task_desc:
                    score += 5
                    matches.append(f"task:{task.get('id', 'unknown')}")
        except Exception:
            pass

        if score > 0:
            results.append({
                "run": run,
                "score": score,
                "matches": matches
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return JSONResponse(content={"results": results[:limit]})


# Helper functions

def _flatten_tasks(data: dict) -> list:
    """Return a flat list of task dicts from either checkpoint or summary format.

    Checkpoints store tasks in ``tasks_by_goal`` (dict: goal → list of task
    dicts) and completed results in ``results`` (list of AgentResult dicts
    keyed by ``task_id``).  Summary files store a flat ``tasks`` list.
    """
    # Prefer flat list when it's non-empty
    flat = data.get("tasks", [])

    # Checkpoint format: tasks_by_goal is the authoritative task list
    tasks_by_goal = data.get("tasks_by_goal", {})
    if tasks_by_goal:
        flat = []
        for goal_tasks in tasks_by_goal.values():
            flat.extend(goal_tasks)

    if not flat:
        # Fall back to results list (log summary format)
        flat = data.get("results", [])

    # Enrich with result data when both sources are present
    results_by_id: dict = {}
    for r in data.get("results", []):
        tid = r.get("task_id")
        if tid:
            results_by_id[tid] = r

    if results_by_id:
        enriched = []
        for task in flat:
            tid = task.get("id", task.get("task_id", ""))
            result = results_by_id.get(tid, {})
            merged = {**task}
            if result:
                merged.setdefault("completed", result.get("success", False))
                merged.setdefault("error", result.get("error"))
                merged.setdefault("duration_seconds", result.get("duration_seconds", 0))
                merged.setdefault("output", result.get("output", ""))
                merged.setdefault("agent_model", result.get("agent_model", ""))
            enriched.append(merged)
        return enriched

    return flat


def build_dependency_graph(tasks):
    """Build a Mermaid-compatible dependency graph from tasks."""
    nodes = []
    edges = []
    node_ids = set()

    for i, task in enumerate(tasks):
        task_id = task.get("id", f"task_{i}")
        node_ids.add(task_id)

        # Determine status for styling
        status = "completed" if task.get("completed") else "pending"
        if task.get("error"):
            status = "error"
        elif task.get("in_progress"):
            status = "running"

        nodes.append({
            "id": task_id,
            "label": task.get("description", f"Task {i}")[:50],
            "status": status,
            "layer": task.get("layer", 0),
            "duration": task.get("duration_seconds", 0)
        })

        # Build edges from dependencies
        for dep in task.get("depends_on", []):
            if dep in node_ids:
                edges.append({
                    "from": dep,
                    "to": task_id,
                    "type": "depends_on"
                })

    return {"nodes": nodes, "edges": edges}


def build_timeline(tasks):
    """Build a timeline of task execution."""
    events = []
    for task in tasks:
        if task.get("started_at"):
            events.append({
                "time": task["started_at"],
                "type": "start",
                "task_id": task.get("id"),
                "description": task.get("description", "")
            })
        if task.get("completed_at"):
            events.append({
                "time": task["completed_at"],
                "type": "complete",
                "task_id": task.get("id"),
                "description": task.get("description", "")
            })

    events.sort(key=lambda x: x["time"])
    return events


def calculate_metrics(run_data, tasks: Optional[list] = None):
    """Calculate metrics for a run."""
    if tasks is None:
        tasks = _flatten_tasks(run_data)

    total_duration = sum(
        t.get("duration_seconds", 0) for t in tasks
    )

    model_usage = defaultdict(lambda: {"prompt_tokens": 0, "completion_tokens": 0})
    for task in tasks:
        if "token_usage" in task:
            model = task.get("model", "unknown")
            model_usage[model]["prompt_tokens"] += task["token_usage"].get("prompt", 0)
            model_usage[model]["completion_tokens"] += task["token_usage"].get("completion", 0)

    return {
        "total_tasks": len(tasks),
        "completed_tasks": len([t for t in tasks if t.get("completed")]),
        "failed_tasks": len([t for t in tasks if t.get("error")]),
        "total_duration_seconds": total_duration,
        "model_usage": dict(model_usage),
        "parallel_tasks": run_data.get("parallel_tasks_executed", 0)
    }


async def get_run_data(run_id: str) -> Optional[dict]:
    """Load run data from checkpoint or summary."""
    checkpoint_path = CHECKPOINT_DIR / f"checkpoint-{run_id}.json"
    summary_exact = RUN_SUMMARY_DIR / f"{run_id}.json"

    if checkpoint_path.exists():
        return json.loads(checkpoint_path.read_text())
    elif summary_exact.exists():
        return json.loads(summary_exact.read_text())
    elif RUN_SUMMARY_DIR.exists():
        matches = list(RUN_SUMMARY_DIR.glob(f"{run_id}.json"))
        if matches:
            return json.loads(matches[0].read_text())
    return None


def calculate_differences(run1: dict, run2: dict) -> list:
    """Calculate differences between two runs."""
    differences = []

    # Compare goals
    if run1.get("goal") != run2.get("goal"):
        differences.append({
            "field": "goal",
            "run1": run1.get("goal"),
            "run2": run2.get("goal")
        })

    # Compare statuses
    if run1.get("status") != run2.get("status"):
        differences.append({
            "field": "status",
            "run1": run1.get("status"),
            "run2": run2.get("status")
        })

    # Compare task counts
    tasks1 = run1.get("tasks", run1.get("results", []))
    tasks2 = run2.get("tasks", run2.get("results", []))

    if len(tasks1) != len(tasks2):
        differences.append({
            "field": "task_count",
            "run1": len(tasks1),
            "run2": len(tasks2)
        })

    return differences


def compare_metrics(run1: dict, run2: dict) -> dict:
    """Compare metrics between two runs."""
    metrics1 = calculate_metrics(run1)
    metrics2 = calculate_metrics(run2)

    return {
        "duration_diff": metrics2["total_duration_seconds"] - metrics1["total_duration_seconds"],
        "tasks_diff": metrics2["total_tasks"] - metrics1["total_tasks"],
        "completed_diff": metrics2["completed_tasks"] - metrics1["completed_tasks"],
        "success_rate_improvement": (
            (metrics2["completed_tasks"] / metrics2["total_tasks"] if metrics2["total_tasks"] else 0) -
            (metrics1["completed_tasks"] / metrics1["total_tasks"] if metrics1["total_tasks"] else 0)
        ) * 100
    }


def start_server(host: str = "0.0.0.0", port: int = 8000):
    """Start the FastAPI server."""
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_server()
