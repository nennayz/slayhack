#!/usr/bin/env bash
# NayzFreedom VPS Setup Script
# Run once on a fresh Ubuntu/Debian server as root (or with sudo).
#
# Usage:
#   curl -sO https://raw.githubusercontent.com/nennayz/nayzfreedom-fleet/main/deploy/setup.sh
#   chmod +x setup.sh
#   sudo ./setup.sh
#
# What it does:
#   1. Installs system dependencies (python3, git, nginx optional)
#   2. Creates a dedicated system user (nayzfreedom)
#   3. Clones the repo to /opt/nayzfreedom
#   4. Creates a venv and installs requirements
#   5. Copies .env.example → /opt/nayzfreedom/.env (you fill in keys after)
#   6. Installs systemd units for dashboard, scheduler, reporter
#   7. Creates dashboard auth defaults if missing
#   8. Enables and starts dashboard, then conditionally enables bot/timers
#   9. Enables production backup, health-check, Instagram queue, and summary timers

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/nennayz/nayzfreedom-fleet.git}"
INSTALL_DIR="/opt/nayzfreedom"
SERVICE_USER="nayzfreedom"
PYTHON="python3"

echo "=== NayzFreedom VPS Setup ==="

# ── 1. System deps ──────────────────────────────────────────────────────────
echo "[1/6] Installing system packages..."
apt-get update -q
apt-get install -y -q python3 python3-venv python3-pip git curl

# ── 2. Create service user ───────────────────────────────────────────────────
echo "[2/6] Creating system user '$SERVICE_USER'..."
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --shell /bin/bash --home "$INSTALL_DIR" --create-home "$SERVICE_USER"
fi

# ── 3. Clone / update repo ───────────────────────────────────────────────────
echo "[3/6] Cloning repo to $INSTALL_DIR..."
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "  Repo already exists — pulling latest..."
    sudo -u "$SERVICE_USER" git -C "$INSTALL_DIR" pull
else
    # For private repos, run with REPO_URL=git@github.com:nennayz/nayzfreedom-fleet.git
    # and copy your deploy key first:
    #   ssh-keygen -t ed25519 -C "nayzfreedom-deploy" -f /home/nayzfreedom/.ssh/id_ed25519
    #   cat /home/nayzfreedom/.ssh/id_ed25519.pub  → add as Deploy Key on GitHub
    sudo -u "$SERVICE_USER" git clone "$REPO_URL" "$INSTALL_DIR"
fi

# ── 4. Python venv + requirements ────────────────────────────────────────────
echo "[4/6] Setting up Python venv..."
sudo -u "$SERVICE_USER" $PYTHON -m venv "$INSTALL_DIR/.venv"
sudo -u "$SERVICE_USER" "$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade pip
sudo -u "$SERVICE_USER" "$INSTALL_DIR/.venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"

# ── 5. .env file ─────────────────────────────────────────────────────────────
echo "[5/6] Creating .env..."
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    chown "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/.env"
    chmod 600 "$INSTALL_DIR/.env"
else
    echo "  .env already exists — skipping."
fi

if ! grep -q '^DASHBOARD_USER=.\+' "$INSTALL_DIR/.env"; then
    sed -i 's/^DASHBOARD_USER=.*/DASHBOARD_USER=admin/' "$INSTALL_DIR/.env"
fi
if ! grep -q '^DASHBOARD_PASSWORD=.\+' "$INSTALL_DIR/.env"; then
    DASHBOARD_PASSWORD="$($PYTHON -c 'import secrets; print(secrets.token_urlsafe(24))')"
    sed -i "s#^DASHBOARD_PASSWORD=.*#DASHBOARD_PASSWORD=$DASHBOARD_PASSWORD#" "$INSTALL_DIR/.env"
    echo ""
    echo "  Dashboard login created:"
    echo "  DASHBOARD_USER=admin"
    echo "  DASHBOARD_PASSWORD=$DASHBOARD_PASSWORD"
    echo "  Store this password now."
    echo ""
fi

# ── 6. Install + enable systemd units ────────────────────────────────────────
echo "[6/6] Installing systemd units..."
DEPLOY_DIR="$(dirname "$0")"

