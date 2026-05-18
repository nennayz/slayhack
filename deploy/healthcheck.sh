#!/usr/bin/env bash
# Fail fast when the production VPS is unhealthy.

set -euo pipefail

HEALTH_URL="${HEALTH_URL:-https://fleet.nayzfreedom.cloud/healthz}"
DISK_PATH="${DISK_PATH:-/opt/nayzfreedom}"
DISK_LIMIT="${DISK_LIMIT:-85}"
ERROR_WINDOW="${ERROR_WINDOW:-5 minutes ago}"
ENV_FILE="${ENV_FILE:-/opt/nayzfreedom/.env}"
META_GRAPH_BASE="${META_GRAPH_BASE:-https://graph.facebook.com/v25.0}"

if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
fi

notify_failure() {
    local status="$?"
    local line="${1:-unknown}"
    if [ "$status" -eq 0 ]; then
        return
    fi
    HEALTHCHECK_ALERT_MESSAGE="NayzFreedom health check failed on $(hostname) at line $line (exit $status)." \
        python3 - <<'PY' || true
import os
from notifier import send_healthcheck_alert

send_healthcheck_alert(os.environ["HEALTHCHECK_ALERT_MESSAGE"])
PY
    exit "$status"
}

trap 'notify_failure "$LINENO"' ERR

check_unit() {
    local unit="$1"
    systemctl is-active --quiet "$unit"
    echo "unit_ok=$unit"
}

curl -fsS "$HEALTH_URL" >/dev/null
echo "health_url_ok=$HEALTH_URL"

check_unit nayzfreedom-dashboard.service
check_unit nayzfreedom-bot.service
check_unit nayzfreedom-scheduler.timer
check_unit nayzfreedom-reporter.timer
check_unit nayzfreedom-instagram-queue.timer
check_unit nayzfreedom-production-summary.timer
check_unit nayzfreedom-log-retention.timer
check_unit nayzfreedom-ops-report.timer
check_unit nayzfreedom-track-scheduler.timer
if [ -n "${COMMENT_BOT_TOKEN:-}" ] && [ -n "${GEMINI_API_KEY:-}" ] && [ -f "${COMMENT_CHAT_MAP_PATH:-/opt/nayzfreedom/secrets/comment_chat_map.yaml}" ]; then
    check_unit nayzfreedom-comment-reply-bot.service
else
    echo "unit_skipped=nayzfreedom-comment-reply-bot.service"
fi

disk_used="$(df -P "$DISK_PATH" | awk 'NR == 2 {gsub("%", "", $5); print $5}')"
if [ "$disk_used" -ge "$DISK_LIMIT" ]; then
    echo "disk_used_percent=$disk_used limit=$DISK_LIMIT"
    exit 1
fi
echo "disk_ok_percent=$disk_used"

if [ -n "${META_ACCESS_TOKEN:-}" ]; then
    curl -fsS --get "$META_GRAPH_BASE/me" \
        --data-urlencode "fields=id,name" \
        --data-urlencode "access_token=$META_ACCESS_TOKEN" >/dev/null
    echo "meta_token_ok=$META_GRAPH_BASE/me"
else
    echo "meta_token_skipped=missing_META_ACCESS_TOKEN"
fi

for unit in \
    nayzfreedom-dashboard.service \
    nayzfreedom-bot.service \
    nayzfreedom-scheduler.service \
    nayzfreedom-instagram-queue.service \
    nayzfreedom-production-summary.service \
    nayzfreedom-log-retention.service \
    nayzfreedom-ops-report.service \
    nayzfreedom-track-scheduler.service \
    nayzfreedom-comment-reply-bot.service \
    nayzfreedom-reporter.service; do
    hits="$(journalctl -u "$unit" --since "$ERROR_WINDOW" --no-pager 2>/dev/null | { grep -E "Traceback|ERROR|CRITICAL" || true; } | wc -l | tr -d " ")"
    if [ "$hits" != "0" ]; then
        echo "recent_error_hits=$unit:$hits"
        exit 1
    fi
    echo "recent_errors_ok=$unit"
done
