# Cloudflare Tunnel Setup — GRPS Local Backend

This lets your Render-hosted frontend reach your desktop's Flask backend
through a secure HTTPS tunnel — no port forwarding, no static IP needed.

---

## Option A — Quick tunnel (no account, URL changes on restart)

```bash
# 1. Install cloudflared
# macOS:
brew install cloudflared

# Windows (PowerShell, run as Admin):
winget install --id Cloudflare.cloudflared

# Linux (Debian/Ubuntu):
curl -L https://pkg.cloudflare.com/cloudflare-main.gpg | sudo gpg --dearmor -o /usr/share/keyrings/cloudflare-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/cloudflare-archive-keyring.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt update && sudo apt install cloudflared

# 2. Start the tunnel (Flask must already be running on port 5000)
cloudflared tunnel --url http://localhost:5000

# 3. Copy the printed URL, e.g.:
#    https://abc-def-ghi.trycloudflare.com

# 4. In Render dashboard → grps-frontend → Environment → BACKEND_URL
#    Paste that URL and trigger a manual deploy.
```

> ⚠️  Quick tunnel URLs change every restart. Re-paste into Render each time.

---

## Option B — Named tunnel (free Cloudflare account, permanent URL)

```bash
# 1. Log in
cloudflared login

# 2. Create a named tunnel
cloudflared tunnel create grps-backend

# 3. Create config file  ~/.cloudflared/config.yml
cat > ~/.cloudflared/config.yml << YAML
tunnel: grps-backend
credentials-file: /home/$USER/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: grps-backend.yourdomain.com
    service: http://localhost:5000
  - service: http_status:404
YAML

# 4. Add DNS record (routes yourdomain.com → tunnel)
cloudflared tunnel route dns grps-backend grps-backend.yourdomain.com

# 5. Run the tunnel
cloudflared tunnel run grps-backend

# 6. Set BACKEND_URL=https://grps-backend.yourdomain.com in Render (permanent)

# Optional: install as a system service so it starts on boot
sudo cloudflared service install
```

---

## Starting everything locally

```bash
# Terminal 1 — Flask backend
cd /path/to/grps_weight
cp .env.example .env          # fill in your values
pip install -r requirements.txt
python app.py
# or: gunicorn app:app --workers 1 --worker-class gthread --threads 4 --bind 0.0.0.0:5000

# Terminal 2 — Cloudflare tunnel
cloudflared tunnel --url http://localhost:5000
# (copy the https://... URL into Render BACKEND_URL)
```

---

## Render deploy checklist

1. Push the updated repo to GitHub
2. In Render → grps-frontend → Environment, set:
   - `BACKEND_URL` = your Cloudflare tunnel URL (no trailing slash)
3. Trigger a manual deploy (or it auto-deploys on push)
4. Open `https://grps-frontend.onrender.com` — you should see the login page

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Login page shows "Cannot reach backend" | Tunnel not running, or BACKEND_URL wrong in Render |
| Login succeeds but API calls fail (CORS error) | `RENDER_FRONTEND_URL` not set in local `.env`, or Flask not restarted |
| Cookies not sent (401 on every request) | Flask must run behind HTTPS (Cloudflare tunnel provides this). Make sure `SESSION_COOKIE_SECURE=True` stays set. |
| Tunnel URL changed after restart | Use Option B (named tunnel) for a permanent URL |
