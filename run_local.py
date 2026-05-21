#!/usr/bin/env python3
"""
run_local.py  —  GRPS local optimization runner
================================================
Runs the full matrix-build + ALNS solver on your desktop and submits
the result to the Render deployment so the browser can pick it up
via the normal poll loop.

Usage
-----
    python run_local.py --input deliveries.xlsx --url https://debugnew-64g2.onrender.com

Required environment variables (or pass on the CLI):
    GRPS_USER       login username   (default: admin)
    GRPS_PASS       login password
    HERE_API_KEY    HERE Routing API key (optional — falls back to OSRM then haversine)

Optional flags:
    --url URL         Render service URL (default: https://debugnew-64g2.onrender.com)
    --user USER       override GRPS_USER
    --pass PASS       override GRPS_PASS
    --max-iter N      ALNS iterations (default: auto-scaled by customer count)
    --k-nearest K     spatial-filter k (default: 12)
    --no-submit       run locally only, print result JSON to stdout without submitting
"""

import argparse
import json
import os
import sys
import time

import requests


# ── CLI args ──────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="GRPS local runner")
    p.add_argument("--input",      required=True, help="Excel file to optimise")
    p.add_argument("--url",        default=os.environ.get("GRPS_URL",
                                                           "https://debugnew-64g2.onrender.com"))
    p.add_argument("--user",       default=os.environ.get("GRPS_USER", "admin"))
    p.add_argument("--password",   default=os.environ.get("GRPS_PASS", ""))
    p.add_argument("--max-iter",   type=int, default=None)
    p.add_argument("--k-nearest",  type=int, default=12)
    p.add_argument("--no-submit",  action="store_true")
    return p.parse_args()


# ── Authenticate against Render ───────────────────────────────────────────────

def login(session, base_url, username, password):
    r = session.post(f"{base_url}/login",
                     data={"username": username, "password": password},
                     allow_redirects=True)
    if "logout" in r.text.lower() or r.url.rstrip("/") == base_url.rstrip("/"):
        print(f"[auth] ✅ logged in as {username}")
        return True
    print(f"[auth] ❌ login failed (status {r.status_code})")
    return False


# ── Import Excel via Render API ───────────────────────────────────────────────

def import_excel(session, base_url, excel_path):
    print(f"[import] uploading {excel_path} …")
    with open(excel_path, "rb") as fh:
        r = session.post(f"{base_url}/api/import_excel",
                         files={"file": (os.path.basename(excel_path), fh,
                                         "application/vnd.openxmlformats-officedocument"
                                         ".spreadsheetml.sheet")})
    r.raise_for_status()
    result = r.json()
    if not result.get("ok"):
        raise RuntimeError(f"import_excel failed: {result}")
    print(f"[import] ✅ {result.get('count', '?')} customers loaded")
    return result["data"]          # the parsed request payload ready for /api/optimize


# ── Reserve a job slot on Render ─────────────────────────────────────────────

def reserve_job(session, base_url):
    r = session.post(f"{base_url}/api/optimize/reserve")
    r.raise_for_status()
    result = r.json()
    job_id = result["job_id"]
    print(f"[reserve] job_id = {job_id}")
    return job_id


# ── Run the optimisation locally ─────────────────────────────────────────────

def run_optimization_locally(data, max_iter, k_nearest):
    """
    Import app.py in-process and call _do_optimize directly.
    This reuses 100% of the same code that runs on Render, but on your
    local machine with no timeouts, more CPU, and your local HERE key.
    """
    # Point HERE key at local env so app.py picks it up
    if "HERE_API_KEY" not in os.environ:
        print("[local] ⚠️  HERE_API_KEY not set — will fall back to OSRM then haversine")

    # Patch request params
    if max_iter is not None:
        data["max_iterations"] = max_iter
    data["advanced"] = data.get("advanced", {})
    data["advanced"]["k_nearest"] = k_nearest

    print("[local] importing app module (this loads all dependencies) …")
    import importlib, sys as _sys
    # Ensure the project directory is on the path
    project_dir = os.path.dirname(os.path.abspath(__file__))
    if project_dir not in _sys.path:
        _sys.path.insert(0, project_dir)

    app_mod = importlib.import_module("app")
    _do_optimize = app_mod._do_optimize

    print("[local] ✅ app loaded — starting optimization")
    t0 = time.time()
    result = _do_optimize(data, "local-runner")
    elapsed = time.time() - t0
    print(f"[local] ✅ optimization finished in {elapsed:.1f}s")
    return result


# ── Submit result to Render ───────────────────────────────────────────────────

def submit_result(session, base_url, job_id, result):
    print(f"[submit] sending result to {base_url} …")
    r = session.post(f"{base_url}/api/optimize/submit/{job_id}",
                     json=result,
                     timeout=60)
    r.raise_for_status()
    resp = r.json()
    if resp.get("ok"):
        print(f"[submit] ✅ result accepted")
        print(f"\n✅ Open in browser: {base_url}  (job will show as done immediately)")
    else:
        print(f"[submit] ❌ server rejected result: {resp}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    if not args.password:
        import getpass
        args.password = getpass.getpass(f"Password for {args.user}@{args.url}: ")

    sess = requests.Session()
    # Fetch CSRF / session cookie
    sess.get(args.url + "/login")

    if not login(sess, args.url, args.user, args.password):
        sys.exit(1)

    # Step 1: upload Excel and get parsed data
    data = import_excel(sess, args.url, args.input)

    # Step 2: reserve a job_id on Render (so the browser can poll it)
    job_id = None
    if not args.no_submit:
        job_id = reserve_job(sess, args.url)
        print(f"\n[browser] You can open the app now — the result will appear")
        print(f"          automatically when optimisation finishes.\n")

    # Step 3: run solver locally
    result = run_optimization_locally(data, args.max_iter, args.k_nearest)

    if args.no_submit:
        print("\n[result] --no-submit: printing JSON to stdout")
        print(json.dumps(result, indent=2, default=str))
        return

    # Step 4: submit to Render
    submit_result(sess, args.url, job_id, result)


if __name__ == "__main__":
    main()
