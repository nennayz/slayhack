# Slayhack Production Runbook

This runbook covers the current production deployment for the Slayhack dashboard and automation services.

## Production Targets

- Dashboard: `https://fleet.nayzfreedom.cloud/aurora`
- Health check: `https://fleet.nayzfreedom.cloud/healthz`
- VPS: `root@2.24.88.63`
- App path: `/opt/nayzfreedom`
- Dashboard service: `nayzfreedom-dashboard.service`
- Bot service: `nayzfreedom-bot.service`
- Timers: `nayzfreedom-scheduler.timer`, `nayzfreedom-reporter.timer`
- Instagram queue timer: `nayzfreedom-instagram-queue.timer`
- Backup timer: `nayzfreedom-backup.timer`
- Health-check timer: `nayzfreedom-healthcheck.timer`
- Production summary timer: `nayzfreedom-production-summary.timer`
- Traefik dynamic config: `/docker/traefik-fmcv/dynamic/nayzfreedom.yml`

## Deploy

Run from the VPS:

```bash
ssh root@2.24.88.63
cd /opt/nayzfreedom
chown -R nayzfreedom:nayzfreedom /opt/nayzfreedom
./deploy/update.sh
```

`main` is protected. Make production changes on a feature branch, open a pull
request, merge the pull request, then run `./deploy/update.sh` on the VPS. For
an emergency branch deploy, set `DEPLOY_BRANCH=your-branch`, but prefer the
protected pull-request path.

Verify:

```bash
systemctl is-active nayzfreedom-dashboard.service
systemctl is-active nayzfreedom-bot.service
systemctl is-active nayzfreedom-scheduler.timer
systemctl is-active nayzfreedom-reporter.timer
systemctl is-active nayzfreedom-instagram-queue.timer
systemctl is-active nayzfreedom-backup.timer
systemctl is-active nayzfreedom-healthcheck.timer
systemctl is-active nayzfreedom-production-summary.timer
curl -fsS https://fleet.nayzfreedom.cloud/healthz
```

## Smoke Test

Expected results:

```text
HTTPS /healthz: 200
HTTP /healthz: 301 redirect to HTTPS
Unauthenticated /: 401
Authenticated /: 200
Authenticated /aurora: 200
Authenticated /aurora/missions: 200 and contains Slayhack
Authenticated /readiness: 200
Dashboard service: active
Bot service: active
Scheduler timer: active
Reporter timer: active
Instagram queue timer: active
Backup timer: active
Health-check timer: active
Production summary timer: active
Traefik config: present
```

Use credentials from `/opt/nayzfreedom/.env` on the VPS. Do not print credentials in shell logs.

## Rollback

Use rollback only when the latest deploy breaks production.

```bash
ssh root@2.24.88.63
cd /opt/nayzfreedom
git log --oneline -5
sudo -u nayzfreedom git -C /opt/nayzfreedom reset --hard <known-good-commit>
systemctl restart nayzfreedom-dashboard.service
systemctl restart nayzfreedom-bot.service
curl -fsS https://fleet.nayzfreedom.cloud/healthz
```

After rollback, create a fix-forward commit locally and deploy normally.

## Logs

```bash
journalctl -u nayzfreedom-dashboard.service -n 100 --no-pager
journalctl -u nayzfreedom-bot.service -n 100 --no-pager
journalctl -u nayzfreedom-scheduler.service -n 100 --no-pager
journalctl -u nayzfreedom-instagram-queue.service -n 100 --no-pager
journalctl -u nayzfreedom-reporter.service -n 100 --no-pager
journalctl -u nayzfreedom-backup.service -n 100 --no-pager
journalctl -u nayzfreedom-healthcheck.service -n 100 --no-pager
journalctl -u nayzfreedom-production-summary.service -n 100 --no-pager
```

For a quick 24-hour error check:

```bash
journalctl -u nayzfreedom-dashboard.service --since "24 hours ago" --no-pager | grep -E "Traceback|ERROR|CRITICAL"
journalctl -u nayzfreedom-bot.service --since "24 hours ago" --no-pager | grep -E "Traceback|ERROR|CRITICAL"
journalctl -u nayzfreedom-scheduler.service --since "24 hours ago" --no-pager | grep -E "Traceback|ERROR|CRITICAL"
journalctl -u nayzfreedom-reporter.service --since "24 hours ago" --no-pager | grep -E "Traceback|ERROR|CRITICAL"
```

## Backups

Backups are stored on the VPS under `/opt/nayzfreedom-backups`.

Each backup contains:

- `.env`
- `projects/`
- `output/`
- `logs/`
- Traefik dynamic config, when present
- SHA-256 checksum for the state archive

