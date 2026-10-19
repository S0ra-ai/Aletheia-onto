# Operations

## Day-to-day monitoring

### Health checks
```bash
# service status
curl http://localhost:8000/health

# metrics
curl http://localhost:8000/metrics
```

### Reading the logs

Logs go to stderr by default, and a containerised deployment hands them to the runtime
(`docker logs` / Kubernetes). To write them to disk, set `ONTOLOGY_LOG_FILE`: the directory is
created, and the file rotates at 10 MiB keeping five copies.

```bash
export ONTOLOGY_LOG_FILE=/var/log/aletheia/platform.log
```

For a log aggregator to parse, turn on JSON (one object per line):

```bash
export ONTOLOGY_LOG_FORMAT=json     # default text, for a person to read
export ONTOLOGY_LOG_LEVEL=INFO      # default INFO
```

Both formats carry `request_id`: inline as `request_id=…` in text, as the `requestId` field in
JSON. **Every record — including warnings emitted from inside a dependency — carries the current
request's id**, because the id is bound to the context when the request arrives rather than
passed down by each call site.

Follow one request through the log:

```bash
grep "request_id=a1b2c3…" /var/log/aletheia/platform.log
```

The id comes from one of two places: the platform (a full UUID4), or the caller through the
`X-Request-Id` header — which lets a gateway line its own ids up with this service's logs. The
response always echoes the same id back.

**When investigating a 500, take the id from the response body first.** The response to an
unhandled exception is `{"detail": …, "code": "internal_error", "requestId": "…"}`; the exception
itself goes to the log and not into the body (exception text contains file paths, SQL fragments,
and occasionally data rows). A user reporting a failure can paste that id and it will locate the
rest.

> The access log records the path and **not the query string**: a query string often carries a
> credential like `?token=`, and an access log is the thing most often shipped to a third-party
> aggregator. uvicorn's own access log prints the whole request line including the query string,
> so its level is raised to WARNING at startup — one access log remains, and it is the one that
> does not leak parameters.

### Request rate limiting

Off by default, because the right number depends on a deployment's traffic and the package
cannot know it. When enabled it counts by caller address and **applies before authentication** —
an unauthenticated flood is exactly what it is for:

```bash
export ONTOLOGY_RATE_LIMIT_PER_MINUTE=600        # 0 or unset = no limit
export ONTOLOGY_RATE_LIMIT_AUTH_PER_MINUTE=10    # login / SSO, default 10, stricter
```

A refused request returns `429` with a standard `Retry-After` header; a normal response carries
`X-RateLimit-Limit` and `X-RateLimit-Remaining`. Public paths such as the health check and
`/metrics` are not counted, or monitoring would consume the quota of the address it monitors.

Counters are per process: with several workers the effective limit is the configured value times
the worker count. Sharing a counter across processes needs storage this package does not depend
on, which is written down in [current limitations](limitations.md) rather than papered over.

`aletheia preflight` warns when the service is reachable from the network with no limit set.

### Metrics
Prometheus at http://localhost:9090
- HTTP request rate
- error rate
- response time P99
- active sessions

## Backup and restore

### Create a backup

The built-in HTTP backup supports the SQLite platform database only, and `/admin/backup/*`
requires an administrator token:
```bash
curl -X POST http://localhost:8000/admin/backup/create \
  -H "Authorization: Bearer $ONTOLOGY_ADMIN_TOKEN"
```

### List backups
```bash
curl http://localhost:8000/admin/backup/list \
  -H "Authorization: Bearer $ONTOLOGY_ADMIN_TOKEN"
```

### Restore a backup
```bash
curl -X POST http://localhost:8000/admin/backup/restore/{backup_name} \
  -H "Authorization: Bearer $ONTOLOGY_ADMIN_TOKEN"
```

A restore replaces the current SQLite platform database and should be run with the service
stopped. **Before restoring, the platform saves the current database as a
`before-restore-<UTC timestamp>` backup** and reports its name in the response as `safetyCopy` —
a backup list holds dozens of similarly named archives, picking the wrong one is ordinary, and
the time you pick wrong has to be recoverable. If the snapshot cannot be written the **restore is
refused** (fail-closed): losing what you have and then installing something possibly wrong is
worse than not restoring.

The production reference stack uses PostgreSQL; back that up with `pg_dump` / PITR. The built-in
backup endpoint refuses a server database outright rather than producing an unrecoverable
physical snapshot.

## Troubleshooting

### The service will not start
1. `aletheia preflight` — the deployment check names the configuration item that is wrong.
   `aletheia serve` runs it itself before binding a non-loopback address and refuses to start
   when it fails.
2. Check the port: `lsof -i :8000`
3. Check the platform database: `ls -la data/platform.sqlite3`

### A 500
1. Take `requestId` from the response body.
2. `grep "request_id=<that value>" <log file>` for the full stack and every log line of that
   request.
3. If the logs are on stderr, in a container use
   `docker logs <container> 2>&1 | grep <that value>`.

### Performance
1. Look at `/metrics`: request rate, error rate, response time.
2. Check the database connection count — the platform does not pool; every `connect()` opens a
   new connection, so the count rises linearly with concurrency.
3. Check memory: `top -p $(pgrep -f uvicorn)`

### Authentication
1. Reset the administrator password (the bootstrap flow `aletheia` provides).
2. Expired sessions are cleared at startup; the log records how many.
3. Authentication uses an **opaque bearer token** (only a digest is stored), not a JWT; a JWT
   appears only on the SSO path (see [configuration](configuration.md)).

## Upgrading

1. Back up the database (the `aletheia` backup endpoint, or `pg_dump`).
2. Stop the service.
3. `pip install -U aletheia-onto`.
4. Start the service — **migrations are applied at startup**, with no separate manual step; the
   versions applied are logged and recorded in the platform database's version ledger.
5. Verify: `curl http://localhost:8000/health`.

## Security checklist

- [ ] Change the default administrator password
- [ ] Configure HTTPS
- [ ] Set firewall rules
- [ ] Enable audit logging (`ONTOLOGY_LOG_FILE`, or ship to a log aggregator)
- [ ] Set request rate limits (`ONTOLOGY_RATE_LIMIT_PER_MINUTE`)
- [ ] Configure a backup schedule
- [ ] Set up monitoring alerts
