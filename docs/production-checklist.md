# Production deployment checklist

## Infrastructure

- [ ] Use PostgreSQL rather than SQLite
- [ ] Size the database's `max_connections` to your concurrency ceiling — **the platform does
      not pool**; every `connect()` opens a new connection, so the count rises linearly with
      concurrency (see [current limitations](limitations.md))
- [ ] Enable database backups (nightly full + hourly incremental)
- [ ] Configure firewall rules (expose 80/443 only)
- [ ] Enable TLS/SSL (Let's Encrypt or a commercial certificate)

## Security

- [ ] Change the default administrator password (at least 16 random characters)
- [ ] Disable `ONTOLOGY_AUTH_DISABLED`
- [ ] Set request rate limits (`ONTOLOGY_RATE_LIMIT_PER_MINUTE`) — off by default, so an
      unset value leaves a single caller unbounded; the login endpoint has a stricter limit of
      its own
- [ ] Configure the correct CORS origins (never `*`)
- [ ] Protect the platform database's file permissions — **data source passwords and model API
      keys are stored in it in plaintext**, so that database *is* the credential store; prefer
      injecting the model key from the environment
- [ ] Configure RBAC policies
- [ ] Enable audit logging (`ONTOLOGY_LOG_FILE`, or ship to a log aggregator;
      `ONTOLOGY_LOG_FORMAT=json` is recommended)
- [ ] Rotate keys and application secrets on a schedule

## Monitoring and alerting

- [ ] Deploy Prometheus
- [ ] Configure a Grafana dashboard
- [ ] Set up Alertmanager
- [ ] Configure log aggregation (ELK/Loki)
- [ ] Alert on the metrics that matter:
  - [ ] HTTP error rate > 5%
  - [ ] P99 response time > 1s
  - [ ] database connections > 80%
  - [ ] disk usage > 85%
  - [ ] memory usage > 90%

## Performance

- [ ] Run multiple workers (`workers=4`)
- [ ] Cache responses at the reverse proxy or CDN — **the platform provides no response cache
      of its own**, and no Redis integration; cache at the gateway if you need it, and note that
      business-object endpoints filter rows by permission, so caching by URL would serve one
      role's visible rows to another
- [ ] Optimise database indexes (the objects' source tables and this platform's mapping tables)
- [ ] Configure a CDN (for static assets)

## Disaster recovery

- [ ] Schedule automatic nightly backups
- [ ] Test the restore procedure
- [ ] Configure cross-region backups
- [ ] Set RTO/RPO targets
- [ ] Run disaster-recovery drills regularly

## Operations documentation

- [ ] Update the operations manual
- [ ] Write incident procedures
- [ ] Set up an on-call rota
- [ ] Establish a change-management process
- [ ] Prepare a rollback plan

## Compliance

- [ ] Data encryption (in transit and at rest)
- [ ] Access-control audit
- [ ] Privacy policy updated
- [ ] Data retention policy
- [ ] Compliance reporting

## Final sign-off before going live

- [ ] All tests pass
- [ ] Performance benchmarks pass
- [ ] Security scan passes
- [ ] Backup-and-restore test passes
- [ ] Monitoring and alerting verified
- [ ] Operations team trained
- [ ] Incident response plan in place
