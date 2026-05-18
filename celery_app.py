"""
Celery application configuration for GRPS Web.
Uses Redis as both broker and result backend.
"""

import os
from celery import Celery
from celery.signals import worker_process_init

# ── Redis URL ────────────────────────────────────────────────────────────────
# Render provides REDIS_URL automatically when a Redis instance is attached.
# For local development, fall back to redis://localhost:6379/0.
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# ── Celery App ─────────────────────────────────────────────────────────────
celery_app = Celery(
    "grps",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks"],  # tasks module will be registered
)

# ── Configuration ────────────────────────────────────────────────────────────
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Reliability — ack only after task completes, survive worker crash
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,

    # Memory management — recycle workers to prevent leaks
    worker_max_tasks_per_child=100,
    worker_max_memory_per_child=300000,  # 300 MB

    # Timeouts — optimization can take up to 15 minutes
    task_soft_time_limit=900,   # 15 min soft limit (can catch & cleanup)
    task_time_limit=960,        # 16 min hard limit (SIGKILL after this)

    # Result backend — keep results for 2 hours (longer than any poll cycle)
    result_expires=7200,

    # Redis-specific — visibility timeout must exceed longest ETA/countdown
    # We don't use ETA/countdown, but set generously for safety
    broker_transport_options={
        "visibility_timeout": 1200,  # 20 minutes
        "queue_order_strategy": "priority",
    },

    # Task routing — optimization tasks go to dedicated queue
    task_routes={
        "tasks.optimize_routes": {"queue": "optimization"},
    },

    # Default queue
    task_default_queue="default",
)

# ── Worker init ─────────────────────────────────────────────────────────────
@worker_process_init.connect
def init_worker(**kwargs):
    """Called when each worker process starts.

    We import the VRP solver modules here so they're loaded once per
    worker process, not per task. This avoids the import overhead on every
    optimization job.
    """
    import numpy as np
    # Pre-warm numpy RNG
    np.random.default_rng(42)
    print("[celery] Worker process initialized")


if __name__ == "__main__":
    celery_app.start()
