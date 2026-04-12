# Database Backup

FlowList uses PostgreSQL in a Docker volume. This guide covers manual and automated backups.

## Manual backup

```bash
# Dump to a timestamped file
docker compose exec db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
  | gzip > "flowlist_$(date +%Y%m%d_%H%M%S).sql.gz"
```

## Manual restore

```bash
gunzip -c flowlist_20260101_120000.sql.gz \
  | docker compose exec -T db psql -U "$POSTGRES_USER" "$POSTGRES_DB"
```

## Automated daily backup (cron)

Add to your host crontab (`crontab -e`):

```cron
0 3 * * * cd /path/to/flowlist && \
  docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
  | gzip > "/backups/flowlist_$(date +\%Y\%m\%d).sql.gz" && \
  find /backups -name "flowlist_*.sql.gz" -mtime +30 -delete
```

This:
- Runs at 3:00 AM daily
- Saves compressed dumps to `/backups/`
- Deletes dumps older than 30 days

## Off-site backup

For off-site copies, sync the `/backups/` directory with rclone:

```bash
# Install rclone and configure a remote (e.g. Backblaze B2, S3, Google Drive)
rclone sync /backups/ remote:flowlist-backups/
```

Add to crontab after the dump step:

```cron
30 3 * * * rclone sync /backups/ remote:flowlist-backups/
```

## Redis backup

Redis is used for sessions and the ARQ job queue. It does not need persistent backups — sessions are ephemeral and the job queue recovers on restart. The `redis_data` volume is preserved across container restarts.

If you want Redis persistence enabled, add `--save 60 1` to the Redis command in `docker-compose.yml`.
