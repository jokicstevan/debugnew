# tasks.py
"""Celery background tasks — imports optimizer, NOT app.py"""
import os
from celery import Celery
from celery.signals import worker_ready
from optimizer import _do_optimize, build_distance_matrix, spatial_filter

# Initialize Celery — no Flask app needed
celery = Celery(
    "grps",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 min hard limit
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)


@celery.task(bind=True, max_retries=3)
def optimize_route_task(
    self,
    depot_id: int,
    customer_ids: list,
    vehicle_count: int,
    location_coords: list,  # [(lat, lon), ...]
    matrix_source: str = "osrm",
    deadline_seconds: float = 30.0
):
    """
    Background VRP optimization task.
    Called by Flask via .delay() or .apply_async()
    """
    try:
        # Update progress
        self.update_state(state="PROGRESS", meta={"step": "building_matrix"})

        # Build distance matrix
        locations, _, _ = spatial_filter(location_coords, depot_idx=0, k_nearest=10)
        matrix = build_distance_matrix(locations, source=matrix_source)

        self.update_state(state="PROGRESS", meta={"step": "optimizing"})

        # Run optimization
        result = _do_optimize(
            depot_id=depot_id,
            customer_ids=customer_ids,
            vehicle_count=vehicle_count,
            distance_matrix=matrix,
            deadline_seconds=deadline_seconds,
        )

        return {
            "status": result.status,
            "routes": result.routes,
            "total_distance": result.total_distance,
            "compute_time_ms": result.compute_time_ms,
            "solver": result.solver,
        }

    except Exception as exc:
        # Retry on failure
        raise self.retry(exc=exc, countdown=60)


@celery.task
def health_check_task():
    """Simple health check for Celery workers."""
    return {"status": "ok", "worker": "grps-celery"}


@worker_ready.connect
def on_worker_ready(**kwargs):
    """Log when worker is ready."""
    print("[celery] ✅ Worker ready and connected to Redis")
