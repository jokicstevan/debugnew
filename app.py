"""
GRPS Web — Belgrade Delivery Route Planner
Flask backend: auth, optimization, OSRM, PDF, Excel import
"""

import os, copy, math, json, io, tempfile, threading, time
import requests
import numpy as np
from collections import defaultdict
from datetime import datetime
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

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "grps-secret-2024-change-me")
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB upload limit
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
REPORT_FOLDER = os.path.join(os.path.dirname(__file__), "reports")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(REPORT_FOLDER, exist_ok=True)

# ─────────────────────────── AUTH ────────────────────────────────────────────

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


@app.route("/api/here_debug")
def here_debug():
    """Shows the raw HERE API response for debugging."""
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
            params={
                "apiKey":        HERE_API_KEY,
                "departureTime": _here_departure_time(),
            },
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
    """Health-check endpoint — shows which routing services are configured and reachable."""
    import time as _time

    result = {
        "here_key_set":   bool(HERE_API_KEY),
        "here_reachable": False,
        "osrm_reachable": False,
        "routing_source": "haversine",
        "details":        {},
    }

    # Test HERE with a minimal 2-point matrix (Belgrade city centre → Novi Beograd)
    if HERE_API_KEY:
        try:
            t0 = _time.time()
            test_locs = [
                {"lat": 44.8178, "lng": 20.4569},  # Trg Republike
                {"lat": 44.8125, "lng": 20.4612},  # Kalemegdan
            ]
            d, t = fetch_here_matrix(test_locs)
            elapsed = round(_time.time() - t0, 2)
            if d is not None:
                result["here_reachable"] = True
                result["routing_source"] = "here"
                result["details"]["here"] = {
                    "status":       "ok",
                    "response_sec": elapsed,
                    "sample_dist_km": round(d[0][1], 3),
                    "sample_time_min": round(t[0][1], 2),
                }
            else:
                result["details"]["here"] = {"status": "error — matrix returned None"}
        except Exception as e:
            result["details"]["here"] = {"status": f"exception: {e}"}

    # Test OSRM with the same two points
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
                "status":          "ok",
                "response_sec":    elapsed,
                "sample_dist_km":  round(d[0][1], 3),
                "sample_time_min": round(t[0][1], 2),
            }
        else:
            result["details"]["osrm"] = {"status": "unavailable"}
    except Exception as e:
        result["details"]["osrm"] = {"status": f"exception: {e}"}

    result["details"]["haversine"] = {"status": "always available (straight-line fallback)"}

    return jsonify(result)

# ─────────────────────── GEOCODING ───────────────────────────────────────────

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

