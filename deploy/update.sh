#!/usr/bin/env bash
# Pull latest code and restart services.
# Run on the VPS as root (or with sudo) whenever you push changes.
#
# Usage: sudo ./update.sh

set -euo pipefail

INSTALL_DIR="/opt/nayzfreedom"
SERVICE_USER="nayzfreedom"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"

echo "=== NayzFreedom Update ==="

echo "[preflight] Checking deploy ownership..."
ownership_probe="$(find "$INSTALL_DIR" -path "$INSTALL_DIR/.venv" -prune -o -path "$INSTALL_DIR/.git" -prune -o ! -user "$SERVICE_USER" -print -quit)"
if [ -n "$ownership_probe" ]; then
    echo "ownership_warning=$ownership_probe"
    echo "Repairing $INSTALL_DIR ownership for $SERVICE_USER before pulling."
    chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
fi

echo "[1/3] Pulling latest code..."
sudo -u "$SERVICE_USER" git -C "$INSTALL_DIR" fetch origin "$DEPLOY_BRANCH"
current_branch="$(sudo -u "$SERVICE_USER" git -C "$INSTALL_DIR" branch --show-current)"
if [ "$current_branch" != "$DEPLOY_BRANCH" ]; then
    sudo -u "$SERVICE_USER" git -C "$INSTALL_DIR" switch "$DEPLOY_BRANCH"
fi
sudo -u "$SERVICE_USER" git -C "$INSTALL_DIR" pull --ff-only origin "$DEPLOY_BRANCH"

echo "[2/3] Installing dependencies..."
sudo -u "$SERVICE_USER" "$INSTALL_DIR/.venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"
if [ -f "$INSTALL_DIR/deploy/nayzfreedom-ops.sudoers" ]; then
    cp "$INSTALL_DIR/deploy/nayzfreedom-ops.sudoers" /etc/sudoers.d/nayzfreedom-ops
    chmod 440 /etc/sudoers.d/nayzfreedom-ops
fi
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
    cp "$INSTALL_DIR/deploy/$unit" "/etc/systemd/system/$unit"
done

echo "[3/3] Restarting services..."
systemctl daemon-reload
systemctl enable --now nayzfreedom-log-retention.timer
systemctl enable --now nayzfreedom-ops-report.timer
systemctl enable --now nayzfreedom-track-scheduler.timer
systemctl restart nayzfreedom-dashboard.service
systemctl status nayzfreedom-dashboard.service --no-pager
if grep -q '^TELEGRAM_BOT_TOKEN=.\+' "$INSTALL_DIR/.env" && grep -q '^TELEGRAM_CHAT_ID=.\+' "$INSTALL_DIR/.env"; then
    systemctl enable --now nayzfreedom-bot.service
    systemctl restart nayzfreedom-bot.service
    systemctl status nayzfreedom-bot.service --no-pager
else
    systemctl disable --now nayzfreedom-bot.service 2>/dev/null || true
    echo "Bot not started: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing."
fi
comment_chat_map_path="$(grep -E '^COMMENT_CHAT_MAP_PATH=.' "$INSTALL_DIR/.env" | tail -n 1 | cut -d= -f2-)"
comment_chat_map_path="${comment_chat_map_path:-$INSTALL_DIR/secrets/comment_chat_map.yaml}"
if grep -q '^COMMENT_BOT_TOKEN=.\+' "$INSTALL_DIR/.env" && grep -q '^GEMINI_API_KEY=.\+' "$INSTALL_DIR/.env" && [ -f "$comment_chat_map_path" ]; then
    systemctl enable --now nayzfreedom-comment-reply-bot.service
    systemctl restart nayzfreedom-comment-reply-bot.service
    systemctl status nayzfreedom-comment-reply-bot.service --no-pager
else
    systemctl disable --now nayzfreedom-comment-reply-bot.service 2>/dev/null || true
    echo "Comment reply bot not started: COMMENT_BOT_TOKEN, GEMINI_API_KEY, or COMMENT_CHAT_MAP_PATH is missing."
fi
systemctl restart nayzfreedom-healthcheck.timer

echo ""
echo "Done. Services are running."
echo "Dashboard logs: journalctl -u nayzfreedom-dashboard -f"
echo "Bot logs:       journalctl -u nayzfreedom-bot -f"
echo "Comment logs:   journalctl -u nayzfreedom-comment-reply-bot -f"
