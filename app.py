# app.py
"""Flask web application — imports optimizer and tasks, no circular deps"""
import os
import json
import threading
from datetime import datetime
from functools import wraps

from flask import Flask, request, jsonify
from flask_cors import CORS

# Import optimizer logic
from optimizer import (
    _do_optimize,
    build_distance_matrix,
    spatial_filter,
    OptimizationResult,
)

# Import Celery tasks (tasks.py imports optimizer, NOT app)
from tasks import celery, optimize_route_task, health_check_task

# ─── Flask App Setup ──────────────────────────────────────────────

app = Flask(__name__)
CORS(app)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-key-change-in-prod")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB

# ─── Database ───────────────────────────────────────────────────────

import psycopg2
from psycopg2.extras import RealDictCursor

def get_db():
    """Get PostgreSQL connection."""
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        database=os.getenv("PGDATABASE", "grps"),
        user=os.getenv("PGUSER", "grps_user"),
        password=os.getenv("PGPASSWORD", "grps_pass"),
        port=os.getenv("PGPORT", "5432"),
    )


def init_db():
    """Initialize schema if not exists."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS optimization_jobs (
                    id SERIAL PRIMARY KEY,
                    task_id VARCHAR(64) UNIQUE,
                    status VARCHAR(20) DEFAULT 'pending',
                    depot_id INTEGER,
                    customer_count INTEGER,
                    vehicle_count INTEGER,
                    result JSONB,
                    created_at TIMESTAMP DEFAULT NOW(),
                    completed_at TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_jobs_task_id 
                ON optimization_jobs(task_id);

                CREATE INDEX IF NOT EXISTS idx_jobs_status 
                ON optimization_jobs(status);
            """)
        conn.commit()
    print("[db] ✅ PostgreSQL schema ready")


# ─── Threading Fallback (when Celery unavailable) ───────────────────

class ThreadingFallback:
    """Simple threading fallback for local dev / Render free tier."""

    def __init__(self):
        self._results = {}
        self._lock = threading.Lock()

    def delay(self, task_func, *args, **kwargs):
        """Run task in background thread."""
        task_id = f"thread-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

        def run_task():
            try:
                result = task_func(*args, **kwargs)
                with self._lock:
                    self._results[task_id] = {
                        "status": "SUCCESS",
                        "result": result,
                    }
            except Exception as e:
                with self._lock:
                    self._results[task_id] = {
                        "status": "FAILURE",
                        "result": str(e),
                    }

        thread = threading.Thread(target=run_task, daemon=True)
        thread.start()

        with self._lock:
            self._results[task_id] = {"status": "PENDING"}

        return FakeAsyncResult(task_id, self)

    def get_result(self, task_id):
        with self._lock:
            return self._results.get(task_id, {"status": "NOT_FOUND"})


class FakeAsyncResult:
    def __init__(self, task_id, fallback):
        self.id = task_id
        self._fallback = fallback

    def get(self, timeout=None, propagate=True):
        import time
        start = time.time()
        while True:
            result = self._fallback.get_result(self.id)
            if result["status"] in ("SUCCESS", "FAILURE"):
                return result["result"]
            if timeout and (time.time() - start) > timeout:
                raise TimeoutError()
            time.sleep(0.5)

    @property
    def state(self):
        result = self._fallback.get_result(self.id)
        return result["status"]


# Detect Celery availability
try:
    # Verify Celery can actually connect
    celery.connection().ensure_connection(max_retries=1)
    CELERY_AVAILABLE = True
    print("[celery] ✅ Celery connected to Redis")
except Exception as e:
    CELERY_AVAILABLE = False
    _fallback = ThreadingFallback()
    print(f"[celery] ⚠️  Celery not available ({e}) — using threading fallback")


def run_async_task(task_func, *args, **kwargs):
    """Dispatch to Celery or threading fallback."""
    if CELERY_AVAILABLE:
        return task_func.delay(*args, **kwargs)
    else:
        return _fallback.delay(task_func, *args, **kwargs)


# ─── API Routes ─────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    db_ok = False
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                db_ok = True
    except Exception:
        pass

    celery_ok = CELERY_AVAILABLE
    if celery_ok:
        try:
            health_check_task.delay()
        except Exception:
            celery_ok = False

    return jsonify({
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "error",
        "celery": "connected" if celery_ok else "fallback",
        "timestamp": datetime.utcnow().isoformat(),
    })