for unit in \
    nayzfreedom-dashboard.service \
    nayzfreedom-bot.service \
    nayzfreedom-comment-reply-bot.service \
    nayzfreedom-scheduler.service \
    nayzfreedom-scheduler.timer \
    nayzfreedom-reporter.service \
    nayzfreedom-reporter.timer \
    nayzfreedom-instagram-queue.service \
    nayzfreedom-instagram-queue.timer \
    nayzfreedom-production-summary.service \
    nayzfreedom-production-summary.timer \
    nayzfreedom-log-retention.service \
    nayzfreedom-log-retention.timer \
    nayzfreedom-ops-report.service \
    nayzfreedom-ops-report.timer \
    nayzfreedom-backup.service \
    nayzfreedom-backup.timer \
    nayzfreedom-healthcheck.service \
    nayzfreedom-healthcheck.timer \
    nayzfreedom-track-scheduler.service \
    nayzfreedom-track-scheduler.timer; do
    cp "$DEPLOY_DIR/$unit" "/etc/systemd/system/$unit"
done

chmod +x "$INSTALL_DIR/deploy/backup.sh" "$INSTALL_DIR/deploy/healthcheck.sh" "$INSTALL_DIR/deploy/restore_smoke.sh"
if [ -f "$INSTALL_DIR/deploy/nayzfreedom-ops.sudoers" ]; then
    cp "$INSTALL_DIR/deploy/nayzfreedom-ops.sudoers" /etc/sudoers.d/nayzfreedom-ops
    chmod 440 /etc/sudoers.d/nayzfreedom-ops
fi

systemctl daemon-reload

# Dashboard runs persistently
systemctl enable --now nayzfreedom-dashboard.service
sleep 2
curl -fsS http://127.0.0.1:8000/healthz >/dev/null

if grep -q '^TELEGRAM_BOT_TOKEN=.\+' "$INSTALL_DIR/.env" && grep -q '^TELEGRAM_CHAT_ID=.\+' "$INSTALL_DIR/.env"; then
    systemctl enable --now nayzfreedom-bot.service
else
    systemctl disable --now nayzfreedom-bot.service 2>/dev/null || true
    echo "  Telegram bot not started: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is empty."
fi

comment_chat_map_path="$(grep -E '^COMMENT_CHAT_MAP_PATH=.' "$INSTALL_DIR/.env" | tail -n 1 | cut -d= -f2-)"
comment_chat_map_path="${comment_chat_map_path:-$INSTALL_DIR/secrets/comment_chat_map.yaml}"
if grep -q '^COMMENT_BOT_TOKEN=.\+' "$INSTALL_DIR/.env" && grep -q '^GEMINI_API_KEY=.\+' "$INSTALL_DIR/.env" && [ -f "$comment_chat_map_path" ]; then
    systemctl enable --now nayzfreedom-comment-reply-bot.service
else
    systemctl disable --now nayzfreedom-comment-reply-bot.service 2>/dev/null || true
    echo "  Comment reply bot not started: COMMENT_BOT_TOKEN, GEMINI_API_KEY, or COMMENT_CHAT_MAP_PATH is missing."
fi

if grep -q '^OPENAI_API_KEY=.\+' "$INSTALL_DIR/.env"; then
    systemctl enable --now nayzfreedom-scheduler.timer
    systemctl enable --now nayzfreedom-reporter.timer
else
    systemctl disable --now nayzfreedom-scheduler.timer nayzfreedom-reporter.timer 2>/dev/null || true
    echo "  Scheduler/reporter timers not started: OPENAI_API_KEY is empty."
fi

systemctl enable --now nayzfreedom-backup.timer
systemctl enable --now nayzfreedom-healthcheck.timer
systemctl enable --now nayzfreedom-instagram-queue.timer
systemctl enable --now nayzfreedom-production-summary.timer
systemctl enable --now nayzfreedom-log-retention.timer
systemctl enable --now nayzfreedom-ops-report.timer
systemctl enable --now nayzfreedom-track-scheduler.timer

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Fill in API keys:  nano $INSTALL_DIR/.env"
echo "  2. Restart services:  systemctl restart nayzfreedom-dashboard"
echo "  3. Check dashboard:   systemctl status nayzfreedom-dashboard"
echo "  4. View logs:         journalctl -u nayzfreedom-dashboard -f"
echo "     Bot logs:          journalctl -u nayzfreedom-bot -f"
echo "  5. Health check:      curl http://127.0.0.1:8000/healthz"
echo "  6. Dashboard URL:     http://<your-server-ip>:8000"
echo ""
echo "Timers scheduled:"
echo "  Scheduler: daily at 06:00 UTC"
echo "  Reporter:  every Monday at 08:00 UTC"
echo "  Backup:    daily at 03:30 UTC"
echo "  Health:    every 5 minutes"
echo "  IG queue:  every 5 minutes"
echo "  Summary:   daily at 00:15 UTC"
echo "  Logs:      daily at 00:30 UTC"
echo "  Ops report: every Monday at 00:45 UTC"
echo "  Track:     every hour (on-demand)"
echo "  Check with: systemctl list-timers | grep nayz"
