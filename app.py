"""
GRPS Web — Belgrade Delivery Route Planner
Flask backend: auth, optimization, OSRM, PDF, Excel import
"""

import os, copy, math, json, io, tempfile, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import numpy as np


def _json_default(obj):
    """Custom JSON serializer for types stdlib json cannot handle.

    numpy.int32 / numpy.int64 appear in route indices and schedule entries.
    numpy.float32 / numpy.float64 appear in distance/time matrix values.
    Without this, json.dumps() raises TypeError and _job_set_done() silently
    discards the optimization result, leaving the job stuck as 'running'.
    """
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

import psycopg
from collections import defaultdict
from datetime import datetime, date, timedelta
from functools import wraps

from flask import (Flask, render_template, request, jsonify,
                   session, redirect, url_for, send_file, abort)
from werkzeug.utils import secure_filename

# PDF
from reportlab.lib import colors as rl_colors
from reportlab.lib.pagesizes import A4
import base64
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                 Table, TableStyle, Image as RLImage)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT

# --- LOGGING (heavy job logging) ----------------------------------------------
import logging
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

log_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

file_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, "grps.log"),
    maxBytes=10*1024*1024,
    backupCount=5,
    encoding='utf-8'
)
file_handler.setFormatter(log_formatter)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

logger = logging.getLogger("grps")
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Prevent duplicate logs in some environments
logger.propagate = False

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "grps-secret-2024-change-me")
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB upload limit
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
REPORT_FOLDER = os.path.join(os.path.dirname(__file__), "reports")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(REPORT_FOLDER, exist_ok=True)

# ── PostgreSQL (Render managed DB) ────────────────────────────────────────────
# Render injects DATABASE_URL automatically when a PostgreSQL database is
# attached to this service.  All DB code is fully optional: if DATABASE_URL
# is not set the app works exactly as before (routes are not persisted).

DATABASE_URL = os.environ.get("DATABASE_URL", "")
# Render uses the "postgres://" scheme; psycopg2 requires "postgresql://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_db_ready = False   # set to True after schema is confirmed