@app.route("/api/optimize", methods=["POST"])
def optimize():
    """
    Trigger async optimization.
    Returns task ID for polling.
    """
    data = request.get_json()

    # Validate
    required = ["depot_id", "customer_ids", "vehicle_count", "locations"]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400

    depot_id = data["depot_id"]
    customer_ids = data["customer_ids"]
    vehicle_count = data["vehicle_count"]
    locations = data["locations"]  # [[lat, lon], ...]
    matrix_source = data.get("matrix_source", "osrm")
    deadline = data.get("deadline_seconds", 30.0)

    # Store job in DB
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO optimization_jobs 
                (depot_id, customer_count, vehicle_count, status)
                VALUES (%s, %s, %s, 'pending')
                RETURNING id
            """, (depot_id, len(customer_ids), vehicle_count))
            job_id = cur.fetchone()[0]
        conn.commit()

    # Dispatch async task
    task = run_async_task(
        optimize_route_task,
        depot_id=depot_id,
        customer_ids=customer_ids,
        vehicle_count=vehicle_count,
        location_coords=locations,
        matrix_source=matrix_source,
        deadline_seconds=deadline,
    )

    # Update with task_id
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE optimization_jobs 
                SET task_id = %s WHERE id = %s
            """, (task.id, job_id))
        conn.commit()

    return jsonify({
        "task_id": task.id,
        "job_id": job_id,
        "status": "queued",
        "celery": CELERY_AVAILABLE,
    }), 202


@app.route("/api/optimize/sync", methods=["POST"])
def optimize_sync():
    """
    Synchronous optimization (for small problems).
    """
    data = request.get_json()

    locations = data["locations"]
    depot_id = data.get("depot_id", 0)
    customer_ids = data.get("customer_ids", list(range(1, len(locations))))
    vehicle_count = data.get("vehicle_count", 3)
    matrix_source = data.get("matrix_source", "osrm")
    deadline = data.get("deadline_seconds", 30.0)

    # Filter + build matrix
    filtered_locs, indices, pairs = spatial_filter(locations, depot_idx=0, k_nearest=10)
    print(f"[spatial filter] {len(locations)} locations → {len(pairs)} API pairs")

    matrix = build_distance_matrix(filtered_locs, source=matrix_source, deadline_seconds=10.0)
    print(f"[matrix] ✅ {matrix.shape} source={matrix_source}")

    # Optimize
    print(f"[optimize] Model depots=1 custs={len(customer_ids)} vehicles={vehicle_count}")
    result = _do_optimize(
        depot_id=depot_id,
        customer_ids=customer_ids,
        vehicle_count=vehicle_count,
        distance_matrix=matrix,
        deadline_seconds=deadline,
    )

    return jsonify({
        "status": result.status,
        "routes": result.routes,
        "total_distance": result.total_distance,
        "compute_time_ms": round(result.compute_time_ms, 2),
        "solver": result.solver,
    })


@app.route("/api/result/<task_id>", methods=["GET"])
def get_result(task_id):
    """Poll for async task result."""
    if CELERY_AVAILABLE:
        from celery.result import AsyncResult
        task_result = AsyncResult(task_id, app=celery)

        if task_result.state == "PENDING":
            return jsonify({"status": "pending", "task_id": task_id}), 202
        elif task_result.state == "PROGRESS":
            return jsonify({
                "status": "running",
                "task_id": task_id,
                "meta": task_result.info,
            }), 202
        elif task_result.state == "SUCCESS":
            # Update DB
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE optimization_jobs 
                        SET status = 'completed', 
                            result = %s,
                            completed_at = NOW()
                        WHERE task_id = %s
                    """, (json.dumps(task_result.result), task_id))
                conn.commit()

            return jsonify({
                "status": "completed",
                "task_id": task_id,
                "result": task_result.result,
            })
        else:
            return jsonify({
                "status": "failed",
                "task_id": task_id,
                "error": str(task_result.info),
            }), 500
    else:
        # Threading fallback
        result = _fallback.get_result(task_id)
        if result["status"] == "NOT_FOUND":
            return jsonify({"status": "not_found"}), 404
        elif result["status"] == "PENDING":
            return jsonify({"status": "pending"}), 202
        else:
            return jsonify({
                "status": "completed" if result["status"] == "SUCCESS" else "failed",
                "result": result["result"],
            })


@app.route("/api/jobs", methods=["GET"])
def list_jobs():
    """List recent optimization jobs."""
    limit = request.args.get("limit", 50, type=int)

    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, task_id, status, depot_id, customer_count,
                       vehicle_count, created_at, completed_at
                FROM optimization_jobs
                ORDER BY created_at DESC
                LIMIT %s
            """, (limit,))
            jobs = cur.fetchall()

    return jsonify({"jobs": jobs, "count": len(jobs)})


# ─── Main ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