# ─────────────────────── EXCEL IMPORT ────────────────────────────────────────

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
        # Detect package columns: packages#1/packages#2/packages#3 or legacy 'packages'
        pkg_cols = [k for k in ["packages#1", "packages#2", "packages#3"] if k in hmap]
        if not pkg_cols:
            if "packages" in hmap:
                pkg_cols = ["packages"]
            else:
                return jsonify({"ok": False, "error": "Missing columns: Packages#1 / Packages#2 / Packages#3"})

        import re
        parsed, errors = [], []
        for rn, row in enumerate(rows_iter, 2):
            def g(k):
                v = row[hmap[k]] if hmap[k] < len(row) else None
                return str(v).strip() if v is not None else ""
            name, addr = g("customer"), g("address")
            if not name or not addr:
                errors.append(f"Row {rn}: missing name/address")
                continue
            pkg_counts = []
            for k in pkg_cols:
                try:
                    pkg_counts.append(max(0, int(float(g(k) or 0))))
                except:
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
            parsed.append({"name": name, "address": addr,
                           "pkg_counts": pkg_counts,
                           "unloading_time": unloading,
                           "time_window": tw})
        return jsonify({"ok": True, "rows": parsed, "errors": errors})
    except ImportError:
        return jsonify({"ok": False, "error": "openpyxl not installed"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

# ─────────────────────── OSRM MATRIX ─────────────────────────────────────────

# Serbia bounding box
SERBIA_BBOX = {"lat_min": 41.85, "lat_max": 46.20,
               "lng_min": 18.80, "lng_max": 23.00}

def in_serbia(lat, lng):
    """Return True if coordinates are within Serbia."""
    b = SERBIA_BBOX
    return b["lat_min"] <= lat <= b["lat_max"] and b["lng_min"] <= lng <= b["lng_max"]

HERE_API_KEY = os.environ.get("HERE_API_KEY", "")


def _here_departure_time():
    """Return current UTC time in ISO 8601 format required by HERE API."""
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


# ── HERE Routing (live traffic) ───────────────────────────────────────────────

def fetch_here_matrix(locations):
    """Build N×N matrix using HERE Router v8 /routes with live traffic.
    Avoids the async Matrix API (which requires OAuth2 for polling).
    Uses one API call per origin row — fast enough for ≤25 locations."""
    if not HERE_API_KEY:
        return None, None
    n = len(locations)
    dist_mat = [[0.0]*n for _ in range(n)]
    time_mat = [[0.0]*n for _ in range(n)]

    dep_time = _here_departure_time()

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
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
                                    params=params, timeout=10)
                if resp.status_code == 200:
                    routes = resp.json().get("routes", [])
                    if routes:
                        summary = routes[0]["sections"][0]["summary"]
                        dist_mat[i][j] = summary["length"]   / 1000.0  # m → km
                        time_mat[i][j] = summary["duration"] / 60.0    # s → min
                        continue
                print(f"[HERE matrix] ({i},{j}) failed: {resp.status_code} {resp.text[:100]}")
                return None, None   # fail fast — fall back to OSRM
            except Exception as e:
                print(f"[HERE matrix] ({i},{j}) exception: {e}")
                return None, None

    print(f"[HERE matrix] ✅ {n}×{n} matrix built with live traffic")
    return dist_mat, time_mat


def _decode_here_polyline(encoded):
    """Decode HERE flexible-polyline → list of (lat, lng). Handles 2D and 3D."""
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
    _, idx    = _uint(encoded, idx)          # version
    hdr, idx  = _uint(encoded, idx)          # header
    factor    = 10 ** (hdr & 0xF)            # lat/lng precision (bits 0-3)
    third_dim = (hdr >> 4) & 0x7             # 3D type: 0=absent, else altitude/elevation/etc.

    coords, lat, lng = [], 0, 0
    while idx < len(encoded):
        dlat, idx = _sint(encoded, idx)
        dlng, idx = _sint(encoded, idx)
        if third_dim:                        # consume altitude delta to keep pointer in sync
            _, idx = _sint(encoded, idx)
        lat += dlat; lng += dlng
        coords.append((lat / factor, lng / factor))
    return coords


def fetch_here_route(waypoints):
    """Fetch road geometry from HERE Router v8 (live traffic).
    Concatenates all sections so multi-stop routes display correctly on the map."""
    if not HERE_API_KEY:
        return None, None, None
    origin = f"{waypoints[0][1]},{waypoints[0][0]}"
    dest   = f"{waypoints[-1][1]},{waypoints[-1][0]}"
    # HERE v8 expects repeated `via=lat,lng` query params, NOT `via[0]=…`.
    # Passing a list makes `requests` emit: &via=lat1,lng1&via=lat2,lng2
    via_list = [f"{lat},{lng}" for lng, lat in waypoints[1:-1]]
    params = {
        "apiKey":        HERE_API_KEY,
        "transportMode": "car",
        "routingMode":   "fast",
        "departureTime": _here_departure_time(),
        "origin":        origin,
        "destination":   dest,
        "return":        "polyline,summary",
    }
    if via_list:
        params["via"] = via_list
    try:
        req = requests.Request("GET", "https://router.hereapi.com/v8/routes",
                               params=params).prepare()
        print(f"[HERE route] URL: {req.url[:300]}")
        resp = requests.get("https://router.hereapi.com/v8/routes",
                            params=params, timeout=20)
        if resp.status_code != 200:
            print(f"[HERE route] failed: {resp.status_code} {resp.text[:200]}")
            return None, None, None
        routes = resp.json().get("routes", [])
        if not routes:
            print("[HERE route] no routes returned")
            return None, None, None
        # Concatenate geometry from ALL sections (one per leg between stops).
        # Adjacent sections share an endpoint (junction stop), so skip the
        # duplicate first point on every section after the first.
        geom, dist_km, dur_min = [], 0.0, 0.0
        for section in routes[0]["sections"]:
            summary   = section.get("summary", {})
            dist_km  += summary.get("length",   0) / 1000.0
            dur_min  += summary.get("duration", 0) / 60.0
            raw_poly  = section.get("polyline")
            if not raw_poly:
                continue
            pts  = _decode_here_polyline(raw_poly)
            pts  = pts[1:] if geom else pts   # drop duplicate junction point
            geom += [(p[1], p[0]) for p in pts]
        if not geom:
            print("[HERE route] empty geometry after decoding")
            return None, None, None
        print(f"[HERE route] OK {len(geom)} pts {dist_km:.1f}km {dur_min:.1f}min")
        return geom, dist_km, dur_min
    except Exception as e:
        print(f"[HERE route] exception: {e}")
        return None, None, None


# ── OSRM Routing (fallback, no live traffic) ──────────────────────────────────

def fetch_osrm_matrix(locations):
    """Fetch N×N road distance+time matrix from OSRM /table."""
    coords = ";".join(f"{loc['lng']},{loc['lat']}" for loc in locations)
    url    = f"https://router.project-osrm.org/table/v1/driving/{coords}"
    delays = [2, 5, 10, 15]
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
            n = len(locations)
            dist = [[0.0]*n for _ in range(n)]
            tdur = [[0.0]*n for _ in range(n)]
            for i in range(n):
                for j in range(n):
                    d = data["distances"][i][j]
                    t = data["durations"][i][j]
                    dist[i][j] = (d / 1000.0) if d else 0.0
                    tdur[i][j] = (t / 60.0)   if t else 0.0
            return dist, tdur
        except Exception:
            time.sleep(delays[attempt])
    return None, None


def haversine(lat1, lon1, lat2, lon2):
    R    = 6371
    la1, la2 = math.radians(lat1), math.radians(lat2)
    a    = (math.sin((la2-la1)/2)**2
            + math.cos(la1)*math.cos(la2)*math.sin(math.radians(lon2-lon1)/2)**2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def build_haversine_matrix(locations):
    n = len(locations)
    dist = [[0.0]*n for _ in range(n)]
    tdur = [[0.0]*n for _ in range(n)]
    for i in range(n):
        for j in range(i+1, n):
            d = haversine(locations[i]["lat"], locations[i]["lng"],
                          locations[j]["lat"], locations[j]["lng"])
            t = d / 30 * 60
            dist[i][j] = dist[j][i] = d
            tdur[i][j] = tdur[j][i] = t
    return dist, tdur


def straight_line_geometry(waypoints):
    """Straight-line fallback when all routers fail."""
    geom = [(lng, lat) for lng, lat in waypoints]
    dist = sum(haversine(waypoints[i][1], waypoints[i][0],
                         waypoints[i+1][1], waypoints[i+1][0])
               for i in range(len(waypoints)-1))
    return geom, dist, dist / 30 * 60


def fetch_osrm_route(waypoints):
    """Fetch road geometry from OSRM. Falls back to straight-line."""
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


def fetch_best_matrix(locations):
    """Try HERE (live traffic) → OSRM → haversine. Returns (dist, time, source)."""
    if HERE_API_KEY:
        d, t = fetch_here_matrix(locations)
        if d is not None:
            return d, t, "here"
    d, t = fetch_osrm_matrix(locations)
    if d is not None:
        return d, t, "osrm"
    d, t = build_haversine_matrix(locations)
    return d, t, "haversine"


def fetch_best_route(waypoints):
    """Fetch road geometry for map display.
    Uses HERE route geometry (exact roads HERE calculated) when key is set,
    falls back to OSRM, then straight-line."""
    if HERE_API_KEY:
        g, d, t = fetch_here_route(waypoints)
        if g:
            return g, d, t, "here"
    g, d, t = fetch_osrm_route(waypoints)
    sl_g, sl_d, sl_t = straight_line_geometry(waypoints)
    src = "haversine" if (g == sl_g) else "osrm"
    return g, d, t, src


# ─────────────────────── VRPTW CORE ──────────────────────────────────────────
#
# INDEX CONVENTION (simple, no offsets):
#   dist/time matrix indices:
#     0 .. n_depots-1          → depots
#     n_depots .. n_depots+n_c-1 → customers
#   customer list (0-based):
#     customers[i]  ←→  matrix index (n_depots + i)
#   demands[i] = packages for customers[i]
#
# All functions receive `n_depots` so they can compute matrix indices directly.

SERVICE_TIME = 10  # fallback default unloading minutes (used when no per-customer value)

# ── Cost parameters (Serbia, 2025) ───────────────────────────────────────────
DRIVER_WAGE_RSD_PER_HOUR = 900.0   # gross driver wage, RSD/hour (~7.5 EUR)
FUEL_PRICE_RSD_PER_LITRE = 200.0   # diesel pump price, RSD/litre (~1.70 EUR)

# ── Weight & load-dependent fuel parameters ──────────────────────────────────
# Realistic package weights (kg) per type — used for weight capacity check
# and for load-dependent fuel consumption calculation.
# Type 1: small parcel ~5 kg, Type 2: medium box ~15 kg, Type 3: large item ~30 kg
DEFAULT_PKG_WEIGHTS_KG = [5.0, 15.0, 30.0]

# Load factor: each extra 1 000 kg of cargo increases fuel consumption by ~3 %
# (typical diesel van/truck: +2–4 % per 1 000 kg payload — we use 3 %)
FUEL_LOAD_FACTOR_PER_1000KG = 0.03  # 3 % increase per 1 000 kg


def _mat_idx(cust_i, n_depots):
    """Matrix index for 0-based customer index."""
    return n_depots + cust_i


def route_time(route_mat_indices, depot_mat_idx, dist_mat, time_mat, tw, svc,
               start_time=None, svc_map=None):
    """Walk route from depot, return (feasible, schedule).
    route_mat_indices : list of matrix indices of customers in visit order.
    start_time        : departure minute from depot; defaults to depot TW open time.
    svc_map           : dict {matrix_index: unloading_minutes}; falls back to svc scalar.
    Returns (feasible: bool, schedule: list of dicts).
    """
    sched, feasible = [], True
    t    = start_time if start_time is not None else tw[depot_mat_idx][0]
    prev = depot_mat_idx
    for c in route_mat_indices:
        t += time_mat[prev][c]
        tw_s, tw_e = tw[c]
        viol  = max(0.0, t - tw_e)
        if viol > 0:
            feasible = False
        wait       = max(0.0, tw_s - t)
        arrival    = t
        stop_svc   = svc_map[c] if (svc_map and c in svc_map) else svc
        t          = max(t, tw_s) + stop_svc
        sched.append({"customer_mat": c, "arrival": arrival,
                       "wait": wait, "violation": viol, "depart": t,
                       "service_time": stop_svc})
        prev = c
    return feasible, sched


def latest_feasible_departure(route_mat_indices, depot_mat_idx,
                               dist_mat, time_mat, tw, svc, svc_map=None):
    """Find the latest departure minute from depot within depot hours that keeps
    all customer TW constraints feasible (5-minute precision binary search).
    Drivers depart as late as possible to minimise wage cost.
    """
    if not route_mat_indices:
        return tw[depot_mat_idx][0]
    depot_open  = tw[depot_mat_idx][0]
    depot_close = tw[depot_mat_idx][1]
    ok, _ = route_time(route_mat_indices, depot_mat_idx, dist_mat, time_mat,
                        tw, svc, depot_open, svc_map)
    if not ok:
        return depot_open
    best = depot_open
    lo, hi = depot_open, depot_close
    while hi - lo > 5:
        mid = (lo + hi) // 2
        ok, _ = route_time(route_mat_indices, depot_mat_idx, dist_mat, time_mat,
                            tw, svc, mid, svc_map)
        if ok:
            best = mid
            lo   = mid
        else:
            hi   = mid
    return best


def route_working_minutes(route_mat_indices, depot_mat_idx,
                           dist_mat, time_mat, tw, svc, start_time, svc_map=None):
    """Total working minutes: departure -> last customer depart -> return depot."""
    if not route_mat_indices:
        return 0.0
    _, sched = route_time(route_mat_indices, depot_mat_idx, dist_mat, time_mat,
                           tw, svc, start_time, svc_map)
    last_depart = sched[-1]["depart"] if sched else start_time
    return_time = last_depart + time_mat[route_mat_indices[-1]][depot_mat_idx]
    return max(0.0, return_time - start_time)


def route_dist(route_mat_indices, depot_mat_idx, dist_mat):
    """Total distance for a route (depot → stops → depot)."""
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
    """Compute total fuel (litres) for a route with load-shedding after each stop.

    The van starts fully loaded and unloads each customer's cargo on arrival,
    so subsequent legs are driven with a lighter vehicle — reducing fuel burn.

    route_mat_indices : list of matrix indices of customers in visit order
    depot_mat_idx     : matrix index of the depot
    dist_mat          : N×N road distance matrix (km)
    demands_kg        : list indexed by (mat_idx - n_depots)
    n_depots          : number of depots (offset between mat index and demands_kg)
    fuel_per_100km_fn : callable(payload_kg) → L/100 km for the vehicle
    """
    if not route_mat_indices:
        return 0.0

    # Start fully loaded
    remaining_kg = sum(
        demands_kg[c - n_depots]
        for c in route_mat_indices
        if 0 <= (c - n_depots) < len(demands_kg)
    )

    total_litres = 0.0

    # Leg: depot → first customer
    leg_km = dist_mat[depot_mat_idx][route_mat_indices[0]]
    total_litres += leg_km * fuel_per_100km_fn(remaining_kg) / 100.0

    # Unload at first customer, then drive subsequent legs
    prev = route_mat_indices[0]
    drop = demands_kg[prev - n_depots] if 0 <= (prev - n_depots) < len(demands_kg) else 0.0
    remaining_kg = max(0.0, remaining_kg - drop)

    for c in route_mat_indices[1:]:
        leg_km = dist_mat[prev][c]
        total_litres += leg_km * fuel_per_100km_fn(remaining_kg) / 100.0
        # Unload at this customer
        drop = demands_kg[c - n_depots] if 0 <= (c - n_depots) < len(demands_kg) else 0.0
        remaining_kg = max(0.0, remaining_kg - drop)
        prev = c

    # Final leg: last customer → depot (empty or nearly empty)
    leg_km = dist_mat[prev][depot_mat_idx]
    total_litres += leg_km * fuel_per_100km_fn(remaining_kg) / 100.0

    return total_litres


def best_depot_for_route(route_mat_indices, n_depots, dist_mat):
    """Return the depot index (0..n_depots-1) that minimises route distance."""
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
    """Immutable-style VRP state.
    routes[v]  : list of matrix indices for vehicle v's customers
    depot_of[v]: depot matrix index (0..n_depots-1) for vehicle v
    use_tw     : when True, TW lateness is a soft penalty (100x) not hard-inf
    svc_map    : {matrix_index: unloading_minutes} per customer
    """
    def __init__(self, routes, depot_of, dist_mat, time_mat,
                 demands, fleet, tw, n_depots, svc=SERVICE_TIME,
                 use_tw=False, svc_map=None, demands_kg=None, obj_weights=None,
                 use_volume_cap=True, use_weight_cap=True,
                 fuel_price_rsd_l=None, driver_wage_rsd_h=None,
                 fuel_load_factor=None):
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
        self.svc_map    = svc_map or {}
        # obj_weights: dict controlling which cost components enter the objective.
        # Keys: "fuel" (bool), "wages" (bool), "distance" (bool), "vehicles" (bool)
        # At least one must be True; the optimizer minimises the selected sum.
        self.obj_weights = obj_weights or {"fuel": True, "wages": True, "distance": False, "vehicles": False}
        # Constraint toggles: when False, the corresponding hard constraint is ignored
        self.use_volume_cap = use_volume_cap
        self.use_weight_cap = use_weight_cap
        self.fuel_price_rsd_l  = fuel_price_rsd_l  if fuel_price_rsd_l  is not None else FUEL_PRICE_RSD_PER_LITRE
        self.driver_wage_rsd_h = driver_wage_rsd_h if driver_wage_rsd_h is not None else DRIVER_WAGE_RSD_PER_HOUR
        self.fuel_load_factor  = fuel_load_factor  if fuel_load_factor  is not None else FUEL_LOAD_FACTOR_PER_1000KG

    def fuel_per_100km(self, v, payload_kg=0.0):
        """Base fuel + linear load surcharge.
        payload_kg = total cargo weight on this vehicle for this route.
        Formula: L/100km = base * (1 + fuel_load_factor * payload_kg / 1000)
        """
        if v < len(self.fleet):
            base = float(self.fleet[v].get("fuel_consumption", 10.0))
        else:
            base = 10.0
        surcharge = 1.0 + self.fuel_load_factor * payload_kg / 1000.0
        return base * surcharge

    def weight_cap(self, v):
        """Max payload weight (kg) for vehicle v. 0 = unlimited."""
        if v < len(self.fleet):
            return float(self.fleet[v].get("weight_capacity", 0.0))
        return 0.0

    def route_weight(self, v):
        """Total cargo weight (kg) for vehicle v."""
        return sum(self.fleet[v].get("pkg_weights", DEFAULT_PKG_WEIGHTS_KG)[0] * 0
                   for _ in [])  # placeholder — calculated via demands_kg

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
            self.fuel_load_factor)

    def cap(self, v):
        return self.fleet[v]["capacity"] if v < len(self.fleet) else float("inf")

    def load(self, v):
        """Total volumetric load on vehicle v."""
        return sum(self.demands[c - self.n_depots]
                   for c in self.routes[v]
                   if 0 <= (c - self.n_depots) < len(self.demands))

    def weight_load(self, v):
        """Total weight load (kg) on vehicle v."""
        return sum(self.demands_kg[c - self.n_depots]
                   for c in self.routes[v]
                   if 0 <= (c - self.n_depots) < len(self.demands_kg))

    def reassign_depots(self):
        for v, route in enumerate(self.routes):
            if route:
                self.depot_of[v] = best_depot_for_route(
                    route, self.n_depots, self.dist_mat)

    def objective(self):
        """Minimise a user-selected combination of cost components.

        Hard constraints (enforced unless the corresponding toggle is disabled):
          - Volume capacity overload → inf  (if use_volume_cap)
          - Weight capacity overload → inf  (if use_weight_cap)
          - TW violation (hard mode) → inf  (if not use_tw)

        Selectable objective components (via self.obj_weights):
          "fuel"     — fuel cost in RSD (load-dependent)
          "wages"    — driver wage cost in RSD
          "distance" — total route distance in km (normalised to RSD scale)
          "vehicles" — number of vehicles used (penalty per active vehicle)

        At least one component is always active.  If none are checked the
        optimizer falls back to minimising fuel + wages.
        """
        ow          = self.obj_weights or {}
        do_fuel     = ow.get("fuel",     True)
        do_wages    = ow.get("wages",    True)
        do_dist     = ow.get("distance", False)
        do_vehicles = ow.get("vehicles", False)
        # Fallback: if user unchecked everything, use fuel+wages
        if not any([do_fuel, do_wages, do_dist, do_vehicles]):
            do_fuel = do_wages = True

        # Distance normalisation: 1 km ≈ cost of driving it with avg fuel & wages
        # Approximately: 10L/100km × 200 RSD/L = 20 RSD/km for fuel alone.
        DIST_RSD_PER_KM = 20.0
        # Vehicle penalty: using one extra vehicle costs roughly half a work-day
        # of wages as an overhead (depot time, admin, etc.) ≈ 4h × 900 RSD/h
        VEHICLE_PENALTY_RSD = 3600.0

        TW_PENALTY = 100.0   # RSD-equivalent penalty per late minute
        total = 0.0
        for v, route in enumerate(self.routes):
            if not route:
                continue
            if self.use_volume_cap and self.load(v) > self.cap(v):
                return float("inf")
            wc = self.weight_cap(v)
            if self.use_weight_cap and wc > 0 and self.weight_load(v) > wc:
                return float("inf")
            # Minimum departure load penalty (soft — large but not inf so solver can converge)
            min_vol_pct = float(self.fleet[v].get("min_vol_pct", 0.0)) if v < len(self.fleet) else 0.0
            min_wt_pct  = float(self.fleet[v].get("min_wt_pct",  0.0)) if v < len(self.fleet) else 0.0
            if min_vol_pct > 0:
                vol_cap = self.cap(v)
                if vol_cap < 9990:  # skip for unlimited capacity vehicles
                    vol_fill_pct = 100.0 * self.load(v) / vol_cap if vol_cap > 0 else 100.0
                    if vol_fill_pct < min_vol_pct:
                        total += 50000.0 * (min_vol_pct - vol_fill_pct)
            if min_wt_pct > 0 and wc > 0:
                wt_fill_pct = 100.0 * self.weight_load(v) / wc if wc > 0 else 100.0
                if wt_fill_pct < min_wt_pct:
                    total += 50000.0 * (min_wt_pct - wt_fill_pct)
            depot = self.depot_of[v]
            start = latest_feasible_departure(
                route, depot, self.dist_mat, self.time_mat, self.tw, self.svc,
                self.svc_map)
            _, sched = route_time(route, depot, self.dist_mat, self.time_mat,
                                   self.tw, self.svc, start, self.svc_map)
            tw_viol = sum(e["violation"] for e in sched)
            if not self.use_tw and tw_viol > 0:
                return float("inf")
            dist_km    = route_dist(route, depot, self.dist_mat)

            if do_fuel:
                # Fuel calculated leg-by-leg: payload shrinks after each delivery,
                # so early deliveries reward routes that drop off heavy stops first.
                fuel_litres = route_fuel_litres(
                    route, depot, self.dist_mat,
                    self.demands_kg, self.n_depots,
                    lambda kg, _v=v: self.fuel_per_100km(_v, kg)
                )
                total += fuel_litres * self.fuel_price_rsd_l
            if do_wages:
                work_mins = route_working_minutes(
                    route, depot, self.dist_mat, self.time_mat, self.tw, self.svc,
                    start, self.svc_map)
                total += (work_mins / 60.0) * self.driver_wage_rsd_h
            if do_dist:
                total += dist_km * DIST_RSD_PER_KM
            if do_vehicles:
                total += VEHICLE_PENALTY_RSD
            if self.use_tw:
                total += tw_viol * TW_PENALTY
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



# ─── ALNS operators ──────────────────────────────────────────────────────────

def _ins_cost(route, pos, c, state, depot):
    """Insertion cost of customer c at position pos in route."""
    new_r = route[:pos] + [c] + route[pos:]
    ok, _ = route_time(new_r, depot, state.dist_mat, state.time_mat, state.tw, state.svc,
                        svc_map=state.svc_map)
    if not ok:
        return float("inf")
    prev = route[pos-1] if pos > 0 else depot
    nxt  = route[pos]   if pos < len(route) else depot
    return (state.dist_mat[prev][c] + state.dist_mat[c][nxt]
            - state.dist_mat[prev][nxt])


def _rand_remove(state, rng):
    s = state.copy()
    all_c = [(v, i, c) for v, r in enumerate(s.routes) for i, c in enumerate(r)]
    if not all_c:
        return s
    n_rem = int(rng.integers(1, max(2, len(all_c)//4)))
    chosen = [all_c[i] for i in rng.choice(len(all_c),
                                             size=min(n_rem, len(all_c)),
                                             replace=False)]
    for v, pos, _ in sorted(chosen, key=lambda x: (x[0], x[1]), reverse=True):
        s.routes[v].pop(pos)
    return s


def _worst_remove(state, rng):
    s = state.copy()
    costs = []
    for v, route in enumerate(s.routes):
        d = s.depot_of[v]
        for i, c in enumerate(route):
            prev = route[i-1] if i > 0 else d
            nxt  = route[i+1] if i < len(route)-1 else d
            saving = (s.dist_mat[prev][c] + s.dist_mat[c][nxt]
                      - s.dist_mat[prev][nxt])
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
    """Remove customers from capacity-overloaded vehicles."""
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


def _greedy_insert(state, rng):
    s = state.copy()
    routed   = {c for r in s.routes for c in r}
    all_cust = {state.n_depots + i for i in range(len(state.demands))}
    unrouted = list(all_cust - routed)
    rng.shuffle(unrouted)
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
            for pos in range(len(s.routes[v]) + 1):
                cost = _ins_cost(s.routes[v], pos, c, state, d)
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
                for pos in range(len(s.routes[v]) + 1):
                    cost = _ins_cost(s.routes[v], pos, c, state, d)
                    if cost < float("inf"):
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


# ─── Helpers ─────────────────────────────────────────────────────────────────

def mins_to_hhmm(m):
    t = int(round(m))
    return f"{t//60:02d}:{t%60:02d}"


def optimize_nn(dist_mat, time_mat, n_depots, n_cust, tw, demands,
                use_tw=False, svc_map=None, demands_kg=None, obj_weights=None,
                use_volume_cap=True, use_weight_cap=True,
                fuel_price_rsd_l=None, driver_wage_rsd_h=None, fuel_load_factor=None):
    """Single-vehicle nearest-neighbour. Returns VRPState."""
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
                    fuel_load_factor=fuel_load_factor)


def optimize_2opt(dist_mat, time_mat, n_depots, n_cust, tw, demands,
                  use_tw=False, svc_map=None, demands_kg=None, obj_weights=None,
                  use_volume_cap=True, use_weight_cap=True,
                  fuel_price_rsd_l=None, driver_wage_rsd_h=None, fuel_load_factor=None):
    """Single-vehicle 2-opt. Returns VRPState."""
    s = optimize_nn(dist_mat, time_mat, n_depots, n_cust, tw, demands,
                    use_tw=use_tw, svc_map=svc_map, demands_kg=demands_kg,
                    obj_weights=obj_weights,
                    use_volume_cap=use_volume_cap, use_weight_cap=use_weight_cap,
                    fuel_price_rsd_l=fuel_price_rsd_l, driver_wage_rsd_h=driver_wage_rsd_h,
                    fuel_load_factor=fuel_load_factor)
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


def optimize_alns(dist_mat, time_mat, n_depots, n_cust, tw, demands,
                  fleet, max_iter=300, temperature=150.0, use_tw=False, svc_map=None,
                  demands_kg=None, obj_weights=None, use_volume_cap=True, use_weight_cap=True,
                  fuel_price_rsd_l=None, driver_wage_rsd_h=None, fuel_load_factor=None):
    """ALNS multi-vehicle optimiser. Returns VRPState."""
    demands_kg = demands_kg or [0.0] * len(demands)
    num_v  = len(fleet)
    all_ci = list(range(n_depots, n_depots + n_cust))

    # Initial assignment: fill vehicles greedily by volume + weight capacity
    routes   = [[] for _ in range(num_v)]
    loads    = [0.0] * num_v
    wloads   = [0.0] * num_v
    for ci in all_ci:
        dem    = demands[ci - n_depots]
        kg     = demands_kg[ci - n_depots] if (ci - n_depots) < len(demands_kg) else 0.0
        def fits(v, dem=dem, kg=kg):
            vol_ok    = (not use_volume_cap) or (loads[v] + dem <= fleet[v]["capacity"])
            wc        = fleet[v].get("weight_capacity", 0.0)
            weight_ok = (not use_weight_cap) or (wc == 0) or (wloads[v] + kg <= wc)
            return vol_ok and weight_ok
        best_v = min(range(num_v),
                     key=lambda v: loads[v] if fits(v) else float("inf"))
        routes[best_v].append(ci)
        loads[best_v]  += dem
        wloads[best_v] += kg

    # NN order within each vehicle's initial assignment
    ordered = []
    for v, route in enumerate(routes):
        if not route:
            ordered.append([])
            continue
        depot = 0   # will be reassigned by reassign_depots
        unvis, cur, nr = route[:], depot, []
        while unvis:
            nn = min(unvis, key=lambda x: dist_mat[cur][x])
            nr.append(nn); unvis.remove(nn); cur = nn
        ordered.append(nr)

    depot_of = [0] * num_v
    state = VRPState(ordered, depot_of, dist_mat, time_mat,
                     demands, fleet, tw, n_depots,
                     use_tw=use_tw, svc_map=svc_map, demands_kg=demands_kg,
                     obj_weights=obj_weights,
                     use_volume_cap=use_volume_cap, use_weight_cap=use_weight_cap,
                     fuel_price_rsd_l=fuel_price_rsd_l, driver_wage_rsd_h=driver_wage_rsd_h,
                     fuel_load_factor=fuel_load_factor)
    state.reassign_depots()

    best     = state.copy()
    best_obj = best.objective()
    cur_obj  = best_obj
    temp     = temperature
    cooling  = 0.995

    destroy = [_rand_remove, _worst_remove, _tw_remove, _cap_remove]
    repair  = [_greedy_insert, _regret_insert]
    dw      = [1.0] * 4
    rw      = [1.0] * 2
    rng     = np.random.default_rng(42)

    def sel(w):
        t = sum(w); r = float(rng.random()) * t; cs = 0
        for i, wi in enumerate(w):
            cs += wi
            if cs >= r:
                return i
        return len(w) - 1

    for _ in range(max_iter):
        di, ri   = sel(dw), sel(rw)
        dest     = destroy[di](state, rng)
        cand     = repair[ri](dest, rng)
        cand_obj = cand.objective()
        delta    = cand_obj - cur_obj
        if delta < 0 or float(rng.random()) < math.exp(-delta / max(temp, 1e-9)):
            state, cur_obj = cand, cand_obj
            if cur_obj < best_obj:
                best, best_obj = state.copy(), cur_obj
        temp *= cooling

    # Final depot reassignment on the winner
    best.reassign_depots()
    return best


# ─────────────────────── OPTIMIZE ENDPOINT ───────────────────────────────────

@app.route("/api/optimize", methods=["POST"])
@login_required
def optimize():
    try:
        data = request.json
        if not data:
            return jsonify({"ok": False, "error": "No data received"})

        # Parse depots (list) with legacy single-depot fallback
        depots_raw  = data.get("depots") or []
        if not depots_raw and data.get("depot"):
            depots_raw = [data["depot"]]
        customers   = data.get("customers", [])
        fleet_cfg   = data.get("fleet", [])
        algorithm   = data.get("algorithm", "ALNS")
        use_tw      = data.get("use_time_windows", False)
        max_iter    = int(data.get("max_iterations", 300))
        temperature = float(data.get("temperature", 150.0))
        # Objective weights: which cost components to minimise
        raw_ow      = data.get("obj_weights", {})
        obj_weights = {
            "fuel":     bool(raw_ow.get("fuel",     True)),
            "wages":    bool(raw_ow.get("wages",    True)),
            "distance": bool(raw_ow.get("distance", False)),
            "vehicles": bool(raw_ow.get("vehicles", False)),
        }
        # Ensure at least one component is active
        if not any(obj_weights.values()):
            obj_weights["fuel"] = obj_weights["wages"] = True
        # Cost parameters — user-editable, fall back to Serbia defaults
        fuel_price_rsd_l      = float(data.get("fuel_price_rsd_l",  FUEL_PRICE_RSD_PER_LITRE))
        driver_wage_rsd_h     = float(data.get("driver_wage_rsd_h", DRIVER_WAGE_RSD_PER_HOUR))
        fuel_load_factor_pct  = float(data.get("fuel_load_factor_pct", FUEL_LOAD_FACTOR_PER_1000KG * 100))
        fuel_load_factor      = fuel_load_factor_pct / 100.0   # convert % → fraction
        # Hard constraint toggles
        use_volume_cap = bool(data.get("use_volume_capacity", True))
        use_weight_cap = bool(data.get("use_weight_capacity", True))

        if not depots_raw:
            return jsonify({"ok": False, "error": "No depot provided"})
        if not customers:
            return jsonify({"ok": False, "error": "No customers provided"})

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
            return jsonify({"ok": False,
                "error": f"Outside Serbia: {', '.join(outside[:5])}."})

        # all_locs for matrix: [depots, original customers] (unique locations)
        # After split-delivery expansion we remap sub-order matrix indices
        # to the corresponding original customer row — no extra matrix rows needed.
        all_locs_orig = depots + customers

        # Phase 1: distance/time matrix — HERE (live traffic) → OSRM → haversine
        dist_mat, time_mat, matrix_source = fetch_best_matrix(all_locs_orig)

        # Temporary tw / all_locs for demand calculations below
        all_locs = all_locs_orig

        # Package type sizes (m³) passed from the frontend
        pkg_sizes = data.get("pkg_sizes", [0.10, 0.30, 0.60])
        while len(pkg_sizes) < 3:
            pkg_sizes.append(0.10)

        # demands[i] = total volume (m³) for customer i (0-based)
        # Each customer carries pkg_counts[0..2] packages of each type
        def customer_volume(c):
            counts = c.get("pkg_counts", [0, 0, 0])
            while len(counts) < 3:
                counts.append(0)
            return sum(counts[j] * pkg_sizes[j] for j in range(3))

        demands = [max(0.0, customer_volume(c)) for c in customers]

        # Package type weights (kg) — passed from frontend or use defaults
        pkg_weights_kg = data.get("pkg_weights_kg", DEFAULT_PKG_WEIGHTS_KG)
        while len(pkg_weights_kg) < 3:
            pkg_weights_kg.append(DEFAULT_PKG_WEIGHTS_KG[len(pkg_weights_kg)])

        def customer_weight(c):
            counts = c.get("pkg_counts", [0, 0, 0])
            while len(counts) < 3:
                counts.append(0)
            return sum(counts[j] * pkg_weights_kg[j] for j in range(3))

        demands_kg = [max(0.0, customer_weight(c)) for c in customers]

        # Per-customer unloading times: {matrix_index: minutes}
        svc_map_orig = {}
        for i, c in enumerate(customers):
            ut = c.get("unloading_time", SERVICE_TIME)
            try:
                ut = max(1, int(float(ut)))
            except Exception:
                ut = SERVICE_TIME
            svc_map_orig[n_depots + i] = ut

        # ── Split-delivery expansion ──────────────────────────────────────────
        # Each customer whose demand exceeds any single vehicle capacity is split
        # into n_splits sub-orders with equal partial demand, all at the same
        # physical location.  The solver treats sub-orders as independent stops.
        #
        # sub_to_orig[sub_i]  = original customer index (0-based)
        # orig_to_mat[orig_i] = original matrix row for customer orig_i
        #                       = n_depots + orig_i  (in the n+m matrix)
        #
        # We build an *expanded* dist/time matrix:
        #   rows 0 .. n_depots-1           → depots  (unchanged)
        #   rows n_depots .. n_depots+S-1  → sub-orders (copy of original row)
        # where S = total number of sub-orders (≥ n_orig_cust).

        max_vol_cap = max(
            (float(v.get("volume_capacity", v.get("capacity", 9999))) for v in fleet_cfg),
            default=9999.0)
        max_wt_cap = max(
            (float(v.get("weight_capacity", 0)) or float("inf") for v in fleet_cfg),
            default=float("inf"))

        orig_customers = customers          # keep original list for response
        n_orig_cust    = len(customers)

        sub_to_orig  = []   # sub_i → original customer index
        exp_demands  = []   # volume per sub-order
        exp_demands_kg = [] # weight per sub-order
        exp_locs     = []   # loc dict per sub-order (same as original)

        for orig_i, c in enumerate(customers):
            vol = demands[orig_i]
            wt  = demands_kg[orig_i]

            # Number of sub-orders: driven by whichever constraint is tighter
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

        n_sub = len(sub_to_orig)   # total sub-orders (≥ n_orig_cust)

        # Build expanded matrix: copy rows/cols from original customer rows
        # New size: (n_depots + n_sub) × (n_depots + n_sub)
        orig_size = n_depots + n_orig_cust
        exp_size  = n_depots + n_sub

        def _expand_matrix(mat):
            # mat is orig_size × orig_size
            # new_mat is exp_size × exp_size
            new_mat = [[0.0] * exp_size for _ in range(exp_size)]
            for r in range(exp_size):
                orig_r = r if r < n_depots else n_depots + sub_to_orig[r - n_depots]
                for c_col in range(exp_size):
                    orig_c = c_col if c_col < n_depots else n_depots + sub_to_orig[c_col - n_depots]
                    new_mat[r][c_col] = mat[orig_r][orig_c]
            return new_mat

        dist_mat  = _expand_matrix(dist_mat)
        time_mat  = _expand_matrix(time_mat)

        # all_locs now maps to the expanded matrix rows
        all_locs   = depots + exp_locs
        n_cust     = n_sub
        demands    = exp_demands
        demands_kg = exp_demands_kg

        # Rebuild tw for expanded all_locs
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

        # svc_map for expanded sub-orders
        svc_map = {}
        for sub_i, orig_i in enumerate(sub_to_orig):
            svc_map[n_depots + sub_i] = svc_map_orig.get(n_depots + orig_i, SERVICE_TIME)

        # Precompute part number for each sub-order (1-based within its original customer)
        sub_part_num = {}
        orig_counter = {}
        for sub_i, orig_i in enumerate(sub_to_orig):
            orig_counter[orig_i] = orig_counter.get(orig_i, 0) + 1
            sub_part_num[sub_i] = orig_counter[orig_i]

        # Expand fleet — capacity is now volumetric (m³)
        vehicle_colors = ["#e74c3c","#3498db","#2ecc71","#f39c12",
                          "#9b59b6","#1abc9c","#e67e22","#e84342"]
        fleet = []
        for veh in fleet_cfg:
            for k in range(max(0, int(veh.get("count", 1)))):
                fleet.append({
                    "type":             veh.get("name", "Vehicle"),
                    "capacity":         float(veh.get("volume_capacity", veh.get("capacity", 9999))),
                    "weight_capacity":  float(veh.get("weight_capacity", 0.0)),  # 0 = unlimited
                    "color":            veh.get("color", "#3b82f6"),
                    "fuel_consumption": float(veh.get("fuel_consumption", 10.0)),
                    "min_vol_pct":      float(veh.get("min_vol_pct", 0.0)),
                    "min_wt_pct":       float(veh.get("min_wt_pct",  0.0)),
                })
        if not fleet:
            fleet = [{"type":"Vehicle","capacity":9999.0,"weight_capacity":0.0,
                      "color":"#3b82f6","fuel_consumption":10.0}]

        print(f"[optimize] {algorithm} depots={n_depots} custs={n_cust} "
              f"vehicles={len(fleet)} matrix={len(dist_mat)}x{len(dist_mat[0])} "
              f"source={matrix_source}")

        # Phase 2: run optimiser → VRPState
        if "Nearest Neighbor" in algorithm:
            state = optimize_nn(dist_mat, time_mat, n_depots, n_cust, tw, demands,
                                use_tw=use_tw, svc_map=svc_map, demands_kg=demands_kg,
                                obj_weights=obj_weights,
                                use_volume_cap=use_volume_cap, use_weight_cap=use_weight_cap,
                                fuel_price_rsd_l=fuel_price_rsd_l, driver_wage_rsd_h=driver_wage_rsd_h,
                                fuel_load_factor=fuel_load_factor)
        elif "Model 2" in algorithm:
            state = optimize_2opt(dist_mat, time_mat, n_depots, n_cust, tw, demands,
                                  use_tw=use_tw, svc_map=svc_map, demands_kg=demands_kg,
                                  obj_weights=obj_weights,
                                  use_volume_cap=use_volume_cap, use_weight_cap=use_weight_cap,
                                  fuel_price_rsd_l=fuel_price_rsd_l, driver_wage_rsd_h=driver_wage_rsd_h,
                                  fuel_load_factor=fuel_load_factor)
        else:
            # Model 1 (ALNS multi-vehicle) — also the default
            state = optimize_alns(dist_mat, time_mat, n_depots, n_cust, tw,
                                   demands, fleet, max_iter, temperature,
                                   use_tw=use_tw, svc_map=svc_map, demands_kg=demands_kg,
                                   obj_weights=obj_weights,
                                   use_volume_cap=use_volume_cap, use_weight_cap=use_weight_cap,
                                   fuel_price_rsd_l=fuel_price_rsd_l, driver_wage_rsd_h=driver_wage_rsd_h,
                                   fuel_load_factor=fuel_load_factor)

        # Assign user fleet config to state vehicles
        for v in range(len(state.routes)):
            if v < len(fleet):
                state.fleet[v] = fleet[v]

        total_dist = state.total_distance()
        # total_time is computed AFTER vehicle_routes loop from actual working hours
        # so we defer hours/mins until after the loop

        # Phase 3: geometry + build response
        vehicle_routes  = []
        real_total_dist = 0.0

        for v_idx, route in enumerate(state.routes):
            if not route:
                continue

            depot_mat = state.depot_of[v_idx]   # matrix index of depot
            dep_loc   = all_locs[depot_mat]
            veh_cfg   = fleet[v_idx] if v_idx < len(fleet) else fleet[0]
            color     = vehicle_colors[v_idx % len(vehicle_colors)]

            pts       = [dep_loc] + [all_locs[c] for c in route] + [dep_loc]
            waypoints = [(p["lng"], p["lat"]) for p in pts]
            geom, seg_dist, seg_dur, route_src = fetch_best_route(waypoints)
            real_total_dist += seg_dist or 0

            # Optimal (latest feasible) departure for this driver
            depart_min = latest_feasible_departure(
                route, depot_mat, dist_mat, time_mat, tw, SERVICE_TIME, svc_map)

            _, sched = route_time(route, depot_mat, dist_mat, time_mat, tw,
                                   SERVICE_TIME, depart_min, svc_map)
            stops = []
            for entry in sched:
                cmat     = entry["customer_mat"]
                loc      = all_locs[cmat]
                t        = loc.get("time_window", {"start":"?","end":"?"})
                sub_idx  = cmat - n_depots          # index into expanded sub-orders
                orig_i   = sub_to_orig[sub_idx] if sub_idx < len(sub_to_orig) else sub_idx
                orig_c   = orig_customers[orig_i] if orig_i < len(orig_customers) else {}
                # Count how many sub-orders this original customer was split into
                n_splits_for_cust = sub_to_orig.count(orig_i)
                c_counts = orig_c.get("pkg_counts", [0, 0, 0])
                while len(c_counts) < 3:
                    c_counts.append(0)
                # Partial counts for this sub-order
                split_counts = [round(cnt / n_splits_for_cust, 4) for cnt in c_counts]
                c_volume = demands[sub_idx]   # already the partial volume
                stops.append({
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
            # Load-dependent fuel: calculated leg-by-leg as cargo is unloaded.
            # route_weight_kg is total initial load (used for display only).
            route_weight_kg = sum(
                demands_kg[c - n_depots]
                for c in route
                if 0 <= (c - n_depots) < len(demands_kg)
            )
            base_fuel       = veh_cfg.get("fuel_consumption", 10.0)
            # Effective average L/100km (for display) — weight-average over the route
            eff_fuel        = base_fuel * (1.0 + fuel_load_factor * (route_weight_kg / 2.0) / 1000.0)
            fuel_l          = round(route_fuel_litres(
                route, depot_mat, dist_mat,
                demands_kg, n_depots,
                lambda kg: base_fuel * (1.0 + fuel_load_factor * kg / 1000.0)
            ), 2)
            fuel_cost       = round(fuel_l * fuel_price_rsd_l, 0)
            work_mins   = route_working_minutes(
                route, depot_mat, dist_mat, time_mat, tw, SERVICE_TIME, depart_min,
                svc_map)
            work_h      = round(work_mins / 60.0, 2)
            wage_cost   = round(work_h * driver_wage_rsd_h, 0)

            # Return-to-depot time
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

        # Derive total displayed time from actual driver working hours (includes
        # service time, waiting, and latest-departure logic) — consistent with wages.
        total_working_mins  = sum(vr["working_hours"] * 60 for vr in vehicle_routes)
        hours, mins         = divmod(int(round(total_working_mins)), 60)

        total_volume        = sum(demands)
        fleet_volume_capacity = (sum(v.get("volume_capacity", v.get("capacity", 0)) * v.get("count", 1)
                              for v in fleet_cfg) or 9999)
        total_fuel_used     = sum(vr["fuel_used"] for vr in vehicle_routes)
        total_fuel_cost_rsd = sum(vr["fuel_cost_rsd"] for vr in vehicle_routes)
        total_wage_cost_rsd = sum(vr["wage_cost_rsd"] for vr in vehicle_routes)
        total_cost_rsd      = total_fuel_cost_rsd + total_wage_cost_rsd
        matrix_msg = {
            "here":      "live traffic (HERE) — routes & map display",
            "osrm":      "road distances (OSRM, no live traffic)",
            "haversine": "straight-line estimates (all routers unavailable)",
        }.get(matrix_source, matrix_source)

        return jsonify({
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
        })

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[optimize] EXCEPTION: {e}\n{tb}")
        return jsonify({"ok": False, "error": str(e)})


# ─────────────────────── PDF REPORT ──────────────────────────────────────────

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
    # Fleet-wide capacity utilisation rows
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
    # Work out row index of the first capacity row (after the fixed 12 rows)
    cap_row_start = len(summary) - 4
    t.setStyle(TableStyle([
        ("FONTSIZE",(0,0),(-1,-1),9),
        ("GRID",(0,0),(-1,-1),0.5,rl_colors.grey),
        ("BACKGROUND",(0,0),(0,-1),rl_colors.HexColor("#f0f9f0")),
        ("FONTNAME",(0,0),(0,-1),"Helvetica-Bold"),
        # Highlight the new capacity rows with a light green tint
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
            # Fit within A4 width (minus margins) with max height of 280 pt
            available_w = A4[0] - 100   # 50 pt each side
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
    available_w = A4[0] - 100   # 50 pt each side
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

        # Per-vehicle map screenshot
        veh_map_b64 = vr.get("vehicle_map_image")
        if veh_map_b64:
            try:
                veh_img_bytes = base64.b64decode(veh_map_b64)
                veh_img_buf   = io.BytesIO(veh_img_bytes)
                map_h = 180   # compact height per vehicle
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
                # Highlight the new capacity columns
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

# ─────────────────────── RUN ──────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
