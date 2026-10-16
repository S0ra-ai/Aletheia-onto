# Self-hosted deployment

> Images, orchestration and the preflight that blocks unsafe configurations.

Back to [English README](../README.md) · [中文 README](../README.zh-CN.md)

```bash
cp deploy/.env.example deploy/.env    # fill in real values; the example has no usable defaults
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d
```

Two-stage image, non-root, no bundled credentials and no seeded database. The reference
compose file uses PostgreSQL as the platform store and does not publish the database port.

部署完成后，平台后端会同时提供管理端：打开 `http://<host>:8000/admin/`，API 使用
同源的 `/api` 前缀。这样不需要额外启动前端容器；开发环境仍可单独运行 Vite 前端。

## Deployment preflight

```bash
aletheia preflight --workers 4 --expect-origin https://ontology.example.com
```

Exits 1 on a blocker, so it works as a pipeline gate. `aletheia serve` runs it
**automatically** when binding to a non-loopback address and refuses to start — nobody
remembers to run a separate command, and the one deployment where it matters is the one
where `ONTOLOGY_AUTH_DISABLED=1` was left behind.

Every check catches a **silent** failure: the platform starts, serves traffic, and looks
healthy.

| Misconfiguration | What actually happens | Level |
|---|---|:--:|
| `ONTOLOGY_AUTH_DISABLED=1` left on | the whole API is reachable with no token, **including writeback** | blocker |
| CORS set to `*` | any site can drive the API carrying a user's credentials | blocker |
| admin password is a placeholder or under 12 chars | somebody chose it and will assume it was changed | blocker |
| SQLite with several workers | writes serialise; the symptom is **intermittent timeouts**, not a config error | blocker |
| platform DB file readable by group/other | that file holds every data source's connection string | blocker |
| CORS still localhost | the real frontend is blocked, and the next step someone takes is `*` | warning |
| admin password unset | a random one is printed once, and container logs rotate | warning |
| password inline in the connection URI | it appears in the process list, container inspect, and crash logs | warning |
| rate limiting never configured | one caller generates unbounded load; nothing logs the requests that were *not* throttled, so the first symptom is the service falling over | warning |

A single-node SQLite evaluation deployment is legitimate, so one worker does not block —
refusing it would push people to skip the check entirely.

Full reasoning in [ADR-0017](adr/0017-deployment-preflight.md).

## Scheduled backups

**`scripts/backup.sh` backs up a local SQLite platform database only.** The reference compose file
uses PostgreSQL, and for that deployment use `pg_dump` / PITR instead: the script's own header and
`backup.py` both refuse a server-side database rather than produce a physical snapshot that cannot
be restored.

For a SQLite deployment the script **does not guess where the database is** -- both variables must
be given explicitly, and cron inherits nothing from your shell, so they belong in the crontab line
itself. Without them the script exits before creating anything (`set -e` plus a required variable):

```bash
crontab -e
0 2 * * * ONTOLOGY_PLATFORM_DB_FILE=/srv/aletheia/platform.sqlite3 ONTOLOGY_BACKUP_DIR=/srv/aletheia/backups /path/to/scripts/backup.sh >> /var/log/aletheia-backup.log 2>&1
```

`PYTHON_BIN` names the interpreter the script runs (it defaults to `python3`): set it to your
virtualenv's interpreter when the platform is installed in one. Environment variables are in
[Configuration](configuration.md); restoring, including the snapshot taken before a restore, is in
[Operations](operations.md).

## Before you go live

[The production checklist](production-checklist.md) is the list to work through -- infrastructure,
secrets, the settings whose defaults are safe for an evaluation and not for a deployment. It is
written in Chinese; the English equivalent is this page plus [Operations](operations.md).

It was reachable from nowhere until a check for orphaned pages was added: a page nothing links
to is a page nobody reads, and 79 lines of pre-production checks were sitting in the repository
with no reader.