Run manually:

```bash
systemctl start nayzfreedom-backup.service
journalctl -u nayzfreedom-backup.service -n 50 --no-pager
```

For off-server Google Drive backup with a service account, set these in `/opt/nayzfreedom/.env`:

```text
GOOGLE_APPLICATION_CREDENTIALS=/opt/nayzfreedom/secrets/google-service-account.json
GOOGLE_DRIVE_BACKUP_FOLDER_ID=<drive-folder-id>
```

The service account must have write access to the target Drive folder. For service-account uploads, use a Google Shared Drive folder or OAuth/domain delegation; regular My Drive folders can return `storageQuotaExceeded` because service accounts do not have personal Drive storage quota.

For personal My Drive backup, create a desktop OAuth client and set these instead:

```text
GOOGLE_DRIVE_OAUTH_CLIENT_SECRETS=/opt/nayzfreedom/secrets/google-oauth-client.json
GOOGLE_DRIVE_OAUTH_TOKEN_FILE=/opt/nayzfreedom/secrets/google-oauth-token.json
```

Drive upload failures are logged as `drive_backup=failed` while the local VPS backup still succeeds.

For manual post kits, create a separate Google Drive folder named `NayzFreedom Fleet Manual Kits`,
share it with the same service account or OAuth user, then set:

```text
GOOGLE_DRIVE_MANUAL_KITS_FOLDER_ID=<manual-kits-root-folder-id>
```

The dashboard creates project/type subfolders inside that folder, for example
`SlayHack/04_Video_PreProduction`, and uploads structured ZIP kits for manual posting.

Verify the latest local backup archive:

```bash
/opt/nayzfreedom/deploy/restore_smoke.sh
```

The restore smoke command appends successful checks to
`/opt/nayzfreedom/logs/restore_smoke.jsonl`, which is shown on `/ops`.

## Restore Drill

Use this drill when validating a backup without replacing production:

```bash
ssh root@2.24.88.63
latest="$(find /opt/nayzfreedom-backups -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)"
mkdir -p /tmp/nayzfreedom-restore-drill
tar -xzf "$latest/state.tgz" -C /tmp/nayzfreedom-restore-drill
ls -la /tmp/nayzfreedom-restore-drill
/opt/nayzfreedom/deploy/restore_smoke.sh
```

Do not overwrite `/opt/nayzfreedom` during a drill. For a real restore, stop
services first, copy the verified state into place, fix ownership, then restart
dashboard and bot services.

## Alerts

Scheduler failure alerts, weekly reports, daily production summaries, and health-check failures use
`SLACK_WEBHOOK_URL` first. If Slack is not set, they fall back to Telegram when
both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are present.

Run the summary manually without sending:

```bash
sudo -u nayzfreedom /opt/nayzfreedom/.venv/bin/python /opt/nayzfreedom/production_summary.py --dry-run
```

## Monitoring

The health-check timer runs every 5 minutes and fails when:

- public `/healthz` is unavailable
- dashboard, bot, scheduler timer, reporter timer, Instagram queue timer, or production summary timer is inactive
- disk usage for `/opt/nayzfreedom` is 85% or higher
- `META_ACCESS_TOKEN` is set but the Meta Graph `/me` check fails
- recent logs from the last 5 minutes contain `Traceback`, `ERROR`, or `CRITICAL`

Run manually:

```bash
systemctl start nayzfreedom-healthcheck.service
journalctl -u nayzfreedom-healthcheck.service -n 50 --no-pager
```

## Security Notes

- Keep Git remotes free of embedded tokens.
- Keep `.env` and `.env.save` permission at `600`.
- Revoke old GitHub tokens after replacing token-based remotes.
- Keep local VPS-only files in `.git/info/exclude`, not in repo `.gitignore`.
- Do not commit production secrets, generated logs, or runtime caches.

## Token Rotation Checklist

Run this after a suspected leak, staff/device change, or scheduled maintenance:

- GitHub: revoke unused classic/fine-grained tokens, then confirm the VPS remote does not contain a token.
- Meta: rotate the long-lived access token and run `deploy/healthcheck.sh`.
- Google Drive: rotate service-account or OAuth JSON, then run backup and restore smoke.
- Telegram: rotate bot token, update `/opt/nayzfreedom/.env`, restart bot and healthcheck timers.
- Dashboard: rotate `DASHBOARD_PASSWORD`, restart dashboard, and confirm Basic Auth still works.
- After any rotation, run `/opt/nayzfreedom/deploy/healthcheck.sh` and inspect `/ops`.