def _get_db_conn():
    """Return a new psycopg3 connection, or raise if DATABASE_URL not set."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not configured")
    return psycopg.connect(DATABASE_URL, connect_timeout=5)


def _ensure_schema():
    """Create tables if they don't exist yet (idempotent, runs once on startup)."""
    global _db_ready
    if not DATABASE_URL:
        return
    try:
        conn = _get_db_conn()
        cur  = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS grps_routes (
                route_id        SERIAL PRIMARY KEY,
                route_date      DATE        NOT NULL DEFAULT CURRENT_DATE,
                saved_by        VARCHAR(50) NOT NULL DEFAULT 'unknown',
                algorithm       VARCHAR(30) NOT NULL DEFAULT 'ALNS',
                matrix_source   VARCHAR(20) NOT NULL DEFAULT 'osrm',
                depot_name      VARCHAR(100),
                depot_lat       DOUBLE PRECISION,
                depot_lng       DOUBLE PRECISION,
                vehicle_type    VARCHAR(50),
                total_distance_km  DOUBLE PRECISION,
                total_fuel_litres  DOUBLE PRECISION,
                fuel_cost_rsd      DOUBLE PRECISION,
                wage_cost_rsd      DOUBLE PRECISION,
                total_cost_rsd     DOUBLE PRECISION,
                working_hours      DOUBLE PRECISION,
                departure_time     VARCHAR(8),
                return_time        VARCHAR(8),
                volume_used_m3     DOUBLE PRECISION,
                weight_used_kg     DOUBLE PRECISION,
                num_stops          INTEGER,
                fuel_price_rsd_l   DOUBLE PRECISION,
                driver_wage_rsd_h  DOUBLE PRECISION,
                notes              TEXT,
                created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS grps_route_stops (
                stop_id         SERIAL PRIMARY KEY,
                route_id        INTEGER NOT NULL REFERENCES grps_routes(route_id) ON DELETE CASCADE,
                stop_sequence   INTEGER NOT NULL,
                customer_name   VARCHAR(200),
                lat             DOUBLE PRECISION,
                lng             DOUBLE PRECISION,
                arrival_time    VARCHAR(8),
                departure_time  VARCHAR(8),
                wait_minutes    INTEGER DEFAULT 0,
                tw_violation_min INTEGER DEFAULT 0,
                service_time_min INTEGER DEFAULT 10,
                packages1       DOUBLE PRECISION DEFAULT 0,
                packages2       DOUBLE PRECISION DEFAULT 0,
                packages3       DOUBLE PRECISION DEFAULT 0,
                volume_m3       DOUBLE PRECISION DEFAULT 0,
                weight_kg       DOUBLE PRECISION DEFAULT 0,
                tw_start        VARCHAR(8),
                tw_end          VARCHAR(8)
            )
        """)
        # ── Workspaces ────────────────────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS grps_workspaces (
                workspace_id   SERIAL PRIMARY KEY,
                name           VARCHAR(200) NOT NULL,
                description    TEXT,
                created_by     VARCHAR(50)  NOT NULL DEFAULT 'unknown',
                updated_by     VARCHAR(50)  NOT NULL DEFAULT 'unknown',
                created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                depots         JSONB        NOT NULL DEFAULT '[]',
                customers      JSONB        NOT NULL DEFAULT '[]',
                fleet          JSONB        NOT NULL DEFAULT '[]',
                settings       JSONB        NOT NULL DEFAULT '{}',
                result         JSONB
            )
        """)

        # ── Traffic history cache ─────────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS grps_traffic_cache (
                cache_id        SERIAL PRIMARY KEY,
                orig_lat        DOUBLE PRECISION NOT NULL,
                orig_lng        DOUBLE PRECISION NOT NULL,
                dest_lat        DOUBLE PRECISION NOT NULL,
                dest_lng        DOUBLE PRECISION NOT NULL,
                slot_minutes    SMALLINT         NOT NULL,
                travel_time_min DOUBLE PRECISION NOT NULL,
                dist_km         DOUBLE PRECISION NOT NULL,
                fetched_at      TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
                UNIQUE (orig_lat, orig_lng, dest_lat, dest_lng, slot_minutes, fetched_at)
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_traffic_cache_lookup
            ON grps_traffic_cache (orig_lat, orig_lng, dest_lat, dest_lng, slot_minutes)
        """)

        # ── Async optimization job queue ─────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS grps_jobs (
                job_id      TEXT        PRIMARY KEY,
                status      TEXT        NOT NULL DEFAULT 'running',
                result_json TEXT,
                error       TEXT,
                owner       TEXT        NOT NULL DEFAULT 'unknown',
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        cur.execute("""
            DELETE FROM grps_jobs
            WHERE status != 'running'
              AND created_at < NOW() - INTERVAL '2 hours'
        """)

        conn.commit()
        conn.close()
        _db_ready = True
        logger.info("✅ PostgreSQL schema ready")
    except Exception as e:
        logger.error(f"Schema init failed: {e}")


# Run schema setup in a background thread so a slow DB doesn't delay startup
threading.Thread(target=_ensure_schema, daemon=True).start()


# ── Postgres-backed job store helpers ─────────────────────────────────────────

_local_jobs: dict = {}   # fallback when DATABASE_URL is not set
_running_jobs: dict = {}  # job_id -> threading.Event (cancellation flag)


def _job_create(job_id: str, owner: str):
    """Create a new job entry. Also store a cancellation event."""
    _running_jobs[job_id] = threading.Event()
    if not DATABASE_URL:
        _local_jobs[job_id] = {"status": "running", "result": None, "error": None}
        logger.info(f"Job {job_id} created (in-memory fallback) by {owner}")
        return
    try:
        conn = _get_db_conn()
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO grps_jobs (job_id, status, owner) VALUES (%s, 'running', %s)",
            (job_id, owner)
        )
        conn.commit()
        conn.close()
        logger.info(f"Job {job_id} created in DB by {owner}")
    except Exception as exc:
        logger.error(f"Job create failed: {exc}")
        _local_jobs[job_id] = {"status": "running", "result": None, "error": None}


def _job_set_done(job_id: str, result_dict: dict):
    logger.info(f"Job {job_id} finished with result (keys: {list(result_dict.keys())})")
    _running_jobs.pop(job_id, None)  # remove cancellation event
    if not DATABASE_URL:
        if job_id in _local_jobs:
            _local_jobs[job_id].update({"status": "done", "result": result_dict})
        return
    try:
        conn = _get_db_conn()
        cur  = conn.cursor()
        cur.execute(
            "UPDATE grps_jobs SET status='done', result_json=%s, updated_at=NOW() WHERE job_id=%s",
            (json.dumps(result_dict, default=_json_default), job_id)
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.error(f"Job set_done failed: {exc}")
        _local_jobs[job_id] = {"status": "done", "result": result_dict}


def _job_set_error(job_id: str, error: str):
    logger.error(f"Job {job_id} error: {error}")
    _running_jobs.pop(job_id, None)
    if not DATABASE_URL:
        if job_id in _local_jobs:
            _local_jobs[job_id].update({"status": "error", "error": error})
        return
    try:
        conn = _get_db_conn()
        cur  = conn.cursor()
        cur.execute(
            "UPDATE grps_jobs SET status='error', error=%s, updated_at=NOW() WHERE job_id=%s",
            (error, job_id)
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.error(f"Job set_error failed: {exc}")
        _local_jobs[job_id] = {"status": "error", "error": error}


def _job_get(job_id: str):
    """Return {status, result, error} or None if not found."""
    if not DATABASE_URL:
        return _local_jobs.get(job_id)
    try:
        conn = _get_db_conn()
        cur  = conn.cursor()
        cur.execute(
            "SELECT status, result_json, error FROM grps_jobs WHERE job_id=%s",
            (job_id,)
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        status, result_json, error = row
        return {"status": status,
                "result": json.loads(result_json) if result_json else None,
                "error":  error}
    except Exception as exc:
        logger.error(f"Job get failed: {exc}")
        return None


# --- Cancel job endpoint -------------------------------------------------------
@app.route("/api/optimize/cancel/<job_id>", methods=["POST"])
@login_required
def cancel_job(job_id):
    """Request cancellation of a running optimisation job."""
    logger.info(f"Cancel request for job {job_id} from user {session.get('user')}")
    job = _job_get(job_id)
    if job is None:
        return jsonify({"ok": False, "error": "Job not found"}), 404
    if job["status"] != "running":
        return jsonify({"ok": False, "error": f"Job is not running (status={job['status']})"}), 400
    event = _running_jobs.get(job_id)
    if event:
        event.set()
        logger.info(f"Cancel event set for job {job_id}")
        return jsonify({"ok": True, "message": "Cancellation requested"})
    else:
        # fallback: set error directly (should not happen)
        _job_set_error(job_id, "Cancelled by user")
        return jsonify({"ok": True, "message": "Job cancelled (no active thread)"})


# --- Save route to DB (unchanged, but added logging) --------------------------
def _save_route_to_db_async(payload: dict):
    """Persist one vehicle route to PostgreSQL in a background thread."""
    if not DATABASE_URL:
        return

    def _insert():
        try:
            vr          = payload["vehicle_route"]
            route_date  = payload.get("route_date", str(date.today()))
            saved_by    = payload.get("saved_by", "unknown")
            algorithm   = payload.get("algorithm", "ALNS")
            matrix_src  = payload.get("matrix_source", "osrm")
            fuel_price  = payload.get("fuel_price_rsd_l",  200.0)
            wage_rate   = payload.get("driver_wage_rsd_h", 900.0)

            conn = _get_db_conn()
            cur  = conn.cursor()

            cur.execute("""
                INSERT INTO grps_routes
                    (route_date, saved_by, algorithm, matrix_source,
                     depot_name, depot_lat, depot_lng, vehicle_type,
                     total_distance_km, total_fuel_litres, fuel_cost_rsd,
                     wage_cost_rsd, total_cost_rsd,
                     working_hours, departure_time, return_time,
                     volume_used_m3, weight_used_kg, num_stops,
                     fuel_price_rsd_l, driver_wage_rsd_h, notes)
                VALUES
                    (%s,%s,%s,%s, %s,%s,%s,%s, %s,%s,%s, %s,%s,
                     %s,%s,%s, %s,%s,%s, %s,%s,%s)
                RETURNING route_id
            """, (
                route_date, saved_by, algorithm, matrix_src,
                vr.get("depot_name"),
                vr.get("depot_lat"),
                vr.get("depot_lng"),
                vr.get("type"),
                vr.get("distance"),
                vr.get("fuel_used"),
                vr.get("fuel_cost_rsd"),
                vr.get("wage_cost_rsd"),
                vr.get("total_cost_rsd"),
                vr.get("working_hours"),
                vr.get("departure_time"),
                vr.get("return_time"),
                vr.get("volume_used"),
                vr.get("weight_used"),
                vr.get("num_customers"),
                fuel_price,
                wage_rate,
                f"Saved by: {saved_by}",
            ))
            route_id = cur.fetchone()[0]

            # Insert stops
            for seq, stop in enumerate(vr.get("stops", []), start=1):
                pc = stop.get("pkg_counts", [0, 0, 0])
                while len(pc) < 3:
                    pc.append(0)
                wt_kg = (pc[0] or 0) * 5.0 + (pc[1] or 0) * 15.0 + (pc[2] or 0) * 30.0
                cur.execute("""
                    INSERT INTO grps_route_stops
                        (route_id, stop_sequence, customer_name, lat, lng,
                         arrival_time, departure_time,
                         wait_minutes, tw_violation_min, service_time_min,
                         packages1, packages2, packages3,
                         volume_m3, weight_kg, tw_start, tw_end)
                    VALUES (%s,%s,%s,%s,%s, %s,%s, %s,%s,%s, %s,%s,%s, %s,%s,%s,%s)
                """, (
                    route_id, seq,
                    stop.get("name", "")[:200],
                    stop.get("lat"), stop.get("lng"),
                    stop.get("arrival"), stop.get("depart"),
                    int(stop.get("wait", 0)),
                    int(stop.get("violation", 0)),
                    int(stop.get("service_time", 10)),
                    round(float(pc[0] or 0), 4),
                    round(float(pc[1] or 0), 4),
                    round(float(pc[2] or 0), 4),
                    float(stop.get("volume", 0)),
                    round(wt_kg, 1),
                    stop.get("tw_start"), stop.get("tw_end"),
                ))

            conn.commit()
            conn.close()
            logger.info(f"RouteID={route_id} saved ({vr.get('num_customers')} stops)")
        except Exception as exc:
            import traceback
            logger.error(f"Save route failed: {exc}\n{traceback.format_exc()}")

    threading.Thread(target=_insert, daemon=True).start()


# --- HISTORICAL TRAFFIC CACHE (unchanged, but added logging) -----------------
_TRAFFIC_FETCH_POOL_SIZE = 2
_TRAFFIC_HISTORY_DAYS    = 14
_TRAFFIC_FETCH_DAYS_PER_RUN = 3
_TRAFFIC_SLOT_MINUTES    = 15

_prefetch_lock = threading.Lock()


def _round_coord(v):
    return round(float(v), 5)


def _slot_minutes(dt_utc):
    total = dt_utc.hour * 60 + dt_utc.minute
    return (total // _TRAFFIC_SLOT_MINUTES) * _TRAFFIC_SLOT_MINUTES


def _fetch_here_for_slot(origin, destination, departure_iso):
    if not HERE_API_KEY:
        return None, None
    params = {
        "apiKey":        HERE_API_KEY,
        "transportMode": "car",
        "routingMode":   "fast",
        "departureTime": departure_iso,
        "origin":        f"{origin['lat']},{origin['lng']}",
        "destination":   f"{destination['lat']},{destination['lng']}",
        "return":        "summary",
    }
    try:
        resp = requests.get("https://router.hereapi.com/v8/routes",
                            params=params, timeout=(5, 12))
        if resp.status_code == 200:
            routes = resp.json().get("routes", [])
            if routes:
                s = routes[0]["sections"][0]["summary"]
                return s["duration"] / 60.0, s["length"] / 1000.0
        logger.debug(f"Traffic cache HERE {resp.status_code} for {departure_iso}")
    except Exception as exc:
        logger.debug(f"Traffic cache exception: {exc}")
    return None, None


def _upsert_traffic_rows(rows):
    if not DATABASE_URL or not rows:
        return
    try:
        conn = _get_db_conn()
        cur  = conn.cursor()
        cur.executemany("""
            INSERT INTO grps_traffic_cache
                (orig_lat, orig_lng, dest_lat, dest_lng, slot_minutes,
                 travel_time_min, dist_km, fetched_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (orig_lat, orig_lng, dest_lat, dest_lng, slot_minutes, fetched_at)
            DO NOTHING
        """, rows)
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.error(f"Traffic upsert failed: {exc}")


def prefetch_traffic_history(locations, pairs):
    if not DATABASE_URL or not HERE_API_KEY:
        return

    def _run():
        if not _prefetch_lock.acquire(blocking=False):
            logger.info("Traffic prefetch skipped — another prefetch already running")
            return
        try:
            already = set()
            try:
                conn = _get_db_conn()
                cur  = conn.cursor()
                for (i, j) in pairs:
                    olat = _round_coord(locations[i]["lat"])
                    olng = _round_coord(locations[i]["lng"])
                    dlat = _round_coord(locations[j]["lat"])
                    dlng = _round_coord(locations[j]["lng"])
                    cur.execute(f"""
                        SELECT slot_minutes, DATE(fetched_at)
                        FROM grps_traffic_cache
                        WHERE orig_lat=%s AND orig_lng=%s
                          AND dest_lat=%s AND dest_lng=%s
                          AND fetched_at >= NOW() - INTERVAL '{_TRAFFIC_HISTORY_DAYS} days'
                    """, (olat, olng, dlat, dlng))
                    for row in cur.fetchall():
                        already.add((i, j, int(row[0]), str(row[1])))
                conn.close()
            except Exception as exc:
                logger.warning(f"Traffic pre-check failed: {exc}")
                already = set()

            today_utc = datetime.utcnow().date()
            work = []
            for day_offset in range(_TRAFFIC_HISTORY_DAYS):
                if day_offset >= _TRAFFIC_FETCH_DAYS_PER_RUN:
                    break
                day = today_utc - timedelta(days=day_offset + 1)
                for (i, j) in pairs:
                    for slot in range(0, 24 * 60, _TRAFFIC_SLOT_MINUTES):
                        if (i, j, slot, str(day)) not in already:
                            work.append((i, j, day, slot))

            if not work:
                logger.info("Traffic cache: all pairs already cached — nothing to fetch")
                return

            logger.info(f"Traffic cache starting prefetch: {len(work)} calls")
            batch = []

            def _do_fetch(item):
                fi, fj, fday, fslot = item
                origin      = locations[fi]
                destination = locations[fj]
                dep_dt  = datetime(fday.year, fday.month, fday.day,
                                   fslot // 60, fslot % 60, 0)
                dep_iso = dep_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                time.sleep(0.15)
                tt, dk  = _fetch_here_for_slot(origin, destination, dep_iso)
                if tt is not None:
                    return (
                        _round_coord(origin["lat"]),  _round_coord(origin["lng"]),
                        _round_coord(destination["lat"]), _round_coord(destination["lng"]),
                        fslot, tt, dk, dep_dt,
                    )
                return None

            fetched = succeeded = 0
            with ThreadPoolExecutor(max_workers=_TRAFFIC_FETCH_POOL_SIZE) as pool:
                future_list = [pool.submit(_do_fetch, item) for item in work]
                for future in as_completed(future_list):
                    fetched += 1
                    result = future.result()
                    if result:
                        batch.append(result)
                        succeeded += 1
                    if len(batch) >= 50:
                        _upsert_traffic_rows(batch)
                        batch.clear()
                    if fetched % 200 == 0:
                        logger.info(f"Traffic cache …{fetched}/{len(work)} fetched, {succeeded} succeeded")
            if batch:
                _upsert_traffic_rows(batch)
            logger.info(f"Traffic cache prefetch complete: {succeeded}/{len(work)} stored")
        finally:
            _prefetch_lock.release()

    threading.Thread(target=_run, daemon=True).start()


def get_historical_time_mat(locations, departure_min, pairs):
    if not DATABASE_URL:
        return None, 0.0

    n = len(locations)
    hist_mat = np.zeros((n, n), dtype=np.float64)

    base_slot   = (int(departure_min) // _TRAFFIC_SLOT_MINUTES) * _TRAFFIC_SLOT_MINUTES
    slot_window = [
        base_slot,
        (base_slot - _TRAFFIC_SLOT_MINUTES) % (24 * 60),
        (base_slot + _TRAFFIC_SLOT_MINUTES) % (24 * 60),
    ]

    pair_list = list(pairs)
    if not pair_list:
        return hist_mat, 0.0

    olats = [_round_coord(locations[i]["lat"]) for i, j in pair_list]
    olngs = [_round_coord(locations[i]["lng"]) for i, j in pair_list]
    dlats = [_round_coord(locations[j]["lat"]) for i, j in pair_list]
    dlngs = [_round_coord(locations[j]["lng"]) for i, j in pair_list]
    ii    = [i for i, j in pair_list]
    jj    = [j for i, j in pair_list]

    hit = miss = 0
    try:
        conn = _get_db_conn()
        cur  = conn.cursor()
        cur.execute("""
            SELECT p.i, p.j, AVG(c.travel_time_min)
            FROM (
                SELECT
                    unnest(%s::float8[]) AS olat,
                    unnest(%s::float8[]) AS olng,
                    unnest(%s::float8[]) AS dlat,
                    unnest(%s::float8[]) AS dlng,
                    unnest(%s::int[])    AS i,
                    unnest(%s::int[])    AS j
            ) p
            JOIN grps_traffic_cache c
              ON  c.orig_lat     = p.olat
              AND c.orig_lng     = p.olng
              AND c.dest_lat     = p.dlat
              AND c.dest_lng     = p.dlng
              AND c.slot_minutes = ANY(%s)
            GROUP BY p.i, p.j
        """, (olats, olngs, dlats, dlngs, ii, jj, slot_window))

        for row in cur.fetchall():
            ri, rj, avg_t = row
            if avg_t is not None:
                hist_mat[ri][rj] = float(avg_t)
                hit += 1

        miss = len(pair_list) - hit
        conn.close()
    except Exception as exc:
        logger.error(f"Traffic cache read failed: {exc}")
        return None, 0.0

    total    = hit + miss
    coverage = hit / total if total > 0 else 0.0
    logger.debug(f"Historical lookup: {hit}/{total} pairs covered (slot window {sorted(slot_window)})")
    return hist_mat, coverage


# ─────────────────────────── AUTH (unchanged) ────────────────────────────────
USERS = {
    os.environ.get("APP_USER", "admin"):      os.environ.get("APP_PASS", "grps2024"),
    os.environ.get("APP_USER2", "dispatcher"): os.environ.get("APP_PASS2", "route123"),
}

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        if USERS.get(u) == p:
            session["user"] = u
            return redirect(url_for("index"))
        error = "Invalid credentials"
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def index():
    return render_template("index.html", user=session["user"])


# --- Debug endpoints (unchanged) ----------------------------------------------
@app.route("/api/here_debug")
def here_debug():
    if not HERE_API_KEY:
        return jsonify({"error": "HERE_API_KEY not set"})
    payload = {
        "origins":          [{"lat": 44.8178, "lng": 20.4569}],
        "destinations":     [{"lat": 44.8125, "lng": 20.4612}],
        "routingMode":      "fast",
        "transportMode":    "car",
        "matrixAttributes": ["travelTimes", "distances"],
        "regionDefinition": {
            "type":  "boundingBox",
            "north": 44.83,
            "south": 44.80,
            "east":  20.47,
            "west":  20.45,
        },
    }
    try:
        resp = requests.post(
            "https://matrix.router.hereapi.com/v8/matrix",
            json=payload,
            params={"apiKey": HERE_API_KEY, "departureTime": _here_departure_time()},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        return jsonify({
            "status_code": resp.status_code,
            "response":    resp.json() if resp.headers.get("content-type","").startswith("application/json") else resp.text[:500],
            "key_prefix":  HERE_API_KEY[:6] + "..." if HERE_API_KEY else None,
        })
    except Exception as e:
        return jsonify({"exception": str(e)})


@app.route("/api/status")
def status():
    import time as _time
    result = {
        "here_key_set":   bool(HERE_API_KEY),
        "here_reachable": False,
        "osrm_reachable": False,
        "routing_source": "haversine",
        "details":        {},
    }
    if HERE_API_KEY:
        try:
            t0 = _time.time()
            test_locs = [
                {"lat": 44.8178, "lng": 20.4569},
                {"lat": 44.8125, "lng": 20.4612},
            ]
            d, t = fetch_here_matrix(test_locs)
            elapsed = round(_time.time() - t0, 2)
            if d is not None:
                result["here_reachable"] = True
                result["routing_source"] = "here"
                result["details"]["here"] = {
                    "status": "ok", "response_sec": elapsed,
                    "sample_dist_km": round(d[0][1], 3),
                    "sample_time_min": round(t[0][1], 2),
                }
            else:
                result["details"]["here"] = {"status": "error — matrix returned None"}
        except Exception as e:
            result["details"]["here"] = {"status": f"exception: {e}"}
    try:
        t0 = _time.time()
        test_locs = [
            {"lat": 44.8178, "lng": 20.4569},
            {"lat": 44.8125, "lng": 20.4612},
        ]
        d, t = fetch_osrm_matrix(test_locs)
        elapsed = round(_time.time() - t0, 2)
        if d is not None:
            result["osrm_reachable"] = True
            if result["routing_source"] == "haversine":
                result["routing_source"] = "osrm"
            result["details"]["osrm"] = {
                "status": "ok", "response_sec": elapsed,
                "sample_dist_km": round(d[0][1], 3),
                "sample_time_min": round(t[0][1], 2),
            }
        else:
            result["details"]["osrm"] = {"status": "unavailable"}
    except Exception as e:
        result["details"]["osrm"] = {"status": f"exception: {e}"}
    result["details"]["haversine"] = {"status": "always available (straight-line fallback)"}
    return jsonify(result)

# ─────────────────────── GEOCODING (unchanged) ───────────────────────────────
@app.route("/api/geocode", methods=["POST"])
@login_required
def geocode():
    data = request.json
    address = data.get("address", "")
    if "serbia" not in address.lower() and "srbija" not in address.lower():
        address = f"{address}, Serbia"
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1, "countrycodes": "rs"},
            headers={"User-Agent": "GRPSWeb/1.0"},
            timeout=8,
        )
        results = resp.json()
        if results:
            return jsonify({"ok": True, "lat": float(results[0]["lat"]),
                            "lng": float(results[0]["lon"]),
                            "display": results[0].get("display_name", "")})
        return jsonify({"ok": False, "error": "Address not found"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

# ─────────────────────── EXCEL IMPORT (unchanged) ────────────────────────────
@app.route("/api/import_excel", methods=["POST"])
@login_required
def import_excel():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file"})
    f = request.files["file"]
    fname = secure_filename(f.filename)
    path = os.path.join(UPLOAD_FOLDER, fname)
    f.save(path)
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        header = next(rows_iter, None)
        if not header:
            return jsonify({"ok": False, "error": "Empty workbook"})
        hmap = {str(c).strip().lower(): i for i, c in enumerate(header) if c}
        required = {"customer", "address", "time"}
        missing = required - set(hmap.keys())
        if missing:
            return jsonify({"ok": False, "error": f"Missing columns: {missing}"})
        pkg_cols = [k for k in ["packages#1", "packages#2", "packages#3"] if k in hmap]
        if not pkg_cols:
            if "packages" in hmap:
                pkg_cols = ["packages"]
            else:
                return jsonify({"ok": False, "error": "Missing columns: Packages#1 / Packages#2 / Packages#3"})

        import re
        LAT_ALIASES = {"lat", "latitude"}
        LNG_ALIASES = {"lng", "lon", "longitude"}
        lat_col = next((k for k in LAT_ALIASES if k in hmap), None)
        lng_col = next((k for k in LNG_ALIASES if k in hmap), None)

        parsed, errors = [], []
        for rn, row in enumerate(rows_iter, 2):
            def g(k):
                v = row[hmap[k]] if hmap[k] < len(row) else None
                return str(v).strip() if v is not None else ""
            name, addr = g("customer"), g("address")
            if not name:
                errors.append(f"Row {rn}: missing customer name")
                continue

            lat = lng = None
            if lat_col and lng_col:
                try:
                    lat_v = g(lat_col)
                    lng_v = g(lng_col)
                    if lat_v and lng_v:
                        lat = float(lat_v)
                        lng = float(lng_v)
                except (ValueError, TypeError):
                    errors.append(f"Row {rn}: invalid lat/lng values — will geocode instead")

            if not addr and lat is None:
                errors.append(f"Row {rn}: missing address (and no lat/lng)")
                continue

            pkg_counts = []
            for k in pkg_cols:
                try:
                    pkg_counts.append(max(0, int(float(g(k) or 0))))
                except Exception:
                    pkg_counts.append(0)
            while len(pkg_counts) < 3:
                pkg_counts.append(0)
            tw = {"start": "09:00", "end": "17:00"}
            raw_t = g("time")
            m = re.match(r"^(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})$", raw_t)
            if m:
                tw = {"start": m.group(1), "end": m.group(2)}
            try:
                unloading = max(1, int(float(g("unloading") or SERVICE_TIME))) if "unloading" in hmap else SERVICE_TIME
            except Exception:
                unloading = SERVICE_TIME
            row_data = {"name": name, "address": addr or "",
                        "pkg_counts": pkg_counts,
                        "unloading_time": unloading,
                        "time_window": tw}
            if lat is not None and lng is not None:
                row_data["lat"] = lat
                row_data["lng"] = lng
            parsed.append(row_data)
        return jsonify({"ok": True, "rows": parsed, "errors": errors})
    except ImportError:
        return jsonify({"ok": False, "error": "openpyxl not installed"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

# ─────────────────────── OSRM MATRIX (unchanged constants) ───────────────────
SERBIA_BBOX = {"lat_min": 41.85, "lat_max": 46.20,
               "lng_min": 18.80, "lng_max": 23.00}

def in_serbia(lat, lng):
    b = SERBIA_BBOX
    return b["lat_min"] <= lat <= b["lat_max"] and b["lng_min"] <= lng <= b["lng_max"]

HERE_API_KEY = os.environ.get("HERE_API_KEY", "")


def _here_departure_time():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


# ── HERE Routing (live traffic) ───────────────────────────────────────────────
def fetch_here_matrix(locations, pairs=None, hav_km=None, sentinel_factor=None,
                      departure_min=None):
    if not HERE_API_KEY:
        return None, None
    sf       = sentinel_factor if sentinel_factor is not None else SENTINEL_FACTOR
    n        = len(locations)
    dist_mat = np.zeros((n, n), dtype=np.float64)
    time_mat = np.zeros((n, n), dtype=np.float64)
    if departure_min is not None:
        today = datetime.utcnow().date()
        dh, dm = divmod(int(departure_min), 60)
        dep_time = datetime(today.year, today.month, today.day,
                            dh % 24, dm % 60).strftime("%Y-%m-%dT%H:%M:%SZ")
        logger.debug(f"HERE matrix using planned departure time {dep_time}")
    else:
        dep_time = _here_departure_time()

    if pairs is not None and hav_km is not None:
        skip_mask = np.ones((n, n), dtype=bool)
        np.fill_diagonal(skip_mask, False)
        for i, j in pairs:
            skip_mask[i, j] = False
        sentinel_d = hav_km * sf
        dist_mat[skip_mask] = sentinel_d[skip_mask]
        time_mat[skip_mask] = sentinel_d[skip_mask] / 30.0 * 60.0

    fetch_set = pairs if pairs is not None else {(i, j) for i in range(n) for j in range(n) if i != j}

    MAX_HERE_WORKERS    = 4
    HERE_FAIL_THRESHOLD = 0.20
    wall_budget         = 90.0 if len(fetch_set) > 50 else 45.0
    wall_deadline       = time.time() + wall_budget

    abort_flag = threading.Event()

    def _fetch_pair(i, j):
        if abort_flag.is_set():
            return None
        params = {
            "apiKey":        HERE_API_KEY,
            "transportMode": "car",
            "routingMode":   "fast",
            "departureTime": dep_time,
            "origin":        f"{locations[i]['lat']},{locations[i]['lng']}",
            "destination":   f"{locations[j]['lat']},{locations[j]['lng']}",
            "return":        "summary",
        }
        try:
            resp = requests.get("https://router.hereapi.com/v8/routes",
                                params=params, timeout=(3, 6))
            if resp.status_code == 200:
                routes = resp.json().get("routes", [])
                if routes:
                    s = routes[0]["sections"][0]["summary"]
                    return (i, j, s["length"] / 1000.0, s["duration"] / 60.0)
            logger.debug(f"HERE matrix ({i},{j}) failed: {resp.status_code}")
        except Exception as e:
            logger.debug(f"HERE matrix ({i},{j}) exception: {e}")
        return None

    api_calls = failures = 0
    timed_out = False
    with ThreadPoolExecutor(max_workers=MAX_HERE_WORKERS) as pool:
        futures = {pool.submit(_fetch_pair, i, j): (i, j) for (i, j) in fetch_set}
        n_pairs = len(futures)
        for future in as_completed(futures):
            if time.time() > wall_deadline:
                timed_out = True
                abort_flag.set()
                logger.warning(f"HERE matrix deadline exceeded after {api_calls} successes / {failures} failures — falling back to OSRM")
                pool.shutdown(wait=False, cancel_futures=True)
                return None, None

            result = future.result()
            if result is None:
                failures += 1
                if failures > n_pairs * HERE_FAIL_THRESHOLD:
                    abort_flag.set()
                    logger.warning(f"HERE matrix failure threshold exceeded ({failures}/{n_pairs}) — falling back to OSRM")
                    pool.shutdown(wait=False, cancel_futures=True)
                    return None, None
            else:
                i, j, dist, time_val = result
                dist_mat[i][j] = dist
                time_mat[i][j] = time_val
                api_calls += 1

    skipped = n * (n - 1) - api_calls
    logger.info(f"HERE matrix: {n}×{n} built with live traffic ({api_calls} API calls, {failures} failed→sentinel, {skipped} skipped)")
    return dist_mat, time_mat


def _decode_here_polyline(encoded):
    TABLE = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    dec   = {c: i for i, c in enumerate(TABLE)}

    def _uint(s, i):
        r, sh = 0, 0
        while True:
            v = dec[s[i]]; i += 1
            r |= (v & 0x1F) << sh; sh += 5
            if v < 0x20: break
        return r, i

    def _sint(s, i):
        r, i = _uint(s, i)
        return (~r >> 1) if (r & 1) else (r >> 1), i

    idx = 0
    _, idx    = _uint(encoded, idx)
    hdr, idx  = _uint(encoded, idx)
    factor    = 10 ** (hdr & 0xF)
    third_dim = (hdr >> 4) & 0x7

    coords, lat, lng = [], 0, 0
    while idx < len(encoded):
        dlat, idx = _sint(encoded, idx)
        dlng, idx = _sint(encoded, idx)
        if third_dim:
            _, idx = _sint(encoded, idx)
        lat += dlat; lng += dlng
        coords.append((lat / factor, lng / factor))
    return coords


_HERE_MAX_VIA = 10

def _here_route_leg(origin_wp, dest_wp, via_wps):
    origin   = f"{origin_wp[1]},{origin_wp[0]}"
    dest_str = f"{dest_wp[1]},{dest_wp[0]}"
    via_list = [f"{lat},{lng}" for lng, lat in via_wps]
    params   = {
        "apiKey":        HERE_API_KEY,
        "transportMode": "car",
        "routingMode":   "fast",
        "departureTime": _here_departure_time(),
        "origin":        origin,
        "destination":   dest_str,
        "return":        "polyline,summary",
    }
    if via_list:
        params["via"] = via_list
    try:
        resp = requests.get("https://router.hereapi.com/v8/routes",
                            params=params, timeout=(5, 20))
        if resp.status_code != 200:
            return None, None, None
        routes = resp.json().get("routes", [])
        if not routes:
            return None, None, None
        geom, dist_km, dur_min = [], 0.0, 0.0
        for section in routes[0]["sections"]:
            summary  = section.get("summary", {})
            dist_km += summary.get("length",   0) / 1000.0
            dur_min += summary.get("duration", 0) / 60.0
            raw_poly = section.get("polyline")
            if not raw_poly:
                continue
            pts   = _decode_here_polyline(raw_poly)
            pts   = pts[1:] if geom else pts
            geom += [(p[1], p[0]) for p in pts]
        return geom, dist_km, dur_min
    except Exception:
        return None, None, None


def fetch_here_route(waypoints):
    if not HERE_API_KEY:
        return None, None, None

    chunk_size = _HERE_MAX_VIA + 2
    chunks = []
    i = 0
    while i < len(waypoints) - 1:
        end = min(i + chunk_size, len(waypoints))
        chunks.append(waypoints[i:end])
        i = end - 1

    geom_all, dist_km_all, dur_min_all = [], 0.0, 0.0
    for chunk in chunks:
        g, d, t = _here_route_leg(chunk[0], chunk[-1], chunk[1:-1])
        if g is None:
            logger.debug("HERE route leg failed, falling back to OSRM")
            return None, None, None
        geom_all  += g[1:] if geom_all else g
        dist_km_all  += d or 0.0
        dur_min_all  += t or 0.0

    if not geom_all:
        return None, None, None

    logger.debug(f"HERE route OK {len(geom_all)} pts {dist_km_all:.1f}km {dur_min_all:.1f}min ({len(chunks)} chunks)")
    return geom_all, dist_km_all, dur_min_all


# ── OSRM Routing (fallback) ──────────────────────────────────────────────────
def fetch_osrm_matrix(locations, pairs=None, hav_km=None, sentinel_factor=None):
    sf = sentinel_factor if sentinel_factor is not None else SENTINEL_FACTOR
    n = len(locations)

    if pairs is not None:
        needed_idx = sorted({i for p in pairs for i in p})
    else:
        needed_idx = list(range(n))

    sub_locs = [locations[i] for i in needed_idx]
    idx_map  = {orig: sub for sub, orig in enumerate(needed_idx)}

    coords = ";".join(f"{loc['lng']},{loc['lat']}" for loc in sub_locs)
    url    = f"https://router.project-osrm.org/table/v1/driving/{coords}"
    delays = [2, 5, 10, 15]

    dist_mat = np.zeros((n, n), dtype=np.float64)
    time_mat = np.zeros((n, n), dtype=np.float64)

    if pairs is not None and hav_km is not None:
        skip_mask = np.ones((n, n), dtype=bool)
        np.fill_diagonal(skip_mask, False)
        for i, j in pairs:
            skip_mask[i, j] = False
        sentinel_d = hav_km * sf
        dist_mat[skip_mask] = sentinel_d[skip_mask]
        time_mat[skip_mask] = sentinel_d[skip_mask] / 30.0 * 60.0

    for attempt in range(4):
        try:
            resp = requests.get(url, params={"annotations": "distance,duration"},
                                headers={"User-Agent": "GRPSWeb/1.0"}, timeout=15)
            if resp.status_code in (429, 500, 503):
                time.sleep(delays[attempt]); continue
            if resp.status_code != 200:
                time.sleep(delays[attempt]); continue
            data = resp.json()
            if data.get("code") != "Ok":
                time.sleep(delays[attempt]); continue

            for si, i in enumerate(needed_idx):
                for sj, j in enumerate(needed_idx):
                    if i == j:
                        continue
                    d = data["distances"][si][sj]
                    t = data["durations"][si][sj]
                    dist_mat[i][j] = (d / 1000.0) if d else 0.0
                    time_mat[i][j] = (t / 60.0)   if t else 0.0

            skipped = n * (n - 1) - len(needed_idx) * (len(needed_idx) - 1)
            logger.info(f"OSRM matrix: {n}×{n} (fetched {len(needed_idx)} locs, {skipped} sentinel-filled)")
            return dist_mat, time_mat
        except Exception:
            time.sleep(delays[attempt])
    return None, None


def haversine(lat1, lon1, lat2, lon2):
    R    = 6371
    la1, la2 = math.radians(lat1), math.radians(lat2)
    a    = (math.sin((la2-la1)/2)**2
            + math.cos(la1)*math.cos(la2)*math.sin(math.radians(lon2-lon1)/2)**2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


# ── Spatial pre-filtering ─────────────────────────────────────────────────────
K_NEAREST       = 12
SENTINEL_FACTOR = 4.5


def _haversine_matrix_km(locations):
    n    = len(locations)
    lats = np.radians([loc["lat"] for loc in locations])
    lngs = np.radians([loc["lng"] for loc in locations])
    mat  = np.zeros((n, n))
    for i in range(n):
        dlat = lats - lats[i]
        dlng = lngs - lngs[i]
        a    = np.sin(dlat / 2)**2 + np.cos(lats[i]) * np.cos(lats) * np.sin(dlng / 2)**2
        mat[i] = 6371.0 * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return mat


def build_api_pairs(locations, k=K_NEAREST):
    n      = len(locations)
    hav_km = _haversine_matrix_km(locations)

    if n <= k + 1:
        pairs = {(i, j) for i in range(n) for j in range(n) if i != j}
        return hav_km, pairs

    pairs = set()
    for i in range(n):
        row      = hav_km[i].copy()
        row[i]   = np.inf
        nearest  = np.argpartition(row, k)[:k]
        for j in nearest:
            pairs.add((i, int(j)))
            pairs.add((int(j), i))

    logger.debug(f"Spatial filter: {n} locations → {len(pairs)} API pairs (skipped {n*(n-1) - len(pairs)} pairs, k={k})")
    return hav_km, pairs


def build_haversine_matrix(locations):
    hav_km   = _haversine_matrix_km(locations)
    time_mat = hav_km / 30.0 * 60.0
    return hav_km.copy(), time_mat


def straight_line_geometry(waypoints):
    geom = [(lng, lat) for lng, lat in waypoints]
    dist = sum(haversine(waypoints[i][1], waypoints[i][0],
                         waypoints[i+1][1], waypoints[i+1][0])
               for i in range(len(waypoints)-1))
    return geom, dist, dist / 30 * 60


def fetch_osrm_route(waypoints):
    coord_str = ";".join(f"{lng},{lat}" for lng, lat in waypoints)
    url       = f"https://router.project-osrm.org/route/v1/driving/{coord_str}"
    delays    = [2, 5, 10, 15]
    for attempt in range(4):
        try:
            resp = requests.get(url,
                params={"overview": "full", "geometries": "geojson",
                        "steps": "false", "alternatives": "false"},
                headers={"User-Agent": "GRPSWeb/1.0"}, timeout=15)
            if resp.status_code in (429, 500, 503):
                time.sleep(delays[attempt]); continue
            if resp.status_code != 200:
                time.sleep(delays[attempt]); continue
            data = resp.json()
            if data.get("code") == "Ok" and data.get("routes"):
                r    = data["routes"][0]
                geom = [(c[0], c[1]) for c in r["geometry"]["coordinates"]]
                return geom, r["distance"]/1000.0, r["duration"]/60.0
        except Exception:
            time.sleep(delays[attempt])
    return straight_line_geometry(waypoints)


def fetch_best_matrix(locations, k_nearest=None, sentinel_factor=None,
                      departure_min=None, hist_blend_weight=None):
    _DEFAULT_HIST_BLEND_WEIGHT = 0.5
    blend_w = hist_blend_weight if hist_blend_weight is not None else _DEFAULT_HIST_BLEND_WEIGHT

    k  = k_nearest      if k_nearest      is not None else K_NEAREST
    sf = sentinel_factor if sentinel_factor is not None else SENTINEL_FACTOR

    hav_km, pairs = build_api_pairs(locations, k=k)

    if HERE_API_KEY:
        d, t = fetch_here_matrix(locations, pairs=pairs, hav_km=hav_km,
                                  sentinel_factor=sf, departure_min=departure_min)
        if d is not None:
            t = _blend_historical(t, locations, departure_min, pairs, blend_w)
            return d, t, "here"
    d, t = fetch_osrm_matrix(locations, pairs=pairs, hav_km=hav_km, sentinel_factor=sf)
    if d is not None:
        t = _blend_historical(t, locations, departure_min, pairs, blend_w)
        return d, t, "osrm"
    d, t = build_haversine_matrix(locations)
    return d, t, "haversine"


def _blend_historical(live_time_mat, locations, departure_min, pairs, weight):
    if departure_min is None or not DATABASE_URL:
        return live_time_mat

    hist_mat, coverage = get_historical_time_mat(locations, departure_min, pairs)
    if hist_mat is None or coverage == 0.0:
        return live_time_mat

    hist_np = np.asarray(hist_mat, dtype=np.float64)
    if pairs:
        rows = np.array([i for i, j in pairs], dtype=np.intp)
        cols = np.array([j for i, j in pairs], dtype=np.intp)
        has_hist = hist_np[rows, cols] > 0
        r, c = rows[has_hist], cols[has_hist]
        blended = live_time_mat.copy()
        blended[r, c] = (1.0 - weight) * live_time_mat[r, c] + weight * hist_np[r, c]
        blended_count = int(has_hist.sum())
    else:
        blended = live_time_mat
        blended_count = 0

    logger.debug(f"Traffic blend: {blended_count}/{len(pairs)} pairs (coverage={coverage:.1%}, weight={weight})")
    return blended


def fetch_best_route(waypoints):
    if HERE_API_KEY:
        g, d, t = fetch_here_route(waypoints)
        if g:
            return g, d, t, "here"
    g, d, t = fetch_osrm_route(waypoints)
    sl_g, sl_d, sl_t = straight_line_geometry(waypoints)
    src = "haversine" if (g == sl_g) else "osrm"
    return g, d, t, src


# ─────────────────────── VRPTW CORE (unchanged except logging) ─────────────────
SERVICE_TIME = 10
DRIVER_WAGE_RSD_PER_HOUR = 900.0
FUEL_PRICE_RSD_PER_LITRE = 200.0
DEFAULT_PKG_WEIGHTS_KG = [5.0, 15.0, 30.0]
FUEL_LOAD_FACTOR_PER_1000KG = 0.03


def _mat_idx(cust_i, n_depots):
    return n_depots + cust_i


def route_time(route_mat_indices, depot_mat_idx, dist_mat, time_mat, tw, svc,
               start_time=None, svc_map=None, no_wait=False):
    sched, feasible = [], True
    t    = start_time if start_time is not None else tw[depot_mat_idx][0]
    prev = depot_mat_idx
    for c in route_mat_indices:
        t += time_mat[prev][c]
        tw_s, tw_e = tw[c]
        viol  = max(0.0, t - tw_e)
        if viol > 0:
            feasible = False
        if no_wait:
            wait = 0.0
        else:
            wait = max(0.0, tw_s - t)
        arrival    = t
        stop_svc   = svc_map[c] if (svc_map and c in svc_map) else svc
        t          = (t if no_wait else max(t, tw_s)) + stop_svc
        sched.append({"customer_mat": c, "arrival": arrival,
                       "wait": wait, "violation": viol, "depart": t,
                       "service_time": stop_svc})
        prev = c
    return feasible, sched


def latest_feasible_departure(route_mat_indices, depot_mat_idx,
                               dist_mat, time_mat, tw, svc, svc_map=None,
                               no_wait=False):
    if not route_mat_indices:
        return tw[depot_mat_idx][0]
    depot_open  = tw[depot_mat_idx][0]
    depot_close = tw[depot_mat_idx][1]
    ok, _ = route_time(route_mat_indices, depot_mat_idx, dist_mat, time_mat,
                        tw, svc, depot_open, svc_map, no_wait=no_wait)
    if not ok:
        return depot_open
    best = depot_open
    lo, hi = depot_open, depot_close
    while hi - lo > 5:
        mid = (lo + hi) // 2
        ok, _ = route_time(route_mat_indices, depot_mat_idx, dist_mat, time_mat,
                            tw, svc, mid, svc_map, no_wait=no_wait)
        if ok:
            best = mid
            lo   = mid
        else:
            hi   = mid
    return best


def route_working_minutes(route_mat_indices, depot_mat_idx,
                           dist_mat, time_mat, tw, svc, start_time, svc_map=None,
                           no_wait=False):
    if not route_mat_indices:
        return 0.0
    _, sched = route_time(route_mat_indices, depot_mat_idx, dist_mat, time_mat,
                           tw, svc, start_time, svc_map, no_wait=no_wait)
    last_depart = sched[-1]["depart"] if sched else start_time
    return_time = last_depart + time_mat[route_mat_indices[-1]][depot_mat_idx]
    return max(0.0, return_time - start_time)


def route_dist(route_mat_indices, depot_mat_idx, dist_mat):
    if not route_mat_indices:
        return 0.0
    d    = dist_mat[depot_mat_idx][route_mat_indices[0]]
    prev = route_mat_indices[0]
    for c in route_mat_indices[1:]:
        d   += dist_mat[prev][c]
        prev = c
    d += dist_mat[prev][depot_mat_idx]
    return d


def route_fuel_litres(route_mat_indices, depot_mat_idx, dist_mat,
                      demands_kg, n_depots, fuel_per_100km_fn):
    if not route_mat_indices:
        return 0.0
    remaining_kg = sum(
        demands_kg[c - n_depots]
        for c in route_mat_indices
        if 0 <= (c - n_depots) < len(demands_kg)
    )
    total_litres = 0.0
    leg_km = dist_mat[depot_mat_idx][route_mat_indices[0]]
    total_litres += leg_km * fuel_per_100km_fn(remaining_kg) / 100.0
    prev = route_mat_indices[0]
    drop = demands_kg[prev - n_depots] if 0 <= (prev - n_depots) < len(demands_kg) else 0.0
    remaining_kg = max(0.0, remaining_kg - drop)
    for c in route_mat_indices[1:]:
        leg_km = dist_mat[prev][c]
        total_litres += leg_km * fuel_per_100km_fn(remaining_kg) / 100.0
        drop = demands_kg[c - n_depots] if 0 <= (c - n_depots) < len(demands_kg) else 0.0
        remaining_kg = max(0.0, remaining_kg - drop)
        prev = c
    leg_km = dist_mat[prev][depot_mat_idx]
    total_litres += leg_km * fuel_per_100km_fn(remaining_kg) / 100.0
    return total_litres


OVERLAP_THRESHOLD_KM = 3.0
OVERLAP_WEIGHT_RSD   = 500.0


def route_overlap_penalty(routes, dist_mat, depot_of,
                          threshold_km=None, weight_rsd=None):
    if weight_rsd is None:
        weight_rsd = OVERLAP_WEIGHT_RSD
    active = [(v, r) for v, r in enumerate(routes) if r]
    if len(active) < 2:
        return 0.0

    def route_edges(v, route):
        d = depot_of[v]
        full = [d] + list(route) + [d]
        edges = set()
        for k in range(len(full) - 1):
            edges.add(frozenset((full[k], full[k + 1])))
        return full, edges

    penalty = 0.0
    edge_cache = {v: route_edges(v, r) for v, r in active}
    for idx_a in range(len(active)):
        v_a, route_a = active[idx_a]
        full_a, edges_a = edge_cache[v_a]
        for idx_b in range(idx_a + 1, len(active)):
            v_b, route_b = active[idx_b]
            full_b, edges_b = edge_cache[v_b]
            shared = edges_a & edges_b
            for edge in shared:
                i, j = tuple(edge)
                shared_km = (dist_mat[i][j] + dist_mat[j][i]) / 2.0
                penalty += shared_km * weight_rsd
    return penalty


def best_depot_for_route(route_mat_indices, n_depots, dist_mat):
    if n_depots == 1 or not route_mat_indices:
        return 0
    best_d, best_cost = 0, float("inf")
    for d in range(n_depots):
        cost = dist_mat[d][route_mat_indices[0]] + dist_mat[route_mat_indices[-1]][d]
        if cost < best_cost:
            best_cost = cost
            best_d    = d
    return best_d


class VRPState:
    def __init__(self, routes, depot_of, dist_mat, time_mat,
                 demands, fleet, tw, n_depots, svc=SERVICE_TIME,
                 use_tw=False, svc_map=None, demands_kg=None, obj_weights=None,
                 use_volume_cap=True, use_weight_cap=True,
                 fuel_price_rsd_l=None, driver_wage_rsd_h=None,
                 fuel_load_factor=None,
                 overlap_threshold_km=None, overlap_weight_rsd=None,
                 dist_rsd_per_km=None, tw_penalty_rsd=None,
                 no_wait=False):
        self.routes     = routes
        self.depot_of   = depot_of
        self.dist_mat   = dist_mat
        self.time_mat   = time_mat
        self.demands    = demands
        self.demands_kg = demands_kg or [0.0] * len(demands)
        self.fleet      = fleet
        self.tw         = tw
        self.n_depots   = n_depots
        self.svc        = svc
        self.use_tw     = use_tw
        self.no_wait    = no_wait
        self.svc_map    = svc_map or {}
        self.obj_weights = obj_weights or {"fuel": False, "wages": False, "distance": False, "vehicles": False}
        self.use_volume_cap = use_volume_cap
        self.use_weight_cap = use_weight_cap
        self.fuel_price_rsd_l  = fuel_price_rsd_l  if fuel_price_rsd_l  is not None else FUEL_PRICE_RSD_PER_LITRE
        self.driver_wage_rsd_h = driver_wage_rsd_h if driver_wage_rsd_h is not None else DRIVER_WAGE_RSD_PER_HOUR
        self.fuel_load_factor  = fuel_load_factor  if fuel_load_factor  is not None else FUEL_LOAD_FACTOR_PER_1000KG
        self.overlap_threshold_km = overlap_threshold_km if overlap_threshold_km is not None else OVERLAP_THRESHOLD_KM
        self.overlap_weight_rsd   = overlap_weight_rsd   if overlap_weight_rsd   is not None else OVERLAP_WEIGHT_RSD
        self.dist_rsd_per_km      = dist_rsd_per_km      if dist_rsd_per_km      is not None else 20.0
        self.tw_penalty_rsd       = tw_penalty_rsd       if tw_penalty_rsd       is not None else 100.0

    def fuel_per_100km(self, v, payload_kg=0.0):
        if v < len(self.fleet):
            base = float(self.fleet[v].get("fuel_consumption", 10.0))
        else:
            base = 10.0
        surcharge = 1.0 + self.fuel_load_factor * payload_kg / 1000.0
        return base * surcharge

    def weight_cap(self, v):
        if v < len(self.fleet):
            return float(self.fleet[v].get("weight_capacity", 0.0))
        return 0.0

    def route_weight(self, v):
        return self.weight_load(v)

    def copy(self):
        return VRPState(
            copy.deepcopy(self.routes),
            self.depot_of[:],
            self.dist_mat, self.time_mat,
            self.demands, self.fleet, self.tw,
            self.n_depots, self.svc, self.use_tw, self.svc_map, self.demands_kg,
            self.obj_weights,
            self.use_volume_cap, self.use_weight_cap,
            self.fuel_price_rsd_l, self.driver_wage_rsd_h,
            self.fuel_load_factor,
            self.overlap_threshold_km, self.overlap_weight_rsd,
            self.dist_rsd_per_km, self.tw_penalty_rsd,
            self.no_wait)

    def cap(self, v):
        return self.fleet[v]["capacity"] if v < len(self.fleet) else float("inf")

    def load(self, v):
        return sum(self.demands[c - self.n_depots]
                   for c in self.routes[v]
                   if 0 <= (c - self.n_depots) < len(self.demands))

    def weight_load(self, v):
        return sum(self.demands_kg[c - self.n_depots]
                   for c in self.routes[v]
                   if 0 <= (c - self.n_depots) < len(self.demands_kg))

    def reassign_depots(self):
        for v, route in enumerate(self.routes):
            if route:
                self.depot_of[v] = best_depot_for_route(
                    route, self.n_depots, self.dist_mat)

    def objective(self):
        ow          = self.obj_weights or {}
        do_fuel     = ow.get("fuel",     False)
        do_wages    = ow.get("wages",    False)
        do_dist     = ow.get("distance", False)
        do_vehicles = ow.get("vehicles", False)
        do_overlap  = ow.get("overlap",  False)
        if not any([do_fuel, do_wages, do_dist, do_vehicles, do_overlap]):
            do_fuel = do_wages = True

        DIST_RSD_PER_KM = self.dist_rsd_per_km
        VEHICLE_PENALTY_RSD = 1_000_000.0 if do_vehicles else 3600.0
        TW_PENALTY = self.tw_penalty_rsd
        total = 0.0
        for v, route in enumerate(self.routes):
            if not route:
                continue
            if self.use_volume_cap and self.load(v) > self.cap(v):
                return float("inf")
            wc = self.weight_cap(v)
            if self.use_weight_cap and wc > 0 and self.weight_load(v) > wc:
                return float("inf")
            min_vol_pct = float(self.fleet[v].get("min_vol_pct", 0.0)) if v < len(self.fleet) else 0.0
            min_wt_pct  = float(self.fleet[v].get("min_wt_pct",  0.0)) if v < len(self.fleet) else 0.0
            if min_vol_pct > 0:
                vol_cap = self.cap(v)
                if vol_cap < 9990:
                    vol_fill_pct = 100.0 * self.load(v) / vol_cap if vol_cap > 0 else 100.0
                    if vol_fill_pct < min_vol_pct:
                        return float("inf")
            if min_wt_pct > 0 and wc > 0:
                wt_fill_pct = 100.0 * self.weight_load(v) / wc if wc > 0 else 100.0
                if wt_fill_pct < min_wt_pct:
                    return float("inf")
            depot = self.depot_of[v]
            start = latest_feasible_departure(
                route, depot, self.dist_mat, self.time_mat, self.tw, self.svc,
                self.svc_map, no_wait=self.no_wait)
            _, sched = route_time(route, depot, self.dist_mat, self.time_mat,
                                   self.tw, self.svc, start, self.svc_map,
                                   no_wait=self.no_wait)
            tw_viol = sum(e["violation"] for e in sched)
            if not self.use_tw and tw_viol > 0:
                return float("inf")
            dist_km    = route_dist(route, depot, self.dist_mat)

            if do_fuel:
                fuel_litres = route_fuel_litres(
                    route, depot, self.dist_mat,
                    self.demands_kg, self.n_depots,
                    lambda kg, _v=v: self.fuel_per_100km(_v, kg)
                )
                total += fuel_litres * self.fuel_price_rsd_l
            if do_wages:
                work_mins = route_working_minutes(
                    route, depot, self.dist_mat, self.time_mat, self.tw, self.svc,
                    start, self.svc_map, no_wait=self.no_wait)
                total += (work_mins / 60.0) * self.driver_wage_rsd_h
            if do_dist:
                total += dist_km * DIST_RSD_PER_KM
            if do_vehicles:
                total += VEHICLE_PENALTY_RSD
            if self.use_tw:
                total += tw_viol * TW_PENALTY
        if do_overlap:
            total += route_overlap_penalty(self.routes, self.dist_mat,
                                           self.depot_of,
                                           self.overlap_threshold_km,
                                           self.overlap_weight_rsd)
        return total

    def total_distance(self):
        return sum(route_dist(r, self.depot_of[v], self.dist_mat)
                   for v, r in enumerate(self.routes) if r)

    def total_fuel(self):
        total = 0.0
        for v, r in enumerate(self.routes):
            if not r:
                continue
            total += route_fuel_litres(
                r, self.depot_of[v], self.dist_mat,
                self.demands_kg, self.n_depots,
                lambda kg, _v=v: self.fuel_per_100km(_v, kg)
            )
        return total

    def total_time(self):
        return sum(
            sum(self.time_mat[r[i-1] if i>0 else self.depot_of[v]][r[i]]
                for i in range(len(r)))
            + self.time_mat[r[-1]][self.depot_of[v]]
            for v, r in enumerate(self.routes) if r)


# ─── ALNS operators (improved) ──────────────────────────────────────────────
def _ins_cost(route, pos, c, state, depot,
              _old_start=None, _old_work_mins=None, _old_dist=None):
    ow       = state.obj_weights or {}
    do_wages = ow.get("wages",    False)
    do_dist  = ow.get("distance", False)
    do_fuel  = ow.get("fuel",     False)

    new_route = route[:pos] + [c] + route[pos:]

    if _old_start is None:
        _old_start = latest_feasible_departure(
            route, depot, state.dist_mat, state.time_mat,
            state.tw, state.svc, state.svc_map, no_wait=state.no_wait)
    if _old_work_mins is None:
        _old_work_mins = route_working_minutes(
            route, depot, state.dist_mat, state.time_mat,
            state.tw, state.svc, _old_start, state.svc_map,
            no_wait=state.no_wait) if route else 0.0
    if _old_dist is None:
        _old_dist = route_dist(route, depot, state.dist_mat) if route else 0.0

    prev_node = route[pos - 1] if pos > 0 else depot
    next_node = route[pos]     if pos < len(route) else depot
    dm        = state.dist_mat
    dist_delta = (dm[prev_node][c] + dm[c][next_node]
                  - dm[prev_node][next_node])

    cost = 0.0
    if do_dist:
        cost += dist_delta * state.dist_rsd_per_km
    if do_fuel:
        fuel_per_km = 10.0 / 100.0 * state.fuel_price_rsd_l
        cost += dist_delta * fuel_per_km

    if do_wages or state.use_tw:
        new_start = latest_feasible_departure(
            new_route, depot, state.dist_mat, state.time_mat,
            state.tw, state.svc, state.svc_map, no_wait=state.no_wait)
        new_work_mins = route_working_minutes(
            new_route, depot, state.dist_mat, state.time_mat,
            state.tw, state.svc, new_start, state.svc_map, no_wait=state.no_wait)
        if do_wages:
            cost += ((new_work_mins - _old_work_mins) / 60.0) * state.driver_wage_rsd_h
        if state.use_tw:
            feasible, _ = route_time(
                new_route, depot, state.dist_mat, state.time_mat,
                state.tw, state.svc, new_start, state.svc_map, no_wait=state.no_wait)
            if not feasible:
                return float("inf")
    else:
        if not do_dist and not do_fuel:
            cost = dist_delta
    return cost


def _rand_remove(state, rng):
    s = state.copy()
    minimise_vehicles = (state.obj_weights or {}).get("vehicles", False)
    all_c = [(v, i, c) for v, r in enumerate(s.routes) for i, c in enumerate(r)]
    if not all_c:
        return s
    n_rem = int(rng.integers(1, max(2, len(all_c)//4)))
    if minimise_vehicles:
        weights = []
        for v, i, c in all_c:
            route_size = len(s.routes[v])
            weights.append(1.0 / max(route_size, 1))
        total_w = sum(weights)
        probs = [w / total_w for w in weights]
        chosen_idx = rng.choice(len(all_c),
                                size=min(n_rem, len(all_c)),
                                replace=False, p=probs)
        chosen = [all_c[i] for i in chosen_idx]
    else:
        chosen = [all_c[i] for i in rng.choice(len(all_c),
                                                 size=min(n_rem, len(all_c)),
                                                 replace=False)]
    for v, pos, _ in sorted(chosen, key=lambda x: (x[0], x[1]), reverse=True):
        s.routes[v].pop(pos)
    return s


def _worst_remove(state, rng):
    s = state.copy()
    minimise_vehicles = (state.obj_weights or {}).get("vehicles", False)
    costs = []
    for v, route in enumerate(s.routes):
        d = s.depot_of[v]
        for i, c in enumerate(route):
            prev = route[i-1] if i > 0 else d
            nxt  = route[i+1] if i < len(route)-1 else d
            saving = (s.dist_mat[prev][c] + s.dist_mat[c][nxt]
                      - s.dist_mat[prev][nxt])
            if minimise_vehicles:
                route_size = len(route)
                consolidation_bonus = 1_000_000.0 / max(route_size, 1)
                saving += consolidation_bonus
            costs.append((saving, v, i))
    if not costs:
        return s
    costs.sort(reverse=True)
    n_rem = int(rng.integers(1, max(2, len(costs)//4)))
    for _, v, pos in sorted(costs[:n_rem], key=lambda x: (x[1], x[2]), reverse=True):
        s.routes[v].pop(pos)
    return s


def _tw_remove(state, rng):
    s = state.copy()
    viols = []
    for v, route in enumerate(s.routes):
        d  = s.depot_of[v]
        t  = s.tw[d][0]
        prev = d
        for i, c in enumerate(route):
            t += s.time_mat[prev][c]
            tw_s, tw_e = s.tw[c]
            score = max(0, t - tw_e) + max(0, tw_s - t)
            viols.append((score, v, i))
            stop_svc = s.svc_map.get(c, s.svc)
            t    = max(t, tw_s) + stop_svc
            prev = c
    if not viols:
        return s
    viols.sort(reverse=True)
    n_rem = int(rng.integers(1, max(2, len(viols)//4)))
    for _, v, pos in sorted(viols[:n_rem], key=lambda x: (x[1], x[2]), reverse=True):
        s.routes[v].pop(pos)
    return s


def _cap_remove(state, rng):
    s = state.copy()
    scores = []
    for v, route in enumerate(s.routes):
        excess = s.load(v) - s.cap(v)
        if excess > 0:
            for i, c in enumerate(route):
                dem = s.demands[c - s.n_depots]
                scores.append((dem, v, i))
    if not scores:
        return s
    scores.sort(reverse=True)
    n_rem = int(rng.integers(1, max(2, len(scores) // 4 + 1)))
    for _, v, pos in sorted(scores[:n_rem], key=lambda x: (x[1], x[2]), reverse=True):
        s.routes[v].pop(pos)
    return s


def _overlap_remove(state, rng):
    s = state.copy()
    active_vehicles = [(v, r) for v, r in enumerate(s.routes) if r]
    if len(active_vehicles) < 2:
        return s

    scores = []
    for v, route in enumerate(s.routes):
        if not route:
            continue
        for i, c in enumerate(route):
            score = 0.0
            threshold = s.overlap_threshold_km
            for u, other_route in enumerate(s.routes):
                if u == v or not other_route:
                    continue
                for b in other_route:
                    gap = threshold - s.dist_mat[c][b]
                    if gap > 0:
                        score += gap * gap
            scores.append((score, v, i))

    if not scores:
        return s
    scores.sort(reverse=True)
    n_rem = max(1, int(rng.integers(1, max(2, len(scores) // 4 + 1))))
    for _, v, pos in sorted(scores[:n_rem], key=lambda x: (x[1], x[2]), reverse=True):
        s.routes[v].pop(pos)
    return s


# --- NEW: Shaw removal (correlated customer removal) --------------------------
def _shaw_remove(state, rng):
    """Remove a set of customers that are similar to a randomly chosen seed.
    Similarity is measured by distance, time window overlap, and demand size.
    """
    s = state.copy()
    all_cust = [(v, i, c) for v, r in enumerate(s.routes) for i, c in enumerate(r)]
    if len(all_cust) < 2:
        return s
    seed_idx = rng.integers(len(all_cust))
    seed_v, seed_pos, seed_c = all_cust[seed_idx]

    # collect all customers (id, vehicle, position, demand, tw)
    cust_data = []
    for v, r in enumerate(s.routes):
        for i, c in enumerate(r):
            tw_s, tw_e = state.tw[c]
            cust_data.append({
                "v": v, "i": i, "c": c,
                "demand": state.demands[c - state.n_depots],
                "tw_center": (tw_s + tw_e) / 2.0,
                "lat": state.dist_mat[0][0],  # dummy, but we need location
            })
            # Actually we need coordinates from all_locs; but here in ALNS we don't have all_locs.
            # To avoid passing all_locs through VRPState, we approximate distance using dist_mat.
            # We'll store distance to seed_c using dist_mat.

    # Build relatedness score: higher = more related
    scored = []
    for d in cust_data:
        if d["c"] == seed_c:
            continue
        # distance component (use dist_mat)
        dist = state.dist_mat[seed_c][d["c"]]
        # demand difference
        dem_diff = abs(d["demand"] - cust_data[seed_idx]["demand"]) / max(1.0, cust_data[seed_idx]["demand"])
        # TW difference (minutes)
        tw_diff = abs(d["tw_center"] - cust_data[seed_idx]["tw_center"]) / 480.0  # 8h window
        relatedness = dist / 100.0 + dem_diff * 5.0 + tw_diff * 2.0
        scored.append((relatedness, d["v"], d["i"], d["c"]))

    scored.sort(key=lambda x: x[0])  # most similar first (small relatedness)
    n_rem = max(1, int(rng.integers(1, len(all_cust) // 4 + 2)))
    chosen = scored[:n_rem]
    for _, v, pos, _ in sorted(chosen, key=lambda x: (x[1], x[2]), reverse=True):
        s.routes[v].pop(pos)
    return s


def _greedy_insert(state, rng):
    s = state.copy()
    routed   = {c for r in s.routes for c in r}
    all_cust = {state.n_depots + i for i in range(len(state.demands))}
    unrouted = list(all_cust - routed)
    rng.shuffle(unrouted)
    minimise_vehicles = (state.obj_weights or {}).get("vehicles", False)
    for c in unrouted:
        best_v, best_pos, best_cost = -1, -1, float("inf")
        cust_kg = state.demands_kg[c - state.n_depots] if c - state.n_depots < len(state.demands_kg) else 0.0
        for v in range(len(s.routes)):
            if state.use_volume_cap and s.load(v) + state.demands[c - state.n_depots] > s.cap(v):
                continue
            wc = s.weight_cap(v)
            if state.use_weight_cap and wc > 0 and s.weight_load(v) + cust_kg > wc:
                continue
            d = s.depot_of[v]
            route = s.routes[v]
            old_start = latest_feasible_departure(
                route, d, state.dist_mat, state.time_mat,
                state.tw, state.svc, state.svc_map, no_wait=state.no_wait)
            old_work  = route_working_minutes(
                route, d, state.dist_mat, state.time_mat,
                state.tw, state.svc, old_start, state.svc_map,
                no_wait=state.no_wait) if route else 0.0
            old_dist  = route_dist(route, d, state.dist_mat) if route else 0.0
            for pos in range(len(route) + 1):
                cost = _ins_cost(route, pos, c, state, d,
                                 _old_start=old_start,
                                 _old_work_mins=old_work,
                                 _old_dist=old_dist)
                if minimise_vehicles and not route:
                    cost += 1_000_000.0
                if cost < best_cost:
                    best_cost, best_v, best_pos = cost, v, pos
        if best_v != -1:
            s.routes[best_v].insert(best_pos, c)
    s.reassign_depots()
    return s


def _regret_insert(state, rng):
    s = state.copy()
    routed   = {c for r in s.routes for c in r}
    all_cust = {state.n_depots + i for i in range(len(state.demands))}
    unrouted = list(all_cust - routed)
    minimise_vehicles = (state.obj_weights or {}).get("vehicles", False)
    while unrouted:
        best_c, best_v, best_pos, best_reg = None, -1, -1, -float("inf")
        for c in unrouted:
            dem     = state.demands[c - state.n_depots]
            cust_kg = state.demands_kg[c - state.n_depots] if c - state.n_depots < len(state.demands_kg) else 0.0
            opts = []
            for v in range(len(s.routes)):
                if state.use_volume_cap and s.load(v) + dem > s.cap(v):
                    continue
                wc = s.weight_cap(v)
                if state.use_weight_cap and wc > 0 and s.weight_load(v) + cust_kg > wc:
                    continue
                d = s.depot_of[v]
                route = s.routes[v]
                old_start = latest_feasible_departure(
                    route, d, state.dist_mat, state.time_mat,
                    state.tw, state.svc, state.svc_map, no_wait=state.no_wait)
                old_work  = route_working_minutes(
                    route, d, state.dist_mat, state.time_mat,
                    state.tw, state.svc, old_start, state.svc_map,
                    no_wait=state.no_wait) if route else 0.0
                old_dist  = route_dist(route, d, state.dist_mat) if route else 0.0
                for pos in range(len(route) + 1):
                    cost = _ins_cost(route, pos, c, state, d,
                                     _old_start=old_start,
                                     _old_work_mins=old_work,
                                     _old_dist=old_dist)
                    if cost < float("inf"):
                        if minimise_vehicles and not route:
                            cost += 1_000_000.0
                        opts.append((cost, v, pos))
            if not opts:
                continue
            opts.sort(key=lambda x: x[0])
            reg = (opts[1][0] - opts[0][0]) if len(opts) >= 2 else 0
            if reg > best_reg:
                best_reg = reg
                best_c   = c
                _, best_v, best_pos = opts[0]
        if best_c is None:
            break
        s.routes[best_v].insert(best_pos, best_c)
        unrouted.remove(best_c)
    s.reassign_depots()
    return s


# ─── Helper ─────────────────────────────────────────────────────────────────
def mins_to_hhmm(m):
    t = int(round(m))
    return f"{t//60:02d}:{t%60:02d}"


def clarke_wright_initial_solution(dist_mat, time_mat, demands, depot, cap, n_cust, n_depots):
    """Clarke-Wright savings heuristic (multi-depot not supported; uses a single depot)."""
    # We'll implement a simplified version: all customers start as separate routes.
    routes = [[i] for i in range(n_depots, n_depots + n_cust)]
    loads = [demands[i - n_depots] for i in range(n_depots, n_depots + n_cust)]
    # Compute savings for each pair of customers
    savings = []
    for i in range(len(routes)):
        for j in range(i+1, len(routes)):
            ci = routes[i][0]
            cj = routes[j][0]
            save = (dist_mat[depot][ci] + dist_mat[depot][cj] - dist_mat[ci][cj])
            savings.append((save, i, j))
    savings.sort(reverse=True, key=lambda x: x[0])
    # Merge routes if capacity allows
    for save, i, j in savings:
        if loads[i] + loads[j] <= cap:
            # Merge route j into i
            routes[i].extend(routes[j])
            loads[i] += loads[j]
            routes[j] = []
            loads[j] = 0
    # Filter out empty routes
    routes = [r for r in routes if r]
    return routes


def optimize_nn(dist_mat, time_mat, n_depots, n_cust, tw, demands,
                use_tw=False, svc_map=None, demands_kg=None, obj_weights=None,
                use_volume_cap=True, use_weight_cap=True,
                fuel_price_rsd_l=None, driver_wage_rsd_h=None, fuel_load_factor=None,
                overlap_threshold_km=None, overlap_weight_rsd=None,
                dist_rsd_per_km=None, tw_penalty_rsd=None, no_wait=False):
    depot = 0
    unvis = list(range(n_depots, n_depots + n_cust))
    route, cur = [], depot
    while unvis:
        nn = min(unvis, key=lambda x: dist_mat[cur][x])
        route.append(nn); unvis.remove(nn); cur = nn
    fleet = [{"type": "Vehicle", "capacity": float("inf"), "color": "#3b82f6"}]
    return VRPState([route], [depot], dist_mat, time_mat, demands, fleet, tw, n_depots,
                    use_tw=use_tw, svc_map=svc_map, demands_kg=demands_kg,
                    obj_weights=obj_weights,
                    use_volume_cap=use_volume_cap, use_weight_cap=use_weight_cap,
                    fuel_price_rsd_l=fuel_price_rsd_l, driver_wage_rsd_h=driver_wage_rsd_h,
                    fuel_load_factor=fuel_load_factor,
                    overlap_threshold_km=overlap_threshold_km,
                    overlap_weight_rsd=overlap_weight_rsd,
                    dist_rsd_per_km=dist_rsd_per_km,
                    tw_penalty_rsd=tw_penalty_rsd,
                    no_wait=no_wait)


def optimize_2opt(dist_mat, time_mat, n_depots, n_cust, tw, demands,
                  use_tw=False, svc_map=None, demands_kg=None, obj_weights=None,
                  use_volume_cap=True, use_weight_cap=True,
                  fuel_price_rsd_l=None, driver_wage_rsd_h=None, fuel_load_factor=None,
                  overlap_threshold_km=None, overlap_weight_rsd=None,
                  dist_rsd_per_km=None, tw_penalty_rsd=None, no_wait=False):
    s = optimize_nn(dist_mat, time_mat, n_depots, n_cust, tw, demands,
                    use_tw=use_tw, svc_map=svc_map, demands_kg=demands_kg,
                    obj_weights=obj_weights,
                    use_volume_cap=use_volume_cap, use_weight_cap=use_weight_cap,
                    fuel_price_rsd_l=fuel_price_rsd_l, driver_wage_rsd_h=driver_wage_rsd_h,
                    fuel_load_factor=fuel_load_factor,
                    overlap_threshold_km=overlap_threshold_km,
                    overlap_weight_rsd=overlap_weight_rsd,
                    dist_rsd_per_km=dist_rsd_per_km,
                    tw_penalty_rsd=tw_penalty_rsd,
                    no_wait=no_wait)
    route = s.routes[0][:]
    depot = s.depot_of[0]

    def cost(r):
        return route_dist(r, depot, dist_mat)

    bd = cost(route)
    improved = True
    while improved:
        improved = False
        for i in range(len(route) - 1):
            for j in range(i + 1, len(route)):
                nr = route[:i] + route[i:j+1][::-1] + route[j+1:]
                nd = cost(nr)
                if nd < bd - 1e-9:
                    route, bd, improved = nr, nd, True
                    break
            if improved:
                break
    s.routes[0] = route
    return s


def _alns_optimize(fleet, dist_mat, time_mat, n_depots, n_cust, tw, demands,
                   demands_kg, obj_weights, use_volume_cap, use_weight_cap,
                   fuel_price_rsd_l, driver_wage_rsd_h, fuel_load_factor,
                   temperature, max_iter, svc_map, use_tw,
                   overlap_threshold_km=None, overlap_weight_rsd=None,
                   dist_rsd_per_km=None, tw_penalty_rsd=None, alns_cooling=None,
                   no_wait=False, cancel_event=None):
    """Run a single ALNS optimisation with cancellation support."""
    num_v = len(fleet)
    all_ci = list(range(n_depots, n_depots + n_cust))

    # ── Improved initial solution: Clarke-Wright (if only one depot) ─────────
    if n_depots == 1:
        logger.info("ALNS using Clarke-Wright savings for initial solution")
        cap = max(v.get("capacity", float("inf")) for v in fleet)
        routes_cw = clarke_wright_initial_solution(
            dist_mat, time_mat, demands, 0, cap, n_cust, n_depots
        )
        # map routes to vehicles (assign to first vehicles)
        routes = [[] for _ in range(num_v)]
        for i, r in enumerate(routes_cw):
            if i < num_v:
                routes[i] = r
            else:
                # if more routes than vehicles, assign to existing vehicle with least load
                loads = [sum(demands[c - n_depots] for c in route) for route in routes]
                min_load_idx = loads.index(min(loads))
                routes[min_load_idx].extend(r)
        # Now fill remaining vehicles with empty lists
        for v in range(len(routes_cw), num_v):
            routes[v] = []
    else:
        # original greedy assignment
        routes = [[] for _ in range(num_v)]
        loads = [0.0] * num_v
        wloads = [0.0] * num_v
        current_v = 0
        for ci in all_ci:
            dem = demands[ci - n_depots]
            kg = demands_kg[ci - n_depots] if (ci - n_depots) < len(demands_kg) else 0.0
            def fits(v, dem=dem, kg=kg):
                vol_ok = (not use_volume_cap) or (loads[v] + dem <= fleet[v]["capacity"])
                wc = fleet[v].get("weight_capacity", 0.0)
                weight_ok = (not use_weight_cap) or (wc == 0) or (wloads[v] + kg <= wc)
                return vol_ok and weight_ok
            if not fits(current_v):
                found = False
                for v in range(current_v + 1, num_v):
                    if fits(v):
                        current_v = v
                        found = True
                        break
                if not found:
                    best_v = next((v for v in range(num_v) if fits(v)), current_v)
                    current_v = best_v
            routes[current_v].append(ci)
            loads[current_v] += dem
            wloads[current_v] += kg

    # NN ordering for each vehicle
    ordered = []
    for v, route in enumerate(routes):
        if not route:
            ordered.append([])
            continue
        depot = 0
        unvis, cur, nr = route[:], depot, []
        while unvis:
            nn = min(unvis, key=lambda x: dist_mat[cur][x])
            nr.append(nn)
            unvis.remove(nn)
            cur = nn
        ordered.append(nr)

    # Min‑load consolidation (unchanged)
    for v in range(num_v):
        if not ordered[v]:
            continue
        min_vol_pct = float(fleet[v].get("min_vol_pct", 0.0))
        min_wt_pct = float(fleet[v].get("min_wt_pct", 0.0))
        vol_cap = float(fleet[v].get("capacity", float("inf")))
        wt_cap = float(fleet[v].get("weight_capacity", 0.0))
        load_v = sum(demands[c - n_depots] for c in ordered[v])
        wload_v = sum(demands_kg[c - n_depots] for c in ordered[v]) if demands_kg else 0.0
        vol_ok = (min_vol_pct <= 0 or vol_cap >= 9990 or (load_v / vol_cap * 100.0) >= min_vol_pct)
        wt_ok = (min_wt_pct <= 0 or wt_cap <= 0 or (wload_v / wt_cap * 100.0) >= min_wt_pct)
        if vol_ok and wt_ok:
            continue
        for ci in ordered[v][:]:
            dem = demands[ci - n_depots]
            kg = demands_kg[ci - n_depots] if demands_kg else 0.0
            best_other = None
            best_load = float("inf")
            for u in range(num_v):
                if u == v:
                    continue
                vc = float(fleet[u].get("capacity", float("inf")))
                wcu = float(fleet[u].get("weight_capacity", 0.0))
                vol_fits = (not use_volume_cap) or (loads[u] + dem <= vc)
                wt_fits = (not use_weight_cap) or (wcu == 0) or (wloads[u] + kg <= wcu)
                if vol_fits and wt_fits and loads[u] < best_load:
                    best_load = loads[u]
                    best_other = u
            if best_other is not None:
                ordered[best_other].append(ci)
                loads[best_other] += dem
                wloads[best_other] += kg
                ordered[v].remove(ci)
            else:
                # cannot move, keep
                pass
        # cleanup empty
        if not ordered[v]:
            loads[v] = 0.0
            wloads[v] = 0.0

    depot_of = [0] * num_v
    state = VRPState(ordered, depot_of, dist_mat, time_mat,
                     demands, fleet, tw, n_depots,
                     use_tw=use_tw, svc_map=svc_map, demands_kg=demands_kg,
                     obj_weights=obj_weights,
                     use_volume_cap=use_volume_cap, use_weight_cap=use_weight_cap,
                     fuel_price_rsd_l=fuel_price_rsd_l, driver_wage_rsd_h=driver_wage_rsd_h,
                     fuel_load_factor=fuel_load_factor,
                     overlap_threshold_km=overlap_threshold_km,
                     overlap_weight_rsd=overlap_weight_rsd,
                     dist_rsd_per_km=dist_rsd_per_km,
                     tw_penalty_rsd=tw_penalty_rsd,
                     no_wait=no_wait)
    state.reassign_depots()

    best = state.copy()
    best_obj = best.objective()
    cur_obj = best_obj
    temp = temperature
    cooling = alns_cooling if alns_cooling is not None else 0.995

    # Destroy operators (including new Shaw removal)
    destroy = [_rand_remove, _worst_remove, _tw_remove, _cap_remove, _overlap_remove, _shaw_remove]
    repair = [_greedy_insert, _regret_insert]
    # Adaptive weights
    destroy_weights = [1.0] * len(destroy)
    repair_weights = [1.0] * len(repair)
    destroy_scores = [0.0] * len(destroy)
    repair_scores = [0.0] * len(repair)
    rng = np.random.default_rng(42)

    def sel(weights):
        total = sum(weights)
        r = rng.random() * total
        cum = 0.0
        for i, w in enumerate(weights):
            cum += w
            if cum >= r:
                return i
        return len(weights) - 1

    # Log initial objective
    logger.info(f"ALNS start obj={best_obj:.2f}, temp={temp:.1f}, vehicles_used={sum(1 for r in state.routes if r)}")

    for iteration in range(max_iter):
        # Check cancellation
        if cancel_event and cancel_event.is_set():
            logger.info(f"ALNS cancelled by user at iteration {iteration}")
            raise RuntimeError("Cancelled by user")

        di = sel(destroy_weights)
        ri = sel(repair_weights)

        dest = destroy[di](state, rng)
        cand = repair[ri](dest, rng)
        cand_obj = cand.objective()
        delta = cand_obj - cur_obj

        accepted = False
        if delta < 0 or rng.random() < math.exp(-delta / max(temp, 1e-9)):
            state, cur_obj = cand, cand_obj
            accepted = True
            if cur_obj < best_obj:
                best, best_obj = state.copy(), cur_obj
                accepted = True  # also counts as success

        # Update adaptive weights
        if accepted:
            destroy_scores[di] += 1
            repair_scores[ri] += 1
        else:
            # small decay
            destroy_scores[di] += 0.1
            repair_scores[ri] += 0.1

        # Recompute weights every 20 iterations
        if (iteration + 1) % 20 == 0:
            total_d = sum(destroy_scores) + 1e-9
            total_r = sum(repair_scores) + 1e-9
            destroy_weights = [max(0.1, s / total_d * len(destroy)) for s in destroy_scores]
            repair_weights = [max(0.1, s / total_r * len(repair)) for s in repair_scores]

        temp *= cooling

        if iteration % 50 == 0:
            logger.debug(f"ALNS iter {iteration}: obj={cur_obj:.2f}, best={best_obj:.2f}, temp={temp:.2f}")

    best.reassign_depots()
    logger.info(f"ALNS finished. best_obj={best_obj:.2f}, vehicles_used={sum(1 for r in best.routes if r)}")
    return best


def optimize_alns(dist_mat, time_mat, n_depots, n_cust, tw, demands,
                  fleet, max_iter=300, temperature=150.0, use_tw=False, svc_map=None,
                  demands_kg=None, obj_weights=None, use_volume_cap=True, use_weight_cap=True,
                  fuel_price_rsd_l=None, driver_wage_rsd_h=None, fuel_load_factor=None,
                  overlap_threshold_km=None, overlap_weight_rsd=None,
                  dist_rsd_per_km=None, tw_penalty_rsd=None, alns_cooling=None,
                  no_wait=False, cancel_event=None):
    demands_kg = demands_kg or [0.0] * len(demands)
    num_v = len(fleet)

    minimise_vehicles_flag = (obj_weights or {}).get("vehicles", False)
    temp = max(temperature, 10_000.0) if minimise_vehicles_flag else temperature

    only_vehicles = (
        minimise_vehicles_flag
        and not (obj_weights.get("fuel") or obj_weights.get("wages") or obj_weights.get("distance"))
    )

    adv = dict(
        overlap_threshold_km=overlap_threshold_km,
        overlap_weight_rsd=overlap_weight_rsd,
        dist_rsd_per_km=dist_rsd_per_km,
        tw_penalty_rsd=tw_penalty_rsd,
        alns_cooling=alns_cooling,
        no_wait=no_wait,
        cancel_event=cancel_event,
    )

    if only_vehicles:
        if use_weight_cap and not use_volume_cap:
            sorted_fleet = sorted(fleet, key=lambda v: v.get("weight_capacity", 0) or 0, reverse=True)
        else:
            sorted_fleet = sorted(fleet, key=lambda v: v.get("capacity", 0) or 0, reverse=True)

        for k in range(1, num_v + 1):
            sub_fleet = sorted_fleet[:k]
            best_state = _alns_optimize(
                sub_fleet, dist_mat, time_mat, n_depots, n_cust, tw,
                demands, demands_kg, obj_weights, use_volume_cap, use_weight_cap,
                fuel_price_rsd_l, driver_wage_rsd_h, fuel_load_factor,
                temp, max_iter, svc_map, use_tw, **adv
            )
            if best_state.objective() < float("inf"):
                return best_state
        return best_state
    else:
        return _alns_optimize(
            fleet, dist_mat, time_mat, n_depots, n_cust, tw,
            demands, demands_kg, obj_weights, use_volume_cap, use_weight_cap,
            fuel_price_rsd_l, driver_wage_rsd_h, fuel_load_factor,
            temp, max_iter, svc_map, use_tw, **adv
        )


# ─────────────────────── OPTIMIZE ENDPOINT (async with cancellation) ───────────────────
import uuid as _uuid


@app.route("/api/optimize", methods=["POST"])
@login_required
def optimize():
    data = request.json
    if not data:
        return jsonify({"ok": False, "error": "No data received"})

    job_id = str(_uuid.uuid4())
    user   = session.get("user", "unknown")

    _job_create(job_id, user)

    def _run():
        cancel_event = _running_jobs.get(job_id)
        try:
            result = _do_optimize(data, user, cancel_event)
            _job_set_done(job_id, result)
        except Exception as exc:
            import traceback
            logger.error(f"Job {job_id} exception: {exc}\n{traceback.format_exc()}")
            _job_set_error(job_id, str(exc))

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "job_id": job_id})


@app.route("/api/optimize/status/<job_id>", methods=["GET"])
@login_required
def optimize_status(job_id):
    job = _job_get(job_id)
    if job is None:
        return jsonify({"ok": False, "error": "Job not found or expired"}), 404
    if job["status"] == "running":
        return jsonify({"ok": True, "status": "running"})
    if job["status"] == "error":
        return jsonify({"ok": False, "status": "error", "error": job["error"]})
    return jsonify({"ok": True, "status": "done", "result": job["result"]})


def _do_optimize(data, user, cancel_event=None):
    """The synchronous optimization logic, now with cancellation support."""
    if not data:
        raise ValueError("No data received")

    logger.info(f"Optimization started for user {user}, cancel_event={cancel_event is not None}")

    # Parse depots (list) with legacy single-depot fallback
    depots_raw  = data.get("depots") or []
    if not depots_raw and data.get("depot"):
        depots_raw = [data["depot"]]
    customers   = data.get("customers", [])
    fleet_cfg   = data.get("fleet", [])
    algorithm   = data.get("algorithm", "ALNS")
    use_tw      = data.get("use_time_windows", False)
    _n_custs_hint = len(customers)
    if "max_iterations" in data:
        max_iter = int(data["max_iterations"])
    elif _n_custs_hint <= 20:
        max_iter = 600
    elif _n_custs_hint <= 40:
        max_iter = 400
    elif _n_custs_hint <= 60:
        max_iter = 250
    elif _n_custs_hint <= 80:
        max_iter = 180
    else:
        max_iter = 120
    temperature = float(data.get("temperature", 150.0))
    raw_ow      = data.get("obj_weights", {})
    obj_weights = {
        "fuel":     bool(raw_ow.get("fuel",     False)),
        "wages":    bool(raw_ow.get("wages",    False)),
        "distance": bool(raw_ow.get("distance", False)),
        "vehicles": bool(raw_ow.get("vehicles", False)),
        "overlap":  bool(raw_ow.get("overlap",  False)),
    }
    if not any(obj_weights.values()):
        obj_weights["fuel"] = obj_weights["wages"] = True
    fuel_price_rsd_l      = float(data.get("fuel_price_rsd_l",  FUEL_PRICE_RSD_PER_LITRE))
    driver_wage_rsd_h     = float(data.get("driver_wage_rsd_h", DRIVER_WAGE_RSD_PER_HOUR))
    fuel_load_factor_pct  = float(data.get("fuel_load_factor_pct", FUEL_LOAD_FACTOR_PER_1000KG * 100))
    fuel_load_factor      = fuel_load_factor_pct / 100.0
    use_volume_cap = bool(data.get("use_volume_capacity", True))
    use_weight_cap = bool(data.get("use_weight_capacity", True))
    adv_params = data.get("advanced_params", {})
    k_nearest            = int(adv_params.get("k_nearest",            K_NEAREST))
    sentinel_factor      = float(adv_params.get("sentinel_factor",    SENTINEL_FACTOR))
    overlap_threshold_km = float(adv_params.get("overlap_threshold_km", OVERLAP_THRESHOLD_KM))
    overlap_weight_rsd   = float(adv_params.get("overlap_weight_rsd",   OVERLAP_WEIGHT_RSD))
    dist_rsd_per_km      = float(adv_params.get("dist_rsd_per_km",      20.0))
    tw_penalty_rsd       = float(adv_params.get("tw_penalty_rsd",       100.0))
    alns_cooling         = float(adv_params.get("alns_cooling",         0.995))
    hist_blend_weight    = float(adv_params.get("hist_blend_weight",    0.5))
    hist_blend_weight    = max(0.0, min(1.0, hist_blend_weight))

    if not depots_raw:
        raise ValueError("No depot provided")
    if not customers:
        raise ValueError("No customers provided")

    depots   = depots_raw
    n_depots = len(depots)
    n_cust   = len(customers)

    # Serbia validation
    outside = []
    for i, dep in enumerate(depots):
        if not in_serbia(dep["lat"], dep["lng"]):
            outside.append(dep.get("name", f"Depot {i+1}"))
    for c in customers:
        if not in_serbia(c["lat"], c["lng"]):
            outside.append(c.get("name", "Customer"))
    if outside:
        raise ValueError(f"Outside Serbia: {', '.join(outside[:5])}.")

    all_locs_orig = depots + customers
    departure_time_str = data.get("departure_time", "")
    departure_min = None
    if departure_time_str:
        try:
            dh, dm = map(int, departure_time_str.split(":"))
            departure_min = dh * 60 + dm
        except Exception:
            departure_min = None

    logger.info("Building distance/time matrix...")
    dist_mat, time_mat, matrix_source = fetch_best_matrix(
        all_locs_orig, k_nearest=k_nearest, sentinel_factor=sentinel_factor,
        departure_min=departure_min, hist_blend_weight=hist_blend_weight)

    if HERE_API_KEY and DATABASE_URL:
        _, pairs_for_prefetch = build_api_pairs(all_locs_orig, k=k_nearest or K_NEAREST)
        prefetch_traffic_history(all_locs_orig, pairs_for_prefetch)

    all_locs = all_locs_orig
    pkg_sizes = data.get("pkg_sizes", [0.10, 0.30, 0.60])
    while len(pkg_sizes) < 3:
        pkg_sizes.append(0.10)

    def customer_volume(c):
        counts = c.get("pkg_counts", [0, 0, 0])
        while len(counts) < 3:
            counts.append(0)
        return sum(counts[j] * pkg_sizes[j] for j in range(3))

    demands = [max(0.0, customer_volume(c)) for c in customers]

    pkg_weights_kg = data.get("pkg_weights_kg", DEFAULT_PKG_WEIGHTS_KG)
    while len(pkg_weights_kg) < 3:
        pkg_weights_kg.append(DEFAULT_PKG_WEIGHTS_KG[len(pkg_weights_kg)])

    def customer_weight(c):
        counts = c.get("pkg_counts", [0, 0, 0])
        while len(counts) < 3:
            counts.append(0)
        return sum(counts[j] * pkg_weights_kg[j] for j in range(3))

    demands_kg = [max(0.0, customer_weight(c)) for c in customers]

    svc_map_orig = {}
    for i, c in enumerate(customers):
        ut = c.get("unloading_time", SERVICE_TIME)
        try:
            ut = max(1, int(float(ut)))
        except Exception:
            ut = SERVICE_TIME
        svc_map_orig[n_depots + i] = ut

    max_vol_cap = max(
        (float(v.get("volume_capacity", v.get("capacity", 9999))) for v in fleet_cfg),
        default=9999.0)
    max_wt_cap = max(
        (float(v.get("weight_capacity", 0)) or float("inf") for v in fleet_cfg),
        default=float("inf"))

    orig_customers = customers
    n_orig_cust    = len(customers)

    sub_to_orig  = []
    exp_demands  = []
    exp_demands_kg = []
    exp_locs     = []

    for orig_i, c in enumerate(customers):
        vol = demands[orig_i]
        wt  = demands_kg[orig_i]
        n_splits = 1
        if use_volume_cap and max_vol_cap < 9990 and vol > max_vol_cap + 1e-9:
            n_splits = max(n_splits,
                           int(vol / max_vol_cap) + (1 if vol % max_vol_cap > 1e-9 else 0))
        if use_weight_cap and max_wt_cap < float("inf") and wt > max_wt_cap + 1e-9:
            n_splits = max(n_splits,
                           int(wt / max_wt_cap) + (1 if wt % max_wt_cap > 1e-9 else 0))
        for _ in range(n_splits):
            sub_to_orig.append(orig_i)
            exp_demands.append(round(vol / n_splits, 6))
            exp_demands_kg.append(round(wt  / n_splits, 6))
            exp_locs.append(c)

    n_sub = len(sub_to_orig)
    orig_size = n_depots + n_orig_cust
    exp_size  = n_depots + n_sub

    def _expand_matrix(mat: np.ndarray) -> np.ndarray:
        idx = np.empty(exp_size, dtype=np.intp)
        for r in range(exp_size):
            idx[r] = r if r < n_depots else n_depots + sub_to_orig[r - n_depots]
        return mat[np.ix_(idx, idx)]

    dist_mat  = _expand_matrix(dist_mat)
    time_mat  = _expand_matrix(time_mat)
    dist_mat = np.ascontiguousarray(dist_mat, dtype=np.float64)
    time_mat = np.ascontiguousarray(time_mat, dtype=np.float64)

    all_locs   = depots + exp_locs
    n_cust     = n_sub
    demands    = exp_demands
    demands_kg = exp_demands_kg

    if use_tw:
        tw = []
        for loc in all_locs:
            t = loc.get("time_window", {"start": "09:00", "end": "17:00"})
            try:
                sh, sm = map(int, t["start"].split(":"))
                eh, em = map(int, t["end"].split(":"))
            except Exception:
                sh, sm, eh, em = 9, 0, 17, 0
            tw.append((sh*60+sm, eh*60+em))
        for d in range(n_depots):
            tw[d] = (6*60, 12*60)
    else:
        tw = [(6*60, 12*60)] * n_depots + [(540, 1020)] * n_cust

    if departure_min is not None:
        for d in range(n_depots):
            tw[d] = (departure_min, departure_min)
        logger.info(f"Departure pinned to {mins_to_hhmm(departure_min)}")

    svc_map = {}
    for sub_i, orig_i in enumerate(sub_to_orig):
        svc_map[n_depots + sub_i] = svc_map_orig.get(n_depots + orig_i, SERVICE_TIME)

    sub_part_num = {}
    orig_counter = {}
    for sub_i, orig_i in enumerate(sub_to_orig):
        orig_counter[orig_i] = orig_counter.get(orig_i, 0) + 1
        sub_part_num[sub_i] = orig_counter[orig_i]

    vehicle_colors = ["#e74c3c","#3498db","#2ecc71","#f39c12",
                      "#9b59b6","#1abc9c","#e67e22","#e84342"]
    fleet = []
    for veh in fleet_cfg:
        for k in range(max(0, int(veh.get("count", 1)))):
            fleet.append({
                "type":             veh.get("name", "Vehicle"),
                "capacity":         float(veh.get("volume_capacity", veh.get("capacity", 9999))),
                "weight_capacity":  float(veh.get("weight_capacity", 0.0)),
                "color":            veh.get("color", "#3b82f6"),
                "fuel_consumption": float(veh.get("fuel_consumption", 10.0)),
                "min_vol_pct":      float(veh.get("min_vol_pct", 0.0)),
                "min_wt_pct":       float(veh.get("min_wt_pct",  0.0)),
            })
    if not fleet:
        fleet = [{"type":"Vehicle","capacity":9999.0,"weight_capacity":0.0,
                  "color":"#3b82f6","fuel_consumption":10.0}]

    logger.info(f"{algorithm} depots={n_depots} custs={n_cust} vehicles={len(fleet)} matrix={len(dist_mat)}x{len(dist_mat[0])} source={matrix_source}")

    no_wait = departure_min is not None

    adv_kwargs = dict(
        overlap_threshold_km=overlap_threshold_km,
        overlap_weight_rsd=overlap_weight_rsd,
        dist_rsd_per_km=dist_rsd_per_km,
        tw_penalty_rsd=tw_penalty_rsd,
        no_wait=no_wait,
        cancel_event=cancel_event,
    )
    if "Nearest Neighbor" in algorithm:
        state = optimize_nn(dist_mat, time_mat, n_depots, n_cust, tw, demands,
                            use_tw=use_tw, svc_map=svc_map, demands_kg=demands_kg,
                            obj_weights=obj_weights,
                            use_volume_cap=use_volume_cap, use_weight_cap=use_weight_cap,
                            fuel_price_rsd_l=fuel_price_rsd_l, driver_wage_rsd_h=driver_wage_rsd_h,
                            fuel_load_factor=fuel_load_factor, **adv_kwargs)
    elif "Model 2" in algorithm:
        state = optimize_2opt(dist_mat, time_mat, n_depots, n_cust, tw, demands,
                              use_tw=use_tw, svc_map=svc_map, demands_kg=demands_kg,
                              obj_weights=obj_weights,
                              use_volume_cap=use_volume_cap, use_weight_cap=use_weight_cap,
                              fuel_price_rsd_l=fuel_price_rsd_l, driver_wage_rsd_h=driver_wage_rsd_h,
                              fuel_load_factor=fuel_load_factor, **adv_kwargs)
    else:
        state = optimize_alns(dist_mat, time_mat, n_depots, n_cust, tw,
                               demands, fleet, max_iter, temperature,
                               use_tw=use_tw, svc_map=svc_map, demands_kg=demands_kg,
                               obj_weights=obj_weights,
                               use_volume_cap=use_volume_cap, use_weight_cap=use_weight_cap,
                               fuel_price_rsd_l=fuel_price_rsd_l, driver_wage_rsd_h=driver_wage_rsd_h,
                               fuel_load_factor=fuel_load_factor,
                               alns_cooling=alns_cooling, **adv_kwargs)

    total_dist = state.total_distance()
    vehicle_routes  = []
    real_total_dist = 0.0

    for v_idx, route in enumerate(state.routes):
        if not route:
            continue

        depot_mat = state.depot_of[v_idx]
        dep_loc   = all_locs[depot_mat]
        veh_cfg   = state.fleet[v_idx]
        color     = vehicle_colors[v_idx % len(vehicle_colors)]

        pts       = [dep_loc] + [all_locs[c] for c in route] + [dep_loc]
        waypoints = [(p["lng"], p["lat"]) for p in pts]
        geom, seg_dist, seg_dur, route_src = fetch_best_route(waypoints)
        real_total_dist += seg_dist or 0

        depart_min = latest_feasible_departure(
            route, depot_mat, dist_mat, time_mat, tw, SERVICE_TIME, svc_map,
            no_wait=no_wait)

        _, sched = route_time(route, depot_mat, dist_mat, time_mat, tw,
                               SERVICE_TIME, depart_min, svc_map, no_wait=no_wait)
        stops = []
        for stop_num, entry in enumerate(sched, start=1):
            cmat     = entry["customer_mat"]
            loc      = all_locs[cmat]
            t        = loc.get("time_window", {"start":"?","end":"?"})
            sub_idx  = cmat - n_depots
            orig_i   = sub_to_orig[sub_idx] if sub_idx < len(sub_to_orig) else sub_idx
            orig_c   = orig_customers[orig_i] if orig_i < len(orig_customers) else {}
            n_splits_for_cust = sub_to_orig.count(orig_i)
            c_counts = orig_c.get("pkg_counts", [0, 0, 0])
            while len(c_counts) < 3:
                c_counts.append(0)
            split_counts = [round(cnt / n_splits_for_cust, 4) for cnt in c_counts]
            c_volume = demands[sub_idx]
            stops.append({
                "stop_number":  stop_num,
                "name":         loc.get("name", ""),
                "lat":          loc.get("lat"),
                "lng":          loc.get("lng"),
                "pkg_counts":   split_counts,
                "volume":       round(c_volume, 3),
                "arrival":      mins_to_hhmm(entry["arrival"]),
                "depart":       mins_to_hhmm(entry["depart"]),
                "wait":         int(entry.get("wait", 0)),
                "violation":    int(entry.get("violation", 0)),
                "tw_start":     t.get("start","?"),
                "tw_end":       t.get("end","?"),
                "service_time": entry.get("service_time", SERVICE_TIME),
                "split":        n_splits_for_cust > 1,
                "split_part":   sub_part_num.get(sub_idx) if n_splits_for_cust > 1 else None,
                "split_total":  n_splits_for_cust if n_splits_for_cust > 1 else None,
            })

        route_km    = (seg_dist if seg_dist
                       else route_dist(route, depot_mat, dist_mat))
        route_weight_kg = sum(
            demands_kg[c - n_depots]
            for c in route
            if 0 <= (c - n_depots) < len(demands_kg)
        )
        base_fuel       = veh_cfg.get("fuel_consumption", 10.0)
        eff_fuel        = base_fuel * (1.0 + fuel_load_factor * (route_weight_kg / 2.0) / 1000.0)
        fuel_l          = round(route_fuel_litres(
            route, depot_mat, dist_mat,
            demands_kg, n_depots,
            lambda kg: base_fuel * (1.0 + fuel_load_factor * kg / 1000.0)
        ), 2)
        fuel_cost       = round(fuel_l * fuel_price_rsd_l, 0)
        work_mins   = route_working_minutes(
            route, depot_mat, dist_mat, time_mat, tw, SERVICE_TIME, depart_min,
            svc_map, no_wait=no_wait)
        work_h      = round(work_mins / 60.0, 2)
        wage_cost   = round(work_h * driver_wage_rsd_h, 0)

        if sched:
            last_dep  = sched[-1]["depart"]
            return_min = last_dep + time_mat[route[-1]][depot_mat]
        else:
            return_min = depart_min

        vehicle_routes.append({
            "vehicle_id":      v_idx,
            "type":            veh_cfg.get("type", f"Vehicle {v_idx+1}"),
            "color":           color,
            "depot_name":      dep_loc.get("name", f"Depot {depot_mat+1}"),
            "depot_idx":       depot_mat,
            "depot_lat":       dep_loc.get("lat"),
            "depot_lng":       dep_loc.get("lng"),
            "geometry":        geom or [],
            "distance":        round(route_km, 2),
            "fuel_consumption": round(veh_cfg.get("fuel_consumption", 10.0), 1),
            "fuel_used":       fuel_l,
            "fuel_cost_rsd":   int(fuel_cost),
            "num_customers":   len(route),
            "volume_used":     round(sum(demands[c - n_depots] for c in route), 3),
            "volume_capacity": round(veh_cfg.get("capacity", 9999), 3),
            "weight_used":     round(route_weight_kg, 1),
            "weight_capacity": round(veh_cfg.get("weight_capacity", 0.0), 1),
            "effective_fuel_consumption": round(eff_fuel, 2),
            "departure_time":  mins_to_hhmm(depart_min),
            "return_time":     mins_to_hhmm(return_min),
            "working_hours":   work_h,
            "wage_cost_rsd":   int(wage_cost),
            "total_cost_rsd":  int(fuel_cost + wage_cost),
            "stops":           stops,
        })

    total_working_mins  = sum(vr["working_hours"] * 60 for vr in vehicle_routes)
    hours, mins         = divmod(int(round(total_working_mins)), 60)

    total_volume        = sum(demands)
    total_fuel_used     = sum(vr["fuel_used"] for vr in vehicle_routes)
    total_fuel_cost_rsd = sum(vr["fuel_cost_rsd"] for vr in vehicle_routes)
    total_wage_cost_rsd = sum(vr["wage_cost_rsd"] for vr in vehicle_routes)
    total_cost_rsd      = total_fuel_cost_rsd + total_wage_cost_rsd
    matrix_msg = {
        "here":      "live traffic (HERE) — routes & map display",
        "osrm":      "road distances (OSRM, no live traffic)",
        "haversine": "straight-line estimates (all routers unavailable)",
    }.get(matrix_source, matrix_source)

    del dist_mat, time_mat
    import gc; gc.collect()

    for vr in vehicle_routes:
        _save_route_to_db_async({
            "route_date":        str(date.today()),
            "saved_by":          user,
            "algorithm":         algorithm,
            "matrix_source":     matrix_source,
            "fuel_price_rsd_l":  fuel_price_rsd_l,
            "driver_wage_rsd_h": driver_wage_rsd_h,
            "vehicle_route":     vr,
        })

    result = {
        "ok":                  True,
        "matrix_source":       matrix_source,
        "matrix_msg":          matrix_msg,
        "n_depots":            n_depots,
        "total_distance":      round(real_total_dist or total_dist, 2),
        "total_fuel":          round(total_fuel_used, 2),
        "total_fuel_cost_rsd": total_fuel_cost_rsd,
        "total_wage_cost_rsd": total_wage_cost_rsd,
        "total_cost_rsd":      total_cost_rsd,
        "driver_wage_rsd_h":   driver_wage_rsd_h,
        "fuel_price_rsd_l":    fuel_price_rsd_l,
        "fuel_load_factor_pct": round(fuel_load_factor * 100, 2),
        "total_time_h":        hours,
        "total_time_m":        mins,
        "total_volume":        round(total_volume, 3),
        "pkg_sizes":           pkg_sizes,
        "pkg_weights_kg":       pkg_weights_kg,
        "vehicle_routes":      vehicle_routes,
        "unserved_customers":  list({
            orig_customers[sub_to_orig[sub_i]].get("name", f"Customer {sub_to_orig[sub_i]+1}")
            for sub_i in range(len(sub_to_orig))
            if (n_depots + sub_i) not in {c for route in state.routes for c in route}
        }),
        "algorithm":           algorithm,
        "obj_weights":         obj_weights,
        "use_volume_capacity": use_volume_cap,
        "use_weight_capacity": use_weight_cap,
        "service_time":        SERVICE_TIME,
    }
    logger.info(f"Optimization finished for user {user}, total cost {total_cost_rsd} RSD, {len(vehicle_routes)} vehicles")
    return result


# ─────────────────────── ROUTE HISTORY (unchanged) ──────────────────────────
@app.route("/api/routes", methods=["GET"])
@login_required
def list_routes():
    if not DATABASE_URL:
        return jsonify({"ok": False, "error": "Database not configured", "routes": []})
    try:
        conn = _get_db_conn()
        cur  = conn.cursor()
        cur.execute("""
            SELECT
                route_id, route_date, saved_by, algorithm, matrix_source,
                vehicle_type, depot_name,
                total_distance_km, total_fuel_litres,
                fuel_cost_rsd, wage_cost_rsd, total_cost_rsd,
                working_hours, departure_time, return_time,
                volume_used_m3, weight_used_kg, num_stops,
                fuel_price_rsd_l, driver_wage_rsd_h,
                created_at
            FROM grps_routes
            ORDER BY route_id DESC
            LIMIT 100
        """)
        cols = [d[0] for d in cur.description]
        rows = []
        for row in cur.fetchall():
            d = dict(zip(cols, row))
            for k, v in d.items():
                if hasattr(v, 'isoformat'):
                    d[k] = v.isoformat()
            rows.append(d)
        conn.close()
        return jsonify({"ok": True, "routes": rows})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "routes": []})


@app.route("/api/routes/<int:route_id>", methods=["GET"])
@login_required
def get_route(route_id):
    if not DATABASE_URL:
        return jsonify({"ok": False, "error": "Database not configured"})
    try:
        conn = _get_db_conn()
        cur  = conn.cursor()
        cur.execute("SELECT * FROM grps_routes WHERE route_id = %s", (route_id,))
        cols = [d[0] for d in cur.description]
        row  = cur.fetchone()
        if not row:
            return jsonify({"ok": False, "error": "Route not found"}), 404
        route = dict(zip(cols, row))
        for k, v in route.items():
            if hasattr(v, 'isoformat'):
                route[k] = v.isoformat()

        cur.execute("""
            SELECT * FROM grps_route_stops
            WHERE route_id = %s ORDER BY stop_sequence
        """, (route_id,))
        stop_cols = [d[0] for d in cur.description]
        stops = []
        for s in cur.fetchall():
            sd = dict(zip(stop_cols, s))
            for k, v in sd.items():
                if hasattr(v, 'isoformat'):
                    sd[k] = v.isoformat()
            stops.append(sd)

        conn.close()
        route["stops"] = stops
        return jsonify({"ok": True, "route": route})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/routes/<int:route_id>", methods=["DELETE"])
@login_required
def delete_route(route_id):
    if not DATABASE_URL:
        return jsonify({"ok": False, "error": "Database not configured"})
    try:
        conn = _get_db_conn()
        cur  = conn.cursor()
        cur.execute("DELETE FROM grps_routes WHERE route_id = %s RETURNING route_id", (route_id,))
        deleted = cur.fetchone()
        conn.commit()
        conn.close()
        if not deleted:
            return jsonify({"ok": False, "error": "Route not found"}), 404
        return jsonify({"ok": True, "deleted_id": route_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─────────────────────── PDF REPORT (unchanged) ──────────────────────────────
@app.route("/api/pdf", methods=["POST"])
@login_required
def generate_pdf():
    data = request.json
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("Title2", parent=styles["Heading1"],
               fontSize=18, textColor=rl_colors.HexColor("#2c3e50"),
               alignment=TA_CENTER, spaceAfter=16))
    styles.add(ParagraphStyle("Sec", parent=styles["Heading2"],
               fontSize=13, textColor=rl_colors.HexColor("#3498db"),
               spaceBefore=12, spaceAfter=6))
    styles.add(ParagraphStyle("Info", parent=styles["Normal"],
               fontSize=9, textColor=rl_colors.HexColor("#34495e"), spaceAfter=2))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                             rightMargin=50, leftMargin=50,
                             topMargin=50, bottomMargin=50)
    story = []
    story.append(Paragraph("Delivery Route Optimization Report", styles["Title2"]))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                            styles["Info"]))
    story.append(Spacer(1, 12))

    # Summary
    story.append(Paragraph("Summary", styles["Sec"]))
    summary = [
        ["Algorithm", data.get("algorithm","—")],
        ["Optimised for", " + ".join(k for k,v in data.get("obj_weights",{"fuel":True,"wages":True}).items() if v) or "fuel + wages"],
        ["Total Distance", f"{data.get('total_distance',0):.1f} km"],
        ["Total Fuel Used", f"{data.get('total_fuel',0):.2f} L"],
        ["Fuel Cost", f"{data.get('total_fuel_cost_rsd',0):,} RSD  ({data.get('fuel_price_rsd_l',200):.0f} RSD/L)"],
        ["Driver Wages", f"{data.get('total_wage_cost_rsd',0):,} RSD  ({data.get('driver_wage_rsd_h',900):.0f} RSD/h)"],
        ["Total Cost", f"{data.get('total_cost_rsd',0):,} RSD"],
        ["Total Time", f"{data.get('total_time_h',0)}h {data.get('total_time_m',0)}m"],
        ["Total Customers", str(data.get("total_customers",0))],
        ["Total Volume", f"{data.get('total_volume', data.get('total_packages',0)):.3f} m\u00b3"],
        ["Pkg Sizes (m\u00b3)", " \u00b7 ".join(f"{s:.3f}" for s in data.get("pkg_sizes",[0.10,0.30,0.60]))],
        ["Vehicles Used", str(data.get("vehicles_used",0))],
    ]
    veh_routes     = data.get("vehicle_routes", [])
    total_vol_used = sum(float(vr.get("volume_used", vr.get("packages", 0))) for vr in veh_routes)
    total_vol_cap  = sum(float(vr.get("volume_capacity", vr.get("capacity", 0))) for vr in veh_routes)
    total_wt_used  = sum(float(vr.get("weight_used", 0)) for vr in veh_routes)
    total_wt_cap   = sum(float(vr.get("weight_capacity", 0)) for vr in veh_routes)
    vol_pct        = f"{total_vol_used / total_vol_cap * 100:.1f}%" if total_vol_cap > 0 else "\u2014"
    wt_pct         = f"{total_wt_used  / total_wt_cap  * 100:.1f}%" if total_wt_cap  > 0 else "\u2014"
    summary += [
        ["Vol. Capacity (fleet)",  f"{total_vol_cap:.1f} m\u00b3"],
        ["Vol. Used (fleet)",      f"{total_vol_used:.2f} m\u00b3  \u2192  {vol_pct}"],
        ["Weight Cap. (fleet)",    f"{total_wt_cap:,.0f} kg" if total_wt_cap > 0 else "Unlimited"],
        ["Weight Used (fleet)",    f"{total_wt_used:,.0f} kg  \u2192  {wt_pct}" if total_wt_cap > 0 else "\u2014"],
    ]
    t = Table(summary, colWidths=[120, 180])
    cap_row_start = len(summary) - 4
    t.setStyle(TableStyle([
        ("FONTSIZE",(0,0),(-1,-1),9),
        ("GRID",(0,0),(-1,-1),0.5,rl_colors.grey),
        ("BACKGROUND",(0,0),(0,-1),rl_colors.HexColor("#f0f9f0")),
        ("FONTNAME",(0,0),(0,-1),"Helvetica-Bold"),
        ("BACKGROUND",(0,cap_row_start),(-1,-1),rl_colors.HexColor("#e8f5e9")),
        ("FONTNAME",(0,cap_row_start),(0,-1),"Helvetica-Bold"),
        ("TEXTCOLOR",(1,cap_row_start),(1,-1),rl_colors.HexColor("#1b5e20")),
    ]))
    story.append(t); story.append(Spacer(1,10))

    # Fleet
    story.append(Paragraph("Fleet Configuration", styles["Sec"]))
    fleet_data = [["Vehicle Type","Count","Vol. Cap. (m³)","Weight Cap. (kg)","Fuel (L/100km)"]]
    for v in data.get("fleet",[]):
        vol_cap = v.get("volume_capacity", v.get("capacity", "?"))
        wt_cap  = v.get("weight_capacity", 0)
        wt_str  = f"{wt_cap:.0f}" if wt_cap and float(wt_cap) > 0 else "Unlimited"
        fleet_data.append([v["name"], str(v.get("count",1)),
                           str(vol_cap), wt_str,
                           str(v.get("fuel_consumption", 10.0))])
    ft = Table(fleet_data, colWidths=[110, 40, 80, 90, 90])
    ft.setStyle(TableStyle([
        ("FONTSIZE",(0,0),(-1,-1),9),
        ("BACKGROUND",(0,0),(-1,0),rl_colors.HexColor("#3498db")),
        ("TEXTCOLOR",(0,0),(-1,0),rl_colors.white),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
        ("GRID",(0,0),(-1,-1),0.5,rl_colors.grey),
    ]))
    story.append(ft); story.append(Spacer(1,10))

    # Map image
    map_b64 = data.get("map_image")
    if map_b64:
        try:
            img_bytes = base64.b64decode(map_b64)
            img_buf   = io.BytesIO(img_bytes)
            available_w = A4[0] - 100
            max_h       = 280
            rl_img      = RLImage(img_buf, width=available_w, height=max_h,
                                  kind='bound')
            story.append(Paragraph("Route Map", styles["Sec"]))
            story.append(rl_img)
            story.append(Spacer(1, 12))
        except Exception as e:
            story.append(Paragraph(f"(Map image unavailable: {e})", styles["Info"]))

    # Per-vehicle routes
    story.append(Paragraph("Route Details", styles["Sec"]))
    available_w = A4[0] - 100
    for vr in data.get("vehicle_routes",[]):
        hex_color = vr.get("color", "#3498db")
        styles_veh_title = ParagraphStyle(
            f"VehTitle_{vr['vehicle_id']}",
            parent=styles["Info"],
            fontSize=10,
            fontName="Helvetica-Bold",
            textColor=rl_colors.HexColor(hex_color),
            spaceBefore=10,
            spaceAfter=3,
        )
        vol_used = vr.get("volume_used", vr.get("packages", 0))
        vol_cap  = vr.get("volume_capacity", vr.get("capacity", "?"))
        wt_used  = float(vr.get("weight_used", 0))
        wt_cap   = float(vr.get("weight_capacity", 0))
        vol_pct_str = f" ({float(vol_used)/float(vol_cap)*100:.0f}%)" if float(vol_cap) > 0 else ""
        wt_pct_str  = f" ({wt_used/wt_cap*100:.0f}%)" if wt_cap > 0 else ""
        wt_cap_str  = "Unl." if wt_cap == 0 else f"{int(wt_cap)}kg"
        story.append(Paragraph(
            f"{vr['type']} #{vr['vehicle_id']+1} — "
            f"Departs {vr.get('departure_time','?')} · Returns {vr.get('return_time','?')} · "
            f"{vr.get('working_hours',0):.1f}h worked · "
            f"{vr['num_customers']} stops · "
            f"{float(vol_used):.2f}/{float(vol_cap):.1f} m\u00b3{vol_pct_str} · "
            f"{wt_used:.0f}/{wt_cap_str}{wt_pct_str} · "
            f"{vr['distance']:.1f} km · {vr.get('effective_fuel_consumption', vr.get('fuel_consumption',10)):.1f} L/100km · {vr.get('fuel_used',0):.2f} L · "
            f"Fuel {vr.get('fuel_cost_rsd',0):,} RSD · Wages {vr.get('wage_cost_rsd',0):,} RSD · "
            f"Total {vr.get('total_cost_rsd',0):,} RSD",
            styles_veh_title))

        veh_map_b64 = vr.get("vehicle_map_image")
        if veh_map_b64:
            try:
                veh_img_bytes = base64.b64decode(veh_map_b64)
                veh_img_buf   = io.BytesIO(veh_img_bytes)
                map_h = 180
                veh_rl_img = RLImage(veh_img_buf, width=available_w, height=map_h, kind='bound')
                story.append(veh_rl_img)
                story.append(Spacer(1, 4))
            except Exception as e:
                story.append(Paragraph(f"(Vehicle map unavailable: {e})", styles["Info"]))

        if vr.get("stops"):
            pkg_weights = data.get("pkg_weights_kg", [5.0, 15.0, 30.0])
            stop_data = [["#","Customer","Arrival","Depart","Window","P1","P2","P3","Vol m\u00b3","Wt kg"]]
            for i, s in enumerate(vr["stops"], 1):
                flag = f" \u26a0+{s['violation']}m" if s["violation"]>0 else ""
                pc = s.get("pkg_counts", [0, 0, 0])
                while len(pc) < 3: pc.append(0)
                vol = s.get("volume", 0)
                wt  = sum((pc[k] or 0) * (pkg_weights[k] if k < len(pkg_weights) else 0)
                          for k in range(3))
                stop_data.append([str(i), s["name"][:20],
                                   s["arrival"]+flag, s["depart"],
                                   f"{s['tw_start']}-{s['tw_end']}",
                                   str(round(pc[0],2)), str(round(pc[1],2)), str(round(pc[2],2)),
                                   f"{float(vol):.2f}",
                                   f"{wt:.1f}"])
            st = Table(stop_data, colWidths=[18, 88, 48, 44, 64, 20, 20, 20, 30, 30])
            st.setStyle(TableStyle([
                ("FONTSIZE",(0,0),(-1,-1),7.5),
                ("BACKGROUND",(0,0),(-1,0),rl_colors.HexColor("#ecf0f1")),
                ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
                ("GRID",(0,0),(-1,-1),0.4,rl_colors.lightgrey),
                ("ROWBACKGROUNDS",(0,1),(-1,-1),
                 [rl_colors.white, rl_colors.HexColor("#f9f9f9")]),
                ("BACKGROUND",(-2,0),(-1,0),rl_colors.HexColor("#d5e8d4")),
                ("BACKGROUND",(-2,1),(-1,-1),rl_colors.HexColor("#f0f7ef")),
            ]))
            story.append(st)
        story.append(Spacer(1,8))

    doc.build(story)
    buf.seek(0)
    fname = f"route_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(buf, mimetype="application/pdf",
                     as_attachment=True, download_name=fname)


# ─────────────────────── ADMIN DB BROWSER (unchanged) ────────────────────────
ADMIN_USER = os.environ.get("APP_USER", "admin")

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        if session["user"] != ADMIN_USER:
            abort(403)
        return f(*args, **kwargs)
    return decorated


@app.route("/admin/db")
@admin_required
def admin_db():
    if not DATABASE_URL:
        return (
            "<h2 style='font-family:monospace;color:#e74c3c'>"
            "DATABASE_URL is not configured on this deployment.</h2>",
            503,
        )

    TABLES = ["grps_routes", "grps_route_stops", "grps_workspaces"]
    counts   = {}
    previews = {}
    headers  = {}

    try:
        conn = _get_db_conn()
        cur  = conn.cursor()
        for tbl in TABLES:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {tbl}")
                counts[tbl] = cur.fetchone()[0]
                cur.execute(f"SELECT * FROM {tbl} ORDER BY 1 DESC LIMIT 5")
                col_names = [d[0] for d in cur.description]
                headers[tbl]  = col_names
                previews[tbl] = cur.fetchall()
            except Exception:
                counts[tbl]   = "—"
                headers[tbl]  = []
                previews[tbl] = []
        conn.close()
    except Exception as e:
        return (
            f"<h2 style='font-family:monospace;color:#e74c3c'>DB connection failed: {e}</h2>",
            500,
        )

    html = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GRPS — DB Admin</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Syne:wght@700;800&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d1117;--surface:#161b22;--border:#30363d;
  --accent:#2ecc71;--accent2:#3498db;--text:#e6edf3;
  --muted:#8b949e;--danger:#e74c3c;--warn:#f39c12;
}
body{font-family:'DM Mono',monospace;background:var(--bg);color:var(--text);min-height:100vh;padding:24px 20px}
body::before{content:'';position:fixed;inset:0;
  background-image:linear-gradient(rgba(46,204,113,.04) 1px,transparent 1px),
                   linear-gradient(90deg,rgba(46,204,113,.04) 1px,transparent 1px);
  background-size:40px 40px;pointer-events:none;z-index:0}
.wrap{position:relative;z-index:1;max-width:1200px;margin:0 auto}

/* Header */
.topbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:28px}
.logo{font-family:'Syne',sans-serif;font-size:26px;font-weight:800;color:var(--accent);letter-spacing:-1px}
.logo span{color:var(--muted);font-size:13px;font-weight:400;margin-left:10px;font-family:'DM Mono',monospace}
.nav-links a{color:var(--muted);text-decoration:none;font-size:12px;margin-left:16px;
             border:1px solid var(--border);border-radius:5px;padding:5px 12px;transition:all .15s}
.nav-links a:hover{color:var(--text);border-color:var(--text)}
.badge{display:inline-block;background:var(--danger);color:#fff;font-size:10px;
       padding:2px 8px;border-radius:99px;font-weight:700;margin-left:8px;vertical-align:middle}

/* Stat cards */
.cards{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:28px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;
      padding:18px 22px;flex:1;min-width:180px}
.card-label{font-size:10px;color:var(--muted);letter-spacing:.15em;text-transform:uppercase;margin-bottom:6px}
.card-value{font-family:'Syne',sans-serif;font-size:28px;font-weight:800;color:var(--accent)}
.card-sub{font-size:11px;color:var(--muted);margin-top:4px}

/* Section */
h2{font-family:'Syne',sans-serif;font-size:16px;font-weight:700;margin-bottom:12px;color:var(--text)}
.section{background:var(--surface);border:1px solid var(--border);border-radius:10px;
         padding:20px;margin-bottom:24px;overflow:hidden}

/* Table */
.tbl-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:12px}
th{background:#1c2430;color:var(--muted);font-weight:500;text-align:left;
   padding:8px 12px;border-bottom:1px solid var(--border);white-space:nowrap}
td{padding:7px 12px;border-bottom:1px solid #21262d;white-space:nowrap;
   max-width:260px;overflow:hidden;text-overflow:ellipsis}
tr:last-child td{border-bottom:none}
tr:hover td{background:rgba(255,255,255,.03)}
.null{color:var(--muted);font-style:italic}
.num{color:var(--accent2)}

/* SQL box */
.sql-box{display:flex;flex-direction:column;gap:12px}
.sql-box textarea{
  width:100%;background:var(--bg);border:1px solid var(--border);border-radius:7px;
  color:var(--text);font-family:'DM Mono',monospace;font-size:13px;
  padding:12px 14px;resize:vertical;min-height:90px;outline:none;
  transition:border-color .2s}
.sql-box textarea:focus{border-color:var(--accent2)}
.sql-row{display:flex;gap:10px;align-items:center}
.btn{font-family:'Syne',sans-serif;font-weight:700;font-size:13px;
     padding:9px 22px;border-radius:7px;border:none;cursor:pointer;transition:opacity .2s,transform .1s}
.btn:hover{opacity:.85}.btn:active{transform:scale(.97)}
.btn-run{background:var(--accent);color:#0d1117}
.btn-clear{background:var(--surface);color:var(--muted);border:1px solid var(--border)}
.hint-sql{font-size:11px;color:var(--muted)}
.warn-note{font-size:11px;color:var(--warn);margin-left:auto}

/* Result */
#result-area{margin-top:14px}
.result-info{font-size:11px;color:var(--muted);margin-bottom:8px}
.error-box{background:rgba(231,76,60,.1);border:1px solid rgba(231,76,60,.3);
           border-radius:7px;color:var(--danger);font-size:12px;padding:12px 16px}
.spinner{display:none;color:var(--muted);font-size:12px;margin-top:8px}
</style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div class="logo">GRPS <span>/ DB Admin <span class="badge">admin only</span></span></div>
    <div class="nav-links">
      <a href="/">← Back to App</a>
      <a href="/logout">Logout</a>
    </div>
  </div>

  <!-- Stat cards -->
  <div class="cards">
"""

    TABLE_LABELS = {
        "grps_routes":      ("Routes saved", "One row per optimised vehicle route"),
        "grps_route_stops": ("Stops saved",  "One row per delivery stop"),
        "grps_workspaces":  ("Workspaces",   "Saved workspace configs"),
    }
    for tbl, cnt in counts.items():
        label, sub = TABLE_LABELS.get(tbl, (tbl, ""))
        html += f"""    <div class="card">
      <div class="card-label">{label}</div>
      <div class="card-value">{cnt}</div>
      <div class="card-sub">{sub}</div>
    </div>\n"""

    html += "  </div>\n\n"

    for tbl in TABLES:
        html += f'  <div class="section">\n    <h2>{tbl} <span style="color:var(--muted);font-size:12px;font-weight:400">(latest 5 rows)</span></h2>\n'
        if not headers.get(tbl):
            html += '    <div class="hint-sql">Table not found or empty.</div>\n  </div>\n\n'
            continue
        html += '    <div class="tbl-wrap"><table><thead><tr>'
        for col in headers[tbl]:
            html += f"<th>{col}</th>"
        html += "</tr></thead><tbody>"
        for row in previews[tbl]:
            html += "<tr>"
            for cell in row:
                if cell is None:
                    html += '<td class="null">null</td>'
                elif isinstance(cell, (int, float)):
                    html += f'<td class="num">{cell}</td>'
                else:
                    val = str(cell)[:80]
                    html += f"<td>{val}</td>"
            html += "</tr>"
        if not previews[tbl]:
            html += f'<tr><td colspan="{len(headers[tbl])}" class="null">— no rows —</td></tr>'
        html += "</tbody></table></div>\n  </div>\n\n"

    html += r"""
  <div class="section">
    <h2>Custom SQL Query</h2>
    <div class="sql-box">
      <textarea id="sql" placeholder="SELECT * FROM grps_routes ORDER BY created_at DESC LIMIT 20;"></textarea>
      <div class="sql-row">
        <button class="btn btn-run" onclick="runSql()">▶ Run</button>
        <button class="btn btn-clear" onclick="clearSql()">Clear</button>
        <span class="hint-sql">SELECT-only. Results capped at 200 rows.</span>
        <span class="warn-note">⚠ Read-only — no INSERT / UPDATE / DELETE</span>
      </div>
      <div class="spinner" id="spinner">⏳ Running…</div>
      <div id="result-area"></div>
    </div>
  </div>
</div>

<script>
async function runSql() {
  const sql = document.getElementById('sql').value.trim();
  if (!sql) return;
  document.getElementById('spinner').style.display = 'block';
  document.getElementById('result-area').innerHTML = '';
  try {
    const r = await fetch('/admin/db/query', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({sql})
    });
    const d = await r.json();
    document.getElementById('spinner').style.display = 'none';
    if (d.error) {
      document.getElementById('result-area').innerHTML =
        `<div class="error-box">⚠ ${d.error}</div>`;
      return;
    }
    let html = `<div class="result-info">${d.rowcount} row(s) returned in ${d.elapsed_ms} ms</div>`;
    if (d.columns && d.rows.length > 0) {
      html += '<div class="tbl-wrap"><table><thead><tr>';
      d.columns.forEach(c => { html += `<th>${c}</th>`; });
      html += '</tr></thead><tbody>';
      d.rows.forEach(row => {
        html += '<tr>';
        row.forEach(cell => {
          if (cell === null)      html += '<td class="null">null</td>';
          else if (typeof cell === 'number') html += `<td class="num">${cell}</td>`;
          else html += `<td>${String(cell).substring(0,120)}</td>`;
        });
        html += '</tr>';
      });
      html += '</tbody></table></div>';
    } else if (d.rows.length === 0) {
      html += '<div class="hint-sql">Query returned no rows.</div>';
    }
    document.getElementById('result-area').innerHTML = html;
  } catch(e) {
    document.getElementById('spinner').style.display = 'none';
    document.getElementById('result-area').innerHTML =
      `<div class="error-box">Network error: ${e}</div>`;
  }
}
function clearSql() {
  document.getElementById('sql').value = '';
  document.getElementById('result-area').innerHTML = '';
}
document.getElementById('sql').addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') runSql();
});
</script>
</body>
</html>"""

    return html


@app.route("/admin/db/query", methods=["POST"])
@admin_required
def admin_db_query():
    import time as _t
    if not DATABASE_URL:
        return jsonify({"error": "DATABASE_URL not configured"}), 503
    body = request.get_json(force=True, silent=True) or {}
    sql  = (body.get("sql") or "").strip()
    if not sql:
        return jsonify({"error": "Empty query"}), 400
    first_token = sql.lstrip().split()[0].upper()
    if first_token not in ("SELECT", "WITH", "EXPLAIN"):
        return jsonify({"error": "Only SELECT / WITH / EXPLAIN queries are allowed."}), 403
    if "limit" not in sql.lower():
        sql = f"SELECT * FROM ({sql}) _q LIMIT 200"
    t0 = _t.time()
    try:
        conn = _get_db_conn()
        cur  = conn.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(200)
        conn.close()
        elapsed = round((_t.time() - t0) * 1000)
        safe_rows = []
        for row in rows:
            safe_rows.append([
                str(cell) if not isinstance(cell, (int, float, bool, type(None))) else cell
                for cell in row
            ])
        return jsonify({
            "columns":    cols,
            "rows":       safe_rows,
            "rowcount":   len(safe_rows),
            "elapsed_ms": elapsed,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────── WORKSPACE API (export added) ──────────────────────
@app.route("/api/workspaces", methods=["GET"])
@login_required
def list_workspaces():
    if not DATABASE_URL:
        return jsonify({"ok": False, "error": "Database not configured"}), 503
    try:
        conn = _get_db_conn()
        cur  = conn.cursor()
        cur.execute("""
            SELECT workspace_id, name, description, created_by, updated_by,
                   created_at, updated_at,
                   jsonb_array_length(customers) AS n_customers,
                   jsonb_array_length(depots)    AS n_depots
            FROM grps_workspaces
            ORDER BY updated_at DESC
        """)
        rows = cur.fetchall()
        conn.close()
        workspaces = []
        for r in rows:
            workspaces.append({
                "id":          r[0],
                "name":        r[1],
                "description": r[2] or "",
                "created_by":  r[3],
                "updated_by":  r[4],
                "created_at":  str(r[5]),
                "updated_at":  str(r[6]),
                "n_customers": r[7] or 0,
                "n_depots":    r[8] or 0,
            })
        return jsonify({"ok": True, "workspaces": workspaces})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/workspaces", methods=["POST"])
@login_required
def save_workspace():
    if not DATABASE_URL:
        return jsonify({"ok": False, "error": "Database not configured"}), 503
    body = request.get_json(force=True, silent=True) or {}
    name        = (body.get("name") or "").strip()
    description = (body.get("description") or "").strip()
    depots      = body.get("depots", [])
    customers   = body.get("customers", [])
    fleet       = body.get("fleet", [])
    settings    = body.get("settings", {})
    result      = body.get("result")
    ws_id       = body.get("id")
    user        = session.get("user", "unknown")

    if not name:
        return jsonify({"ok": False, "error": "Workspace name is required"}), 400

    try:
        conn = _get_db_conn()
        cur  = conn.cursor()
        if ws_id:
            cur.execute("""
                UPDATE grps_workspaces
                SET name=%s, description=%s, updated_by=%s, updated_at=NOW(),
                    depots=%s, customers=%s, fleet=%s, settings=%s, result=%s
                WHERE workspace_id=%s
                RETURNING workspace_id
            """, (name, description, user,
                  json.dumps(depots), json.dumps(customers),
                  json.dumps(fleet),  json.dumps(settings),
                  json.dumps(result) if result is not None else None,
                  ws_id))
            row = cur.fetchone()
            if not row:
                conn.close()
                return jsonify({"ok": False, "error": "Workspace not found"}), 404
            new_id = row[0]
        else:
            cur.execute("""
                INSERT INTO grps_workspaces
                    (name, description, created_by, updated_by,
                     depots, customers, fleet, settings, result)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING workspace_id
            """, (name, description, user, user,
                  json.dumps(depots), json.dumps(customers),
                  json.dumps(fleet),  json.dumps(settings),
                  json.dumps(result) if result is not None else None))
            new_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "id": new_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/workspaces/<int:ws_id>", methods=["GET"])
@login_required
def load_workspace(ws_id):
    if not DATABASE_URL:
        return jsonify({"ok": False, "error": "Database not configured"}), 503
    try:
        conn = _get_db_conn()
        cur  = conn.cursor()
        cur.execute("""
            SELECT workspace_id, name, description, created_by, updated_by,
                   created_at, updated_at,
                   depots, customers, fleet, settings, result
            FROM grps_workspaces
            WHERE workspace_id = %s
        """, (ws_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return jsonify({"ok": False, "error": "Workspace not found"}), 404
        return jsonify({
            "ok":          True,
            "id":          row[0],
            "name":        row[1],
            "description": row[2] or "",
            "created_by":  row[3],
            "updated_by":  row[4],
            "created_at":  str(row[5]),
            "updated_at":  str(row[6]),
            "depots":      row[7],
            "customers":   row[8],
            "fleet":       row[9],
            "settings":    row[10],
            "result":      row[11],
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/workspaces/<int:ws_id>", methods=["DELETE"])
@login_required
def delete_workspace(ws_id):
    if not DATABASE_URL:
        return jsonify({"ok": False, "error": "Database not configured"}), 503
    try:
        conn = _get_db_conn()
        cur  = conn.cursor()
        cur.execute("DELETE FROM grps_workspaces WHERE workspace_id=%s RETURNING workspace_id",
                    (ws_id,))
        row = cur.fetchone()
        conn.commit()
        conn.close()
        if not row:
            return jsonify({"ok": False, "error": "Workspace not found"}), 404
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# --- NEW: Export workspace as JSON file ---------------------------------------
@app.route("/api/workspaces/<int:ws_id>/export", methods=["GET"])
@login_required
def export_workspace(ws_id):
    """Export a workspace as a downloadable JSON file."""
    if not DATABASE_URL:
        return jsonify({"ok": False, "error": "Database not configured"}), 503
    try:
        conn = _get_db_conn()
        cur  = conn.cursor()
        cur.execute("""
            SELECT workspace_id, name, description, created_by, updated_by,
                   created_at, updated_at,
                   depots, customers, fleet, settings, result
            FROM grps_workspaces
            WHERE workspace_id = %s
        """, (ws_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return jsonify({"ok": False, "error": "Workspace not found"}), 404
        workspace = {
            "id":          row[0],
            "name":        row[1],
            "description": row[2] or "",
            "created_by":  row[3],
            "updated_by":  row[4],
            "created_at":  str(row[5]),
            "updated_at":  str(row[6]),
            "depots":      row[7],
            "customers":   row[8],
            "fleet":       row[9],
            "settings":    row[10],
            "result":      row[11],
        }
        # Convert datetime objects to string
        if workspace["created_at"] and hasattr(workspace["created_at"], "isoformat"):
            workspace["created_at"] = workspace["created_at"].isoformat()
        if workspace["updated_at"] and hasattr(workspace["updated_at"], "isoformat"):
            workspace["updated_at"] = workspace["updated_at"].isoformat()

        json_data = json.dumps(workspace, indent=2, default=_json_default)
        return send_file(
            io.BytesIO(json_data.encode('utf-8')),
            mimetype='application/json',
            as_attachment=True,
            download_name=f"workspace_{ws_id}_{workspace['name']}.json"
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─────────────────────── RUN ────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))