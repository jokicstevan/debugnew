"""
Celery tasks for GRPS Web.
Contains the optimization task that runs in a separate worker process.
"""

import os
import sys
import json
import traceback
from datetime import date

# Add the project root to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from celery_app import celery_app

# ── Import the optimization logic from app.py ──────────────────────────────
# We import only what we need to avoid circular imports.
# The heavy imports (numpy, psycopg, reportlab) happen here in the worker.

import numpy as np

# Import the core optimization functions and VRPState from app.py
# These are stateless and safe to run in a Celery worker.
from app import (
    _do_optimize,
    _save_route_to_db_async,
    in_serbia,
    build_api_pairs,
    fetch_best_matrix,
    fetch_best_route,
    prefetch_traffic_history,
    _get_db_conn,
    _db_ready,
    DATABASE_URL,
    HERE_API_KEY,
    K_NEAREST,
    SENTINEL_FACTOR,
    FUEL_PRICE_RSD_PER_LITRE,
    DRIVER_WAGE_RSD_PER_HOUR,
    FUEL_LOAD_FACTOR_PER_1000KG,
    DEFAULT_PKG_WEIGHTS_KG,
    SERVICE_TIME,
    VRPState,
    route_time,
    route_dist,
    route_fuel_litres,
    route_working_minutes,
    latest_feasible_departure,
    mins_to_hhmm,
    optimize_nn,
    optimize_2opt,
    optimize_alns,
    haversine,
    build_haversine_matrix,
    straight_line_geometry,
    fetch_osrm_route,
    fetch_here_route,
    fetch_here_matrix,
    fetch_osrm_matrix,
    _haversine_matrix_km,
    _expand_matrix,
    _blend_historical,
    get_historical_time_mat,
)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def optimize_routes(self, payload, user):
    """Run route optimization in a Celery worker.

    Parameters
    ----------
    payload : dict
        The full optimization request data (same as what /api/optimize receives).
    user : str
        The username who initiated the optimization.

    Returns
    -------
    dict
        The optimization result (same format as _do_optimize returns).

    Raises
    ------
    Exception
        Re-raised after logging; Celery retry logic handles transient failures.
    """
    try:
        print(f"[celery] Starting optimization task {self.request.id} for user {user}")

        # Run the actual optimization
        result = _do_optimize(payload, user)

        print(f"[celery] Optimization task {self.request.id} completed successfully")
        return result

    except Exception as exc:
        print(f"[celery] Optimization task {self.request.id} failed: {exc}")
        print(traceback.format_exc())
        # Re-raise so Celery can retry (if retries remain)
        raise self.retry(exc=exc)


@celery_app.task(bind=True, ignore_result=True)
def save_route_async(self, route_payload):
    """Persist a route to the database asynchronously.

    This is a fire-and-forget task — the web process doesn't wait for it.
    """
    try:
        _save_route_to_db_async(route_payload)
    except Exception as exc:
        print(f"[celery] Async route save failed: {exc}")
        # Don't retry — this is best-effort persistence
