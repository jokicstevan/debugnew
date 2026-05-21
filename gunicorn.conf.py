"""
gunicorn.conf.py — GRPS Weight server configuration.

Why this file exists
---------------------
The 502 on /api/optimize/status is caused by gunicorn having only ONE worker
process.  The ALNS solver is CPU-bound (holds Python's GIL during pure-Python
loops) so all threads in that single process are starved while it runs.
Render's load balancer then times out waiting for any response → 502.

Fix: at least 2 *worker processes* so one can run a fallback-thread
optimization while the other serves status polls (and all other API calls).

Workers vs threads
------------------
  workers  = OS processes (each gets its own GIL and memory space)
  threads  = threads inside each process (share GIL — bad for CPU work)

We want 2 processes × 2 threads = 4 concurrent slots, but crucially
each process is independently schedulable by the OS.

Memory on Render free tier (~512 MB)
-------------------------------------
  numpy + alns + reportlab + Flask ≈ 150 MB per worker
  2 workers with preload_app = True  ≈ 150 MB shared + small per-worker delta
  Safe headroom for Celery worker running on the same dyno is tight;
  keep web workers at 2 and celery concurrency at 1–2.
"""

import multiprocessing

# ── Worker processes ──────────────────────────────────────────────────────────
# 2 processes = optimization in one process won't block status polls in the other.
# Do NOT set this to (2 * cpu_count + 1) on Render free tier — you'll OOM.
workers = 2
worker_class = "gthread"
threads = 2                 # 2 threads per worker; multiply = 4 total slots

# ── Timeouts ─────────────────────────────────────────────────────────────────
# Must exceed the longest possible ALNS run (80+ customers ≈ 8–10 min).
timeout          = 900      # 15 min hard timeout per request
graceful_timeout = 30       # wait 30 s for in-flight requests on SIGTERM
keepalive        = 5        # keep TCP connection open for 5 s

# ── Memory efficiency ─────────────────────────────────────────────────────────
# Load the app once in the master process, then fork.  Workers share the
# code pages (Copy-on-Write), saving ~100 MB vs loading fresh per worker.
# Side-effect: module-level state (threading.Lock, _local_jobs, etc.) is
# forked into each worker — fine here since they're all re-initialised.
preload_app = True

# ── Request recycling ─────────────────────────────────────────────────────────
# Recycle workers after N requests to prevent slow memory leaks from numpy.
max_requests        = 500
max_requests_jitter = 50    # randomise so workers don't all restart at once

# ── Logging ──────────────────────────────────────────────────────────────────
accesslog  = "-"            # stdout — Render captures it
errorlog   = "-"
loglevel   = "warning"      # info is very verbose; switch to debug to diagnose


# ── Worker lifecycle hooks ────────────────────────────────────────────────────
def post_fork(server, worker):
    """Re-start the DB schema-init thread inside each forked worker.

    WHY THIS IS NEEDED
    ------------------
    With preload_app=True gunicorn loads the module *once in the master*,
    which starts the _ensure_schema background thread there.  When gunicorn
    forks worker processes, Python threads are NOT inherited — only memory is
    copied.  Every worker therefore starts with _db_ready=False and no thread
    running to flip it, so the DB is never written to and every job stays
    in-memory-only forever.

    This hook fires inside each newly-forked worker and restarts the thread,
    giving each worker its own independent schema-init that sets _db_ready=True
    in that worker's memory space.
    """
    import threading
    from app import _ensure_schema
    threading.Thread(target=_ensure_schema, daemon=True, name="schema-init").start()
    server.log.info(f"[gunicorn] post_fork worker={worker.pid} — schema-init thread started")
